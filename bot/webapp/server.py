"""Mini App HTTP server (aiohttp): admin panel + market (klient) sahifalari va JSON API.

Autentifikatsiya: Telegram Web App `initData` (HMAC-SHA256, bot tokeni bilan tekshiriladi).
  /api/*         — faqat ADMIN_IDS
  /api/market/*  — har qanday bloklanmagan foydalanuvchi (ro'yxatdan o'tgan bo'lishi kerak)
  /api/photo/*   — har qanday haqiqiy initData
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import re
import time
from collections import OrderedDict
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl

from aiogram import Bot
from aiogram.types import BufferedInputFile
from aiogram.utils.web_app import safe_parse_webapp_init_data
from aiohttp import web

from bot import db, sync
from bot.config import config

log = logging.getLogger("webapp")

STATIC_DIR = Path(__file__).resolve().parent / "static"
INIT_DATA_MAX_AGE = 60 * 60 * 12  # 12 soat
MAX_PHOTOS = 8
MAX_PHOTO_BYTES = 10 * 1024 * 1024
PHONE_RE = re.compile(r"^\+998\d{9}$")

# file_id -> bytes (rasm proksi uchun kichik kesh)
_photo_cache: "OrderedDict[str, bytes]" = OrderedDict()
_PHOTO_CACHE_MAX = 300


# ------------------------------------------------------------------ auth ---

def _extract_init_data(request: web.Request) -> str | None:
    auth = request.headers.get("Authorization", "")
    if auth.startswith("tma "):
        return auth[4:].strip()
    return request.query.get("_auth") or None  # <img src> uchun


def _tg_secret() -> bytes:
    return hmac.new(b"WebAppData", config.bot_token.encode(), hashlib.sha256).digest()


def verify_tg_signed(raw: str) -> dict[str, str]:
    """Telegram imzolagan ixtiyoriy querystring'ni (masalan requestContact javobi) tekshiradi."""
    fields = dict(parse_qsl(raw, keep_blank_values=True))
    given = fields.pop("hash", None)
    if not given:
        raise ValueError("hash yo'q")
    dcs = "\n".join(f"{k}={v}" for k, v in sorted(fields.items()))
    calc = hmac.new(_tg_secret(), dcs.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(calc, given):
        raise ValueError("imzo mos emas")
    return fields


@web.middleware
async def auth_middleware(request: web.Request, handler):
    if not request.path.startswith("/api/"):
        return await handler(request)

    raw = _extract_init_data(request)
    if not raw:
        raise web.HTTPUnauthorized(text="initData yo'q. Sahifani Telegram orqali oching.")
    try:
        data = safe_parse_webapp_init_data(config.bot_token, raw)
    except ValueError:
        raise web.HTTPUnauthorized(text="initData noto'g'ri yoki buzilgan.")
    if data.auth_date and time.time() - data.auth_date.timestamp() > INIT_DATA_MAX_AGE:
        raise web.HTTPUnauthorized(text="Sessiya eskirgan. Mini App'ni qayta oching.")
    if data.user is None:
        raise web.HTTPUnauthorized(text="Foydalanuvchi aniqlanmadi.")

    request["tg_user"] = data.user
    is_admin = data.user.id in config.admin_ids
    request["is_admin"] = is_admin

    if request.path.startswith("/api/market/"):
        name = " ".join(p for p in (data.user.first_name, data.user.last_name) if p)
        row = await db.upsert_user(data.user.id, name, data.user.username)
        if row["is_blocked"] and not is_admin:
            raise web.HTTPForbidden(text="Siz botdan foydalanishdan bloklangansiz.")
        request["db_user"] = row
    elif request.path.startswith("/api/photo/"):
        pass
    elif not is_admin:
        raise web.HTTPForbidden(text="Siz admin emassiz.")

    return await handler(request)


# --------------------------------------------------------------- helpers ---

def _photo_url(ref: str) -> str:
    """photo_urls elementini klient ochadigan URL ga aylantiradi (tg:FILE_ID -> /api/photo/...)."""
    if ref.startswith("tg:"):
        return "/api/photo/" + ref[3:]
    return ref


def _house_json(h, *, public: bool = False) -> dict[str, Any]:
    photos = [_photo_url(p) for p in (h["photo_urls"] or [])]
    if not photos and h["photo_file_id"]:
        photos = [_photo_url("tg:" + h["photo_file_id"])]
    d: dict[str, Any] = {
        "id": h["id"],
        "title": h["title"],
        "address": h["address"],
        "district": h["district"],
        "rooms": h["rooms"],
        "area": float(h["area"]) if h["area"] is not None else None,
        "floor": h["floor"],
        "floors": h["floors"],
        "price": float(h["price"]),
        "currency": h["currency"],
        "price_uzs": float(h["price_uzs"]) if h["price_uzs"] is not None else None,
        "description": h["description"],
        "photos": photos,
        "contact_phone": h["contact_phone"],
        "seller_name": h["seller_name"],
        "seller_username": h["seller_username"],
        "source": h["source"],
        "source_url": h["source_url"],
        "lat": h["lat"],
        "lon": h["lon"],
        "views": h["views"],
        "is_favorite": h["is_favorite"],
        "is_active": h["is_active"],
        "published_at": (h["external_created_at"] or h["created_at"]).isoformat(),
        "created_at": h["created_at"].isoformat(),
    }
    if not public:
        d["admin_hidden"] = h["admin_hidden"]
        d["last_seen_at"] = h["last_seen_at"].isoformat() if h["last_seen_at"] else None
    return d


def _user_json(u) -> dict[str, Any]:
    return {
        "telegram_id": u["telegram_id"],
        "full_name": u["full_name"],
        "username": u["username"],
        "phone": u["phone"],
        "role": u["role"],
        "registered": u["registered_at"] is not None,
        "is_blocked": u["is_blocked"],
        "block_reason": u["block_reason"],
        "created_at": u["created_at"].isoformat(),
    }


def _bad(msg: str) -> web.HTTPBadRequest:
    return web.HTTPBadRequest(text=msg)


def _cache_put(file_id: str, content: bytes) -> None:
    _photo_cache[file_id] = content
    _photo_cache.move_to_end(file_id)
    while len(_photo_cache) > _PHOTO_CACHE_MAX:
        _photo_cache.popitem(last=False)


# ----------------------------------------------------------- pages/static ---

async def index(request: web.Request) -> web.FileResponse:
    return web.FileResponse(STATIC_DIR / "index.html")


async def market_page(request: web.Request) -> web.FileResponse:
    return web.FileResponse(STATIC_DIR / "market.html")


async def api_photo(request: web.Request) -> web.Response:
    """Telegram file_id bo'yicha rasmni proksilaydi (admin yuklagan rasmlar uchun)."""
    file_id = request.match_info["file_id"]
    content = _photo_cache.get(file_id)
    if content is None:
        bot: Bot = request.app["bot"]
        try:
            tg_file = await bot.get_file(file_id)
            buf = await bot.download_file(tg_file.file_path)
            content = buf.read()
        except Exception as exc:  # noqa: BLE001
            log.warning("Rasm yuklanmadi %s: %s", file_id, exc)
            raise web.HTTPNotFound(text="Rasm topilmadi.")
        _cache_put(file_id, content)
    return web.Response(body=content, content_type="image/jpeg",
                        headers={"Cache-Control": "private, max-age=86400"})


# ------------------------------------------------------------- admin API ---

async def api_me(request: web.Request) -> web.Response:
    u = request["tg_user"]
    name = " ".join(p for p in (u.first_name, u.last_name) if p)
    return web.json_response({"id": u.id, "name": name, "username": u.username})


async def api_stats(request: web.Request) -> web.Response:
    s = await db.stats()
    s["sync_running"] = sync.is_running()
    s["sync_interval_min"] = config.sync_interval_min
    return web.json_response(s)


async def api_sync(request: web.Request) -> web.Response:
    """Joymee bilan hoziroq sinxronlash (admin tugmasi)."""
    if sync.is_running():
        raise web.HTTPConflict(text="Sinxronlash allaqachon ketmoqda.")
    try:
        res = await sync.run_once()
    except Exception as exc:  # noqa: BLE001
        raise web.HTTPBadGateway(text=f"Joymee bilan bog'lanib bo'lmadi: {exc}")
    return web.json_response(res)


async def api_houses(request: web.Request) -> web.Response:
    source = request.query.get("source") or None
    houses = await db.list_houses(offset=0, limit=400, only_active=False, source=source,
                                  viewer_id=request["tg_user"].id)
    return web.json_response([_house_json(h) for h in houses])


async def api_house_add(request: web.Request) -> web.Response:
    """multipart/form-data: title, address, district, rooms, price, description, contact_phone, photos[]."""
    form = await request.post()
    title = str(form.get("title", "")).strip()[:120]
    address = str(form.get("address", "")).strip()[:250]
    district = str(form.get("district", "")).strip()[:80] or None
    description = str(form.get("description", "")).strip()[:1500]
    contact_phone = str(form.get("contact_phone", "")).strip()[:30] or None
    if not title or not address:
        raise _bad("Nom va manzil majburiy.")
    try:
        rooms = int(str(form.get("rooms", "")).strip())
        if not 1 <= rooms <= 50:
            raise ValueError
    except ValueError:
        raise _bad("Xonalar soni 1..50 oralig'ida bo'lsin.")
    try:
        price = Decimal(str(form.get("price", "")).replace(" ", "").replace(",", "."))
        if price < 0 or price > Decimal("999999999999"):
            raise InvalidOperation
    except InvalidOperation:
        raise _bad("Narx noto'g'ri.")

    bot: Bot = request.app["bot"]
    files = [f for f in form.getall("photos", []) if isinstance(f, web.FileField) and f.filename]
    single = form.get("photo")
    if isinstance(single, web.FileField) and single.filename:
        files.insert(0, single)
    if len(files) > MAX_PHOTOS:
        raise _bad(f"Ko'pi bilan {MAX_PHOTOS} ta rasm.")
    file_ids: list[str] = []
    for i, f in enumerate(files):
        content = f.file.read()
        if not content:
            continue
        if len(content) > MAX_PHOTO_BYTES:
            raise _bad("Rasm 10 MB dan katta.")
        msg = await bot.send_photo(
            chat_id=request["tg_user"].id,
            photo=BufferedInputFile(content, filename=f.filename or f"photo{i}.jpg"),
            caption=f"📎 Mini App orqali yuklandi: {title}" if i == 0 else None,
            disable_notification=True,
        )
        fid = msg.photo[-1].file_id
        file_ids.append(fid)
        _cache_put(fid, content)

    house_id = await db.add_house(
        title=title, address=address, rooms=rooms, price=price, description=description,
        photo_file_id=None, contact_phone=contact_phone, created_by=request["tg_user"].id,
        district=district, photo_file_ids=file_ids,
    )
    return web.json_response(_house_json(await db.get_house(house_id)), status=201)


async def api_house_delete(request: web.Request) -> web.Response:
    house_id = int(request.match_info["id"])
    house = await db.get_house(house_id)
    if house is None:
        raise web.HTTPNotFound(text="Uy topilmadi.")
    if house["source"] != "admin":
        # Tashqi e'lon: o'chirsak sinx qayta qo'shadi — shuning uchun doimiy yashiramiz
        await db.set_house_active(house_id, False)
        return web.json_response({"ok": True, "hidden": True})
    await db.delete_house(house_id)
    return web.json_response({"ok": True})


async def api_house_patch(request: web.Request) -> web.Response:
    house_id = int(request.match_info["id"])
    body = await request.json()
    if "is_active" not in body:
        raise _bad("is_active kerak.")
    if not await db.set_house_active(house_id, bool(body["is_active"])):
        raise web.HTTPNotFound(text="Uy topilmadi.")
    return web.json_response(_house_json(await db.get_house(house_id)))


async def api_users(request: web.Request) -> web.Response:
    q = request.query.get("q", "").strip() or None
    blocked_raw = request.query.get("blocked")
    blocked = None if blocked_raw in (None, "", "all") else blocked_raw == "1"
    page = max(0, int(request.query.get("page", "0") or 0))
    per_page = 50
    users = await db.list_users(offset=page * per_page, limit=per_page, blocked=blocked, q=q)
    return web.json_response({"items": [_user_json(u) for u in users], "page": page, "per_page": per_page})


async def api_user_block(request: web.Request) -> web.Response:
    tg_id = int(request.match_info["id"])
    if tg_id == request["tg_user"].id:
        raise _bad("O'zingizni bloklay olmaysiz.")
    body = await request.json() if request.can_read_body else {}
    reason = (body.get("reason") or "").strip()[:300] or "Admin tomonidan bloklangan"
    if not await db.block_user(tg_id, reason):
        raise web.HTTPNotFound(text="Klient topilmadi.")
    return web.json_response(_user_json(await db.get_user(tg_id)))


async def api_user_unblock(request: web.Request) -> web.Response:
    tg_id = int(request.match_info["id"])
    if not await db.unblock_user(tg_id):
        raise web.HTTPNotFound(text="Klient topilmadi.")
    return web.json_response(_user_json(await db.get_user(tg_id)))


# ------------------------------------------------------------ market API ---

def _require_registered(request: web.Request) -> None:
    if request["db_user"]["registered_at"] is None and not request["is_admin"]:
        raise web.HTTPForbidden(text="Avval ro'yxatdan o'ting.")


def _dec(v: str | None) -> Decimal | None:
    if not v:
        return None
    try:
        return Decimal(v.replace(" ", ""))
    except InvalidOperation:
        raise _bad("Narx noto'g'ri.")


async def m_me(request: web.Request) -> web.Response:
    u = request["db_user"]
    tg = request["tg_user"]
    return web.json_response({
        **_user_json(u),
        "tg_name": " ".join(p for p in (tg.first_name, tg.last_name) if p),
        "is_admin": request["is_admin"],
        "usd_rate": config.usd_rate,
    })


async def m_register(request: web.Request) -> web.Response:
    """{full_name, role, phone | contact_response}"""
    body = await request.json()
    full_name = str(body.get("full_name", "")).strip()[:100]
    role = body.get("role")
    if len(full_name) < 2:
        raise _bad("Ismingizni kiriting.")
    if role not in ("tenant", "landlord"):
        raise _bad("Kimligingizni tanlang: ijarachi yoki uy egasi.")

    if body.get("contact_response"):
        # Telegram requestContact() javobi — imzosi tekshiriladi, raqamni qo'lda o'zgartirib bo'lmaydi
        try:
            fields = verify_tg_signed(str(body["contact_response"]))
            contact = json.loads(fields.get("contact", "{}"))
            if int(contact.get("user_id", 0)) != request["tg_user"].id:
                raise ValueError("boshqa foydalanuvchi kontakti")
            phone = "+" + re.sub(r"\D", "", str(contact.get("phone_number", "")))
        except (ValueError, KeyError, json.JSONDecodeError) as exc:
            raise _bad(f"Kontakt tasdiqlanmadi: {exc}")
    else:
        digits = re.sub(r"\D", "", str(body.get("phone", "")))
        if len(digits) == 9:
            digits = "998" + digits
        phone = "+" + digits
    if not PHONE_RE.match(phone):
        raise _bad("Telefon raqam +998XXXXXXXXX ko'rinishida bo'lsin.")

    u = await db.complete_registration(request["tg_user"].id, full_name, phone, role)
    return web.json_response(_user_json(u))


async def m_houses(request: web.Request) -> web.Response:
    _require_registered(request)
    q = request.query
    rooms_raw = q.get("rooms")
    page = max(0, int(q.get("page", "0") or 0))
    per_page = 20
    rows = await db.market_houses(
        viewer_id=request["tg_user"].id,
        q=q.get("q", "").strip() or None,
        rooms=int(rooms_raw) if rooms_raw and rooms_raw.isdigit() else None,
        price_min=_dec(q.get("price_min")),
        price_max=_dec(q.get("price_max")),
        district=q.get("district", "").strip() or None,
        source=q.get("source", "").strip() or None,
        sort=q.get("sort", "new"),
        offset=page * per_page,
        limit=per_page,
    )
    return web.json_response({"items": [_house_json(h, public=True) for h in rows],
                              "page": page, "per_page": per_page, "has_more": len(rows) == per_page})


async def m_house(request: web.Request) -> web.Response:
    _require_registered(request)
    house_id = int(request.match_info["id"])
    h = await db.get_house(house_id, viewer_id=request["tg_user"].id)
    if h is None or not (h["is_active"] and not h["admin_hidden"]):
        raise web.HTTPNotFound(text="E'lon topilmadi yoki yopilgan.")
    await db.increment_views(house_id)
    return web.json_response(_house_json(h, public=True))


async def m_districts(request: web.Request) -> web.Response:
    return web.json_response(await db.districts())


async def m_favorite_toggle(request: web.Request) -> web.Response:
    _require_registered(request)
    house_id = int(request.match_info["id"])
    if await db.get_house(house_id) is None:
        raise web.HTTPNotFound(text="E'lon topilmadi.")
    fav = await db.toggle_favorite(request["tg_user"].id, house_id)
    return web.json_response({"is_favorite": fav})


async def m_favorites(request: web.Request) -> web.Response:
    _require_registered(request)
    rows = await db.list_favorites(request["tg_user"].id)
    return web.json_response([_house_json(h, public=True) for h in rows])


# ------------------------------------------------------------------- app ---

def create_app(bot: Bot) -> web.Application:
    app = web.Application(middlewares=[auth_middleware],
                          client_max_size=MAX_PHOTOS * MAX_PHOTO_BYTES + 1024 * 1024)
    app["bot"] = bot
    app.add_routes([
        web.get("/", index),
        web.get("/market", market_page),
        web.get("/api/photo/{file_id}", api_photo),
        # admin
        web.get("/api/me", api_me),
        web.get("/api/stats", api_stats),
        web.post("/api/sync", api_sync),
        web.get("/api/houses", api_houses),
        web.post("/api/houses", api_house_add),
        web.delete("/api/houses/{id:\\d+}", api_house_delete),
        web.patch("/api/houses/{id:\\d+}", api_house_patch),
        web.get("/api/users", api_users),
        web.post("/api/users/{id:\\d+}/block", api_user_block),
        web.post("/api/users/{id:\\d+}/unblock", api_user_unblock),
        # market
        web.get("/api/market/me", m_me),
        web.post("/api/market/register", m_register),
        web.get("/api/market/houses", m_houses),
        web.get("/api/market/houses/{id:\\d+}", m_house),
        web.get("/api/market/districts", m_districts),
        web.post("/api/market/favorites/{id:\\d+}", m_favorite_toggle),
        web.get("/api/market/favorites", m_favorites),
    ])
    app.router.add_static("/static/", STATIC_DIR, show_index=False)
    return app


async def start_server(bot: Bot) -> web.AppRunner:
    runner = web.AppRunner(create_app(bot), access_log=None)
    await runner.setup()
    site = web.TCPSite(runner, host=config.webapp_host, port=config.webapp_port)
    await site.start()
    log.info("Mini App server: http://%s:%s", config.webapp_host, config.webapp_port)
    return runner
