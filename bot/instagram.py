"""Instagram'ga avtopost: bazadagi e'lon -> Instagram post (Instagram Graph API, Content Publishing).

Oqim (rasmiy API, graph.facebook.com):
  1) POST /{IG_ACCOUNT_ID}/media            image_url + caption -> konteyner
     (2+ rasm bo'lsa: har rasmga is_carousel_item konteyner, keyin media_type=CAROUSEL)
  2) GET  /{container}?fields=status_code   FINISHED bo'lguncha kutiladi
  3) POST /{IG_ACCOUNT_ID}/media_publish    creation_id -> post
  4) instagram_posts jadvali: publishing -> published (media_id, permalink) | failed (error)

Rasm: Instagram faqat ochiq https:// havoladagi JPEG'ni yuklab oladi. Rasmlar Telegram'da (file_id)
yoki tashqi saytda bo'lgani uchun server ularni o'zi beradi:
  GET /ig/img/{house_id}/{n}.jpg?exp=..&sig=..
Havola HMAC bilan imzolangan va vaqtinchalik (IMAGE_TTL) — faqat bizning skript yaratgan havolalar ishlaydi.
Rasm JPEG'ga o'giriladi va Instagram ruxsat bergan nisbatga (4:5 ... 1.91:1) chetiga fon qo'shib keltiriladi.
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import io
import logging
import re
import time
from decimal import Decimal
from typing import Any

import aiohttp

from bot import db
from bot.config import config

log = logging.getLogger("instagram")

GRAPH = "https://graph.facebook.com"
IMAGE_TTL = 24 * 3600            # Instagram konteyneri 24 soat yashaydi
MAX_CAROUSEL = 10
MIN_RATIO, MAX_RATIO = 4 / 5, 1.91
MAX_WIDTH, MIN_WIDTH = 1440, 320
MAX_SOURCE_BYTES = 15 * 1024 * 1024
CAPTION_MAX = 2200
PAD_COLOR = (245, 245, 245)

_task: asyncio.Task | None = None


class IgError(RuntimeError):
    pass


# ------------------------------------------------------------ image links ---

def _sign_key() -> bytes:
    return hashlib.sha256(b"ig-image:" + config.bot_token.encode()).digest()


def sign(house_id: int, n: int, exp: int) -> str:
    return hmac.new(_sign_key(), f"{house_id}:{n}:{exp}".encode(), hashlib.sha256).hexdigest()[:32]


def verify(house_id: int, n: int, exp: str, sig: str) -> bool:
    try:
        exp_i = int(exp)
    except (TypeError, ValueError):
        return False
    if exp_i < time.time():
        return False
    return hmac.compare_digest(sign(house_id, n, exp_i), sig or "")


def image_url(house_id: int, n: int, ttl: int = IMAGE_TTL) -> str:
    if not config.public_base_url:
        raise IgError("PUBLIC_BASE_URL (yoki WEBAPP_URL) yo'q: Instagram rasmni yuklab olishi uchun ochiq server manzili kerak.")
    exp = int(time.time()) + ttl
    return f"{config.public_base_url}/ig/img/{house_id}/{n}.jpg?exp={exp}&sig={sign(house_id, n, exp)}"


def photo_refs(h) -> list[str]:
    """E'lon rasmlari: 'tg:<file_id>' (Telegram) yoki http(s) havola."""
    refs = [r for r in (h["photo_urls"] or []) if r]
    if not refs and h["photo_file_id"]:
        refs = ["tg:" + h["photo_file_id"]]
    return refs


def is_public(h) -> bool:
    return bool(h["is_active"] and not h["admin_hidden"] and h["status"] == "approved")


async def fetch_photo(bot, ref: str) -> bytes:
    """Asl rasm baytlari: Telegram file_id bo'lsa bot orqali, aks holda HTTP orqali."""
    if ref.startswith("tg:"):
        tg_file = await bot.get_file(ref[3:])
        buf = await bot.download_file(tg_file.file_path)
        return buf.read()
    if not ref.startswith(("http://", "https://")):
        raise IgError("rasm manzili noto'g'ri")
    headers = {"User-Agent": "ArendaUzBot/1.0 (Telegram @Arenda1UzBot)"}
    async with aiohttp.ClientSession(headers=headers) as s:
        async with s.get(ref, timeout=aiohttp.ClientTimeout(total=30)) as r:
            if r.status != 200:
                raise IgError(f"rasm HTTP {r.status}")
            data = await r.content.read(MAX_SOURCE_BYTES + 1)
    if len(data) > MAX_SOURCE_BYTES:
        raise IgError("rasm juda katta")
    return data


