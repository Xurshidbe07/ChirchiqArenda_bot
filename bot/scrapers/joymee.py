"""Joymee (joymee.uz) dan Chirchiq ijara e'lonlarini tortish.

Joymee'ning ochiq JSON API'si ishlatiladi (saytning o'zi ham shu API bilan ishlaydi):
  GET https://api.joymee.uz/api/v1/announcement/?deal_type=2&district=166&ordering=newest&page=N
  GET https://api.joymee.uz/api/v1/announcement/{id}/

deal_type: 1 = kunlik ijara, 2 = ijara, 3 = sotuv.
district 166 = Chirchiq shahar (150 Yuqorichirchiq, 156 O'rtachirchiq, 147 Quyichirchiq).
category: 4 Kvartira, 5 Uy/dacha, 6 Tijorat, 7 Yer.

Hurmat qoidalari: so'rovlar orasida pauza, o'zgarmagan e'lonlar qayta yuklanmaydi,
robots.txt ruxsat bergan ochiq sahifalar ishlatiladi.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

import aiohttp

from bot import db
from bot.config import config

log = logging.getLogger("scraper.joymee")

SOURCE = "joymee"
API = "https://api.joymee.uz/api/v1/"
HEADERS = {
    "User-Agent": "ChirchiqArendaBot/1.0 (student project; Telegram @chirchiqarenda_bot)",
    "Accept": "application/json",
    "Origin": "https://joymee.uz",
    "Referer": "https://joymee.uz/",
}
PER_PAGE = 50
MAX_PAGES = 20
PAUSE = 0.4  # soniya, so'rovlar orasida


class JoymeeError(RuntimeError):
    pass


async def _get(session: aiohttp.ClientSession, path: str) -> Any:
    async with session.get(API + path, timeout=aiohttp.ClientTimeout(total=30)) as r:
        if r.status != 200:
            raise JoymeeError(f"{path} -> HTTP {r.status}")
        return await r.json(content_type=None)


def _dec(v: Any) -> Decimal | None:
    if v in (None, ""):
        return None
    try:
        return Decimal(str(v))
    except InvalidOperation:
        return None


def _dt(v: str | None) -> datetime | None:
    if not v:
        return None
    try:
        return datetime.fromisoformat(v)
    except ValueError:
        return None


def map_detail(det: dict[str, Any]) -> dict[str, Any]:
    """Joymee tafsilot javobini bizning houses maydonlariga o'giradi."""
    pricing = det.get("pricing") or {}
    price = _dec(pricing.get("price")) or _dec(pricing.get("price_from")) or Decimal(0)
    currency = "USD" if "y.e" in str(pricing.get("currency_display", "")).lower() or pricing.get("currency") == 2 else "UZS"
    d = det.get("detail") or {}
    media = sorted(det.get("media") or [], key=lambda m: (not m.get("is_cover"), m.get("order", 0)))
    photos = [m["file"]["url"] for m in media if m.get("file") and m["file"].get("url")]
    seller = det.get("seller") or {}
    loc = det.get("location") or {}
    rooms = d.get("room_quantity")
    try:
        rooms = int(rooms) if rooms else None
    except (TypeError, ValueError):
        rooms = None
    floor = d.get("floor_number")
    floors = d.get("floors_count")
    district = (det.get("district") or {}).get("name") or None
    region = (det.get("region") or {}).get("name") or ""
    address = det.get("address_line") or ", ".join(p for p in (region, district) if p)
    stats = det.get("stats") or {}
    return {
        "title": (det.get("title") or "E'lon").strip()[:200],
        "address": address.strip()[:250],
        "rooms": rooms if rooms and 0 < rooms <= 50 else None,
        "price": price,
        "currency": currency,
        "description": (det.get("description") or "").strip()[:4000],
        "contact_phone": det.get("phone_number") or None,
        "district": district,
        "area": _dec(d.get("area_m2")),
        "floor": int(floor) if isinstance(floor, int) else None,
        "floors": int(floors) if isinstance(floors, int) else None,
        "photo_urls": photos[:12],
        "seller_name": " ".join(p for p in (seller.get("first_name"), seller.get("last_name")) if p) or None,
        "seller_username": seller.get("username") or None,
        "lat": loc.get("latitude"),
        "lon": loc.get("longitude"),
        "external_created_at": _dt(det.get("ads_at")),
        "source_url": f"https://joymee.uz/announcements/{det['id']}",
        "views": int(stats.get("views") or 0),
    }


async def fetch_listing_ids(session: aiohttp.ClientSession) -> dict[str, dict[str, Any]]:
    """Barcha sahifalardan e'lon qisqa ma'lumotlarini yig'adi: source_id -> listing item."""
    found: dict[str, dict[str, Any]] = {}
    for district in config.joymee_districts:
        page = 1
        while page <= MAX_PAGES:
            data = await _get(
                session,
                f"announcement/?deal_type=2&district={district}&ordering=newest&page={page}&perPagePlain={PER_PAGE}",
            )
            for item in data.get("results") or []:
                found[str(item["id"])] = item
            if page >= int(data.get("total_pages") or 1):
                break
            page += 1
            await asyncio.sleep(PAUSE)
    return found


async def sync() -> dict[str, int]:
    """Joymee bilan to'liq sinxronlash. Natija: added/updated/deactivated/seen."""
    log_id = await db.sync_started(SOURCE)
    added = updated = deactivated = 0
    seen_ids: list[str] = []
    try:
        async with aiohttp.ClientSession(headers=HEADERS) as session:
            listing = await fetch_listing_ids(session)
            existing = await db.external_snapshot(SOURCE)
            seen_ids = list(listing.keys())

            for sid, item in listing.items():
                price_now = _dec((item.get("pricing") or {}).get("price"))
                title_now = (item.get("title") or "").strip()[:200]
                if sid in existing and existing[sid][0] == price_now and existing[sid][1] == title_now:
                    continue  # o'zgarmagan — tafsilotni qayta yuklamaymiz
                await asyncio.sleep(PAUSE)
                try:
                    det = await _get(session, f"announcement/{sid}/")
                except JoymeeError as exc:
                    log.warning("Tafsilot olinmadi %s: %s", sid, exc)
                    continue
                if det.get("category") not in config.joymee_categories:
                    seen_ids.remove(sid)  # tijorat/yer kabi keraksiz turkum — bizda bo'lmasin
                    continue
                data = map_detail(det)
                _, inserted = await db.upsert_external_house(SOURCE, sid, data)
                if inserted:
                    added += 1
                else:
                    updated += 1

            await db.touch_seen(SOURCE, seen_ids)
            deactivated = await db.deactivate_missing(SOURCE, seen_ids)
        await db.sync_finished(log_id, added=added, updated=updated, deactivated=deactivated, seen=len(seen_ids))
        log.info("Joymee sinx: ko'rildi %s, yangi %s, yangilandi %s, yopildi %s",
                 len(seen_ids), added, updated, deactivated)
    except Exception as exc:  # noqa: BLE001
        log.exception("Joymee sinx xatosi")
        await db.sync_finished(log_id, added=added, updated=updated, deactivated=deactivated,
                               seen=len(seen_ids), error=str(exc)[:500])
        raise
    return {"added": added, "updated": updated, "deactivated": deactivated, "seen": len(seen_ids)}
