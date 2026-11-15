"""Qayoda (qayoda.uz) dan Toshkent va atrofi ijara e'lonlarini tortish — faqat katalog sahifalaridan.

Qayoda — agregator (Uybor, Realt24, Joymee, OLX va boshq.). robots.txt ochiq katalog sahifalarini
ruxsat etadi, /api/, qidiruv (/poisk) va kabinetni yopadi, Crawl-delay: 10 talab qiladi.

Nega faqat katalog: e'lon tafsilot sahifalari server (Render) IP'laridan HTTP 403 qaytaradi.
Bu cheklovni aylanib o'tmaymiz — kerakli ma'lumot katalog kartasining o'zida bor:
  narx (у.е. / сум, oyiga / kuniga), turi, xonalar, maydon, qavat, sarlavha, joy, sana, 1-rasm.
Tavsif va asl manba kartada yo'q — «Bog'lanish ↗» qayoda'dagi e'lon sahifasini ochadi
(foydalanuvchi brauzeridan ochiladi).

Qoidalar: faqat /ru/arenda/... va /ru/posutochno/... katalog sahifalari, har so'rov orasida 10.5 s.
Joymee/Uybor'dan to'g'ridan-to'g'ri olingan e'lonlarning nusxalari (xona + maydon + narx mos) o'tkazib yuboriladi.
"""
from __future__ import annotations

import asyncio
import html as html_lib
import logging
import re
import time
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

import aiohttp

from bot import db
from bot.areas import area_or_default
from bot.config import config

log = logging.getLogger("scraper.qayoda")

SOURCE = "qayoda"
BASE = "https://qayoda.uz"
HEADERS = {"User-Agent": "ArendaUzBot/1.0 (student project; Telegram @chirchiqarenda_bot)"}
CRAWL_DELAY = 10.5      # robots.txt: Crawl-delay: 10

# (katalog yo'li, ijara turi)
SECTIONS = (("arenda", "month"), ("posutochno", "day"))

# Turar joy bo'lmagan e'lonlar (slug bo'yicha)
_SKIP_SLUG = ("tijorat", "yer-uchastka", "ofis", "ombor", "dokon", "biznes", "ishlab-chiqarish", "bino-")
_SKIP_TYPE = ("Коммерческ", "Участок", "Офис", "Склад", "Бизнес", "Помещение")

_ARTICLE_RE = re.compile(r'<article data-impression="(\d+)"(.*?)</article>', re.S)
_HREF_RE = re.compile(r'href="(/ru/obyavlenie/([a-z0-9-]+)-(\d+))"')
_PRICE_RE = re.compile(r'<p class="font-bold[^"]*">\s*([^<]+?)\s*<span[^>]*>\s*(?:<!-- -->)?\s*([^<]*)</span>')
_H3_RE = re.compile(r'<h3[^>]*>.*?<a[^>]*>([^<]*)<span[^>]*>\s*·\s*(?:<!-- -->)?([^<]*)</span>', re.S)
_SR_RE = re.compile(r'<span class="sr-only">([^<]+)</span>')
_PLACE_RE = re.compile(r'<p class="truncate">([^<]+)</p>\s*<time dateTime="([^"]+)"')
_IMG_RE = re.compile(r'\ssrc="(/img/[^"]+)"')

_last_request = 0.0


class QayodaError(RuntimeError):
    pass


async def _get(session: aiohttp.ClientSession, path: str) -> str:
    """Crawl-delay ga rioya qilib sahifani oladi."""
    global _last_request
    wait = CRAWL_DELAY - (time.monotonic() - _last_request)
    if wait > 0:
        await asyncio.sleep(wait)
    _last_request = time.monotonic()
    async with session.get(BASE + path, timeout=aiohttp.ClientTimeout(total=40)) as r:
        if r.status != 200:
            raise QayodaError(f"{path} -> HTTP {r.status}")
        return await r.text()


def _num(s: str) -> Decimal | None:
    s = s.replace(" ", " ").replace(" ", " ").strip()
    m = re.search(r"[\d\s]+(?:[.,]\d+)?", s)
    if not m:
        return None
    try:
        return Decimal(m.group(0).replace(" ", "").replace(",", "."))
    except InvalidOperation:
        return None


def parse_price(text: str) -> tuple[Decimal, str] | None:
    """'58 у.е.' -> (58, USD); '600 тыс. сум' -> (600000, UZS); '1,2 млн сум' -> (1200000, UZS)."""
    t = html_lib.unescape(text).lower()
    n = _num(t)
    if n is None:
        return None
    if "у.е" in t or "$" in t:
        return n, "USD"
    if "млн" in t:
        n *= 1_000_000
    elif "тыс" in t:
        n *= 1_000
    return n, "UZS"