def prepare_jpeg(raw: bytes) -> bytes:
    """Har qanday rasm -> Instagram talabiga mos JPEG (RGB, nisbat 4:5 ... 1.91:1, kengligi 320-1440)."""
    from PIL import Image, ImageOps

    with Image.open(io.BytesIO(raw)) as src:
        img = ImageOps.exif_transpose(src)
        if img.mode in ("RGBA", "LA", "P"):
            img = img.convert("RGBA")
            bg = Image.new("RGB", img.size, PAD_COLOR)
            bg.paste(img, mask=img.getchannel("A"))
            img = bg
        else:
            img = img.convert("RGB")

    w, h = img.size
    ratio = w / h
    if ratio < MIN_RATIO:            # juda baland (telefon rasmi 3:4, 9:16) -> yon tomonlariga fon
        new_w, new_h = round(h * MIN_RATIO), h
    elif ratio > MAX_RATIO:          # juda keng (panorama) -> tepa-pastiga fon
        new_w, new_h = w, round(w / MAX_RATIO)
    else:
        new_w, new_h = w, h
    if (new_w, new_h) != (w, h):
        canvas = Image.new("RGB", (new_w, new_h), PAD_COLOR)
        canvas.paste(img, ((new_w - w) // 2, (new_h - h) // 2))
        img = canvas

    if img.width > MAX_WIDTH or img.width < MIN_WIDTH:
        target = MAX_WIDTH if img.width > MAX_WIDTH else MIN_WIDTH
        img = img.resize((target, round(img.height * target / img.width)), Image.LANCZOS)

    out = io.BytesIO()
    img.save(out, "JPEG", quality=90, optimize=True, progressive=True)
    return out.getvalue()


# ---------------------------------------------------------------- caption ---

def _money(price: Decimal | float | int, currency: str) -> str:
    n = f"{int(Decimal(price)):,}".replace(",", " ")
    return f"${n}" if currency == "USD" else f"{n} so'm"


def _tag(text: str | None) -> str | None:
    if not text:
        return None
    words = [w for w in re.split(r"\s+", text.lower())
             if w not in ("tumani", "tuman", "shahar", "shahri", "viloyati", "viloyat", "t.", "sh.")]
    tag = re.sub(r"[^a-z0-9]", "", "".join(words))
    return f"#{tag}" if len(tag) >= 3 else None


def build_caption(h) -> str:
    """E'londan Instagram post matni (o'zbekcha). Instagram'da havolalar bosilmaydi — bot nomi matnda."""
    period = "kun" if h["rent_period"] == "day" else "oy"
    lines = [f"🏠 {h['title'].strip()}", "", f"💰 {_money(h['price'], h['currency'])} / {period}"]

    facts = []
    if h["rooms"]:
        facts.append(f"🛏 {h['rooms']} xonali")
    if h["area"] is not None:
        facts.append(f"📐 {Decimal(h['area']).normalize():f} m²")
    if h["floor"]:
        facts.append(f"🏢 {h['floor']}/{h['floors']} qavat" if h["floors"] else f"🏢 {h['floor']}-qavat")
    if facts:
        lines.append(" · ".join(facts))

    address = (h["address"] or "").strip()
    district = (h["district"] or "").strip()
    place = address if (not district or district.lower() in address.lower()) else f"{district}, {address}"
    if place:
        lines.append(f"📍 {place}")

    link = f"t.me/{config.ig_bot_username}"
    tags = ["#arenda", "#ijara", "#ijarauy", "#kvartira", "#toshkent", "#аренда", "#ташкент", "#arendauz"]
    dtag = _tag(district)
    if dtag and dtag not in tags:
        tags.append(dtag)
    tail = ["", f"📲 Batafsil ma'lumot va uy egasi bilan bog'lanish — Telegram botimizda: {link}", "", " ".join(tags)]

    head = "\n".join(lines)
    desc = re.sub(r"\n{3,}", "\n\n", (h["description"] or "").strip())
    room = CAPTION_MAX - len(head) - len("\n".join(tail)) - 4
    if desc and room > 40:
        if len(desc) > min(room, 700):
            desc = desc[: min(room, 700) - 1].rstrip() + "…"
        head += "\n\n" + desc
    return (head + "\n" + "\n".join(tail))[:CAPTION_MAX]


# ------------------------------------------------------------- Graph API ---

async def _graph(session: aiohttp.ClientSession, method: str, path: str, **params: Any) -> dict:
    params["access_token"] = config.ig_access_token
    url = f"{GRAPH}/{config.ig_graph_version}/{path}"
    kw = {"params": params} if method == "GET" else {"data": params}
    async with session.request(method, url, timeout=aiohttp.ClientTimeout(total=60), **kw) as r:
        try:
            body = await r.json(content_type=None)
        except Exception:  # noqa: BLE001
            body = {}
    if r.status != 200 or "error" in body:
        err = body.get("error") or {}
        msg = err.get("error_user_msg") or err.get("message") or f"HTTP {r.status}"
        raise IgError(f"{path}: {msg} (code {err.get('code')}/{err.get('error_subcode')})"
                      .replace(config.ig_access_token, "***"))
    return body


async def _wait_ready(session: aiohttp.ClientSession, container_id: str, timeout: int = 90) -> None:
    deadline = time.monotonic() + timeout
    while True:
        st = (await _graph(session, "GET", container_id, fields="status_code,status")).get("status_code")
        if st == "FINISHED":
            return
        if st in ("ERROR", "EXPIRED"):
            raise IgError(f"konteyner {container_id}: {st}")
        if time.monotonic() > deadline:
            raise IgError(f"konteyner {container_id}: {timeout} s da tayyor bo'lmadi ({st})")
        await asyncio.sleep(3)


async def publish_house(h) -> dict[str, Any]:
    """Bitta e'lonni Instagram'ga chiqaradi va instagram_posts holatini yangilaydi.

    Bir e'lon ikki marta chiqmasligi uchun avval bazada «publishing» deb band qilinadi.
    """
    if not config.ig_enabled:
        raise IgError("IG_ACCESS_TOKEN / IG_ACCOUNT_ID sozlanmagan.")
    refs = photo_refs(h)
    if not refs:
        raise IgError("e'londa rasm yo'q (Instagram rasmsiz post qabul qilmaydi)")
    caption = build_caption(h)
    urls = [image_url(h["id"], i) for i in range(min(len(refs), MAX_CAROUSEL))]
    if not await db.ig_claim(h["id"], caption):
        raise IgError(f"#{h['id']} allaqachon chiqarilgan yoki hozir chiqarilmoqda")

    acc = config.ig_account_id
    container_id = None
    try:
        async with aiohttp.ClientSession() as s:
            if len(urls) == 1:
                container_id = (await _graph(s, "POST", f"{acc}/media", image_url=urls[0], caption=caption))["id"]
            else:
                children = []
                for u in urls:
                    cid = (await _graph(s, "POST", f"{acc}/media", image_url=u, is_carousel_item="true"))["id"]
                    await _wait_ready(s, cid)
                    children.append(cid)
                container_id = (await _graph(s, "POST", f"{acc}/media", media_type="CAROUSEL",
                                             children=",".join(children), caption=caption))["id"]
            await db.ig_update(h["id"], container_id=container_id)
            await _wait_ready(s, container_id)
            media_id = (await _graph(s, "POST", f"{acc}/media_publish", creation_id=container_id))["id"]
            try:
                permalink = (await _graph(s, "GET", media_id, fields="permalink")).get("permalink")
            except IgError:
                permalink = None
    except Exception as exc:
        await db.ig_update(h["id"], status="failed", error=str(exc)[:1000])
        log.warning("Instagram: #%s chiqmadi: %s", h["id"], exc)
        raise
    await db.ig_update(h["id"], status="published", media_id=media_id, permalink=permalink, error=None)
    log.info("Instagram: #%s chiqdi -> %s", h["id"], permalink or media_id)
    return {"house_id": h["id"], "media_id": media_id, "permalink": permalink, "photos": len(urls)}


async def run_once(limit: int | None = None) -> list[dict[str, Any]]:
    """Avtopost: hali chiqmagan eng yangi e'lonlardan `limit` tasini chiqaradi."""
    houses = await db.ig_candidates(config.ig_sources, config.ig_max_age_days, limit or config.ig_posts_per_run)
    out = []
    for h in houses:
        try:
            out.append(await publish_house(h))
        except Exception as exc:  # noqa: BLE001 — xato bazaga yozilgan
            out.append({"house_id": h["id"], "error": str(exc)[:300]})
    return out


async def _loop(interval_min: int) -> None:
    await asyncio.sleep(60)  # bot va server to'liq ko'tarilsin (Instagram rasmni shu serverdan oladi)
    while True:
        try:
            await run_once()
        except Exception:  # noqa: BLE001
            log.exception("Instagram avtopost xatosi")
        await asyncio.sleep(interval_min * 60)


def start_background() -> None:
    global _task
    if not (config.ig_autopost and config.ig_enabled):
        log.info("Instagram avtopost o'chiq (IG_AUTOPOST=1 va IG_ACCESS_TOKEN/IG_ACCOUNT_ID kerak).")
        return
    if not config.public_base_url:
        log.warning("Instagram avtopost: ochiq server manzili yo'q (WEBAPP_URL/PUBLIC_BASE_URL) — o'chiq.")
        return
    _task = asyncio.create_task(_loop(config.ig_interval_min), name="instagram-autopost")
    log.info("Instagram avtopost har %s daqiqada, manbalar: %s.", config.ig_interval_min, ", ".join(config.ig_sources))


async def stop_background() -> None:
    if _task is not None and not _task.done():
        _task.cancel()
        try:
            await _task
        except (asyncio.CancelledError, Exception):  # noqa: BLE001
            pass