def parse_cards(page_html: str, rent_period: str) -> dict[str, dict[str, Any]]:
    """Katalog sahifasidagi kartalar: qayoda_id -> houses maydonlari. Turar joy bo'lmaganlar tashlanadi."""
    out: dict[str, dict[str, Any]] = {}
    for qid, body in _ARTICLE_RE.findall(page_html):
        href = _HREF_RE.search(body)
        if not href:
            continue
        path, slug = href.group(1), href.group(2)
        if any(k in slug for k in _SKIP_SLUG):
            continue
        h3 = _H3_RE.search(body)
        kind = html_lib.unescape(h3.group(1)).strip() if h3 else ""
        params = html_lib.unescape(h3.group(2)).strip() if h3 else ""
        if any(k in kind for k in _SKIP_TYPE):
            continue
        pm = _PRICE_RE.search(body)
        price = parse_price(pm.group(1)) if pm else None
        if price is None:
            continue
        unit = html_lib.unescape(pm.group(2)).lower()
        period = "day" if ("сут" in unit or "день" in unit or "ночь" in unit) else rent_period

        rooms = re.search(r"(\d+)\s*комн", params)
        area = re.search(r"([\d]+(?:[.,]\d+)?)\s*м²", params)
        floors = re.search(r"(\d+)\s*/\s*(\d+)\s*эт", params)
        sr = _SR_RE.search(body)
        title = html_lib.unescape(sr.group(1)).strip() if sr else (f"{kind} · {params}".strip(" ·") or "E'lon")
        title = re.sub(r"\s+—\s+[^—]+$", "", title)
        place = _PLACE_RE.search(body)
        place_text = html_lib.unescape(place.group(1)).strip() if place else ""
        try:
            posted = datetime.fromisoformat(place.group(2).replace("Z", "+00:00")) if place else None
        except ValueError:
            posted = None
        img = _IMG_RE.search(body)
        owner = "Собственник" in body

        out[qid] = {
            "rent_period": period,
            "title": title[:200],
            "address": place_text or "Toshkent",
            "rooms": int(rooms.group(1)) if rooms and 0 < int(rooms.group(1)) <= 50 else None,
            "price": price[0],
            "currency": price[1],
            "description": "\n".join(p for p in (f"{kind} · {params}".strip(" ·"), "Uy egasidan" if owner else "") if p),
            "contact_phone": None,
            "district": area_or_default("Toshkent shahri" if "Ташкент" in place_text and "област" not in place_text
                                        else "Toshkent viloyati", place_text, title),
            "area": Decimal(area.group(1).replace(",", ".")) if area else None,
            "floor": int(floors.group(1)) if floors else None,
            "floors": int(floors.group(2)) if floors else None,
            "photo_urls": [BASE + img.group(1)] if img else [],
            "seller_name": None,
            "seller_username": None,
            "lat": None,
            "lon": None,
            "external_created_at": posted,
            "source_url": BASE + path,       # «Bog'lanish ↗» shu sahifani ochadi
            "views": 0,
        }
    return out


def _is_duplicate(d: dict[str, Any], others: list[tuple]) -> bool:
    """Joymee/Uybor'dagi e'lon bilan bir xilmi: ijara turi, xona, maydon (±1 m²) va narx (±3%) mos."""
    if d["area"] is None:
        return False
    price_uzs = db.to_uzs(d["price"], d["currency"])
    for period, rooms, area, other_uzs in others:
        if period != d["rent_period"] or rooms != d["rooms"] or area is None or other_uzs is None:
            continue
        if abs(Decimal(area) - d["area"]) <= 1 and abs(Decimal(other_uzs) - price_uzs) <= price_uzs * Decimal("0.03"):
            return True
    return False


async def sync() -> dict[str, int]:
    """Qayoda katalogi bilan sinxronlash. Natija: added/updated/deactivated/seen (+skipped_dupes)."""
    log_id = await db.sync_started(SOURCE)
    added = updated = deactivated = skipped = 0
    cards: dict[str, dict[str, Any]] = {}
    try:
        async with aiohttp.ClientSession(headers=HEADERS) as session:
            for city_path in config.qayoda_cities:
                for section, period in SECTIONS:
                    for page in range(1, config.qayoda_max_pages + 1):
                        q = f"/ru/{section}/{city_path}" + (f"?page={page}" if page > 1 else "")
                        try:
                            page_html = await _get(session, q)
                        except QayodaError as exc:
                            if "404" in str(exc):
                                break
                            raise
                        found = parse_cards(page_html, period)
                        new = {k: v for k, v in found.items() if k not in cards}
                        cards.update(new)
                        if not new or f"page={page + 1}" not in page_html:
                            break

        others = [(r["rent_period"], r["rooms"], r["area"], r["price_uzs"]) for r in await db.pool().fetch(
            "SELECT rent_period, rooms, area, price_uzs FROM houses "
            "WHERE source IN ('joymee', 'uybor') AND is_active")]
        seen_ids: list[str] = []
        for qid, d in cards.items():
            if _is_duplicate(d, others):
                skipped += 1
                continue
            _, inserted = await db.upsert_external_house(SOURCE, qid, d)
            seen_ids.append(qid)
            added += int(inserted)
            updated += int(not inserted)

        await db.touch_seen(SOURCE, seen_ids)
        # Katalog bo'sh qaytsa (sayt o'zgargan / vaqtinchalik xato) — e'lonlarni yopmaymiz
        deactivated = await db.deactivate_missing(SOURCE, seen_ids) if seen_ids else 0
        note = None if cards else "katalogda e'lon topilmadi (sahifa tuzilishi o'zgargan bo'lishi mumkin)"
        await db.sync_finished(log_id, added=added, updated=updated, deactivated=deactivated,
                               seen=len(seen_ids), error=note)
        log.info("Qayoda sinx: kartalar %s, yangi %s, yangilandi %s, takror %s, yopildi %s",
                 len(cards), added, updated, skipped, deactivated)
    except Exception as exc:  # noqa: BLE001
        log.exception("Qayoda sinx xatosi")
        await db.sync_finished(log_id, added=added, updated=updated, deactivated=deactivated,
                               seen=len(cards), error=str(exc)[:500])
        raise
    return {"added": added, "updated": updated, "deactivated": deactivated,
            "seen": len(cards), "skipped_dupes": skipped}
