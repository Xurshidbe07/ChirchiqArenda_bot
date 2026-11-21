"""Uybor (uybor.uz) dan Chirchiq ijara e'lonlarini tortish.

Saytning o'zi ishlatadigan ochiq JSON API (robots.txt faqat /admin/, /cgi-bin/, /tmp/ ni yopadi):
  GET https://api.uybor.uz/api/v1/listings?mode=search&operationType__eq=rent&region__eq=13
      &embed=category,subCategory,city,district,zone,media,user&limit=..&offset=..

region 13 = Toshkent shahri, region 12 = Toshkent viloyati (city 150 = Chirchiq).
Kategoriyalar: 7 Kvartira, 8 Uy, 9 Kottej, 26 Xona, 27 Dacha, 28 Xususiy uy (UYBOR_CATEGORIES).
pricePeriodUnit: "day" -> kunlik ijara, aks holda oylik.

Eslatma: uybor telefon raqamini ochiq API'da bermaydi — bunday e'lonlarda klient e'lon sahifasiga
o'tib bog'lanadi (market'da «Bog'lanish ↗» tugmasi).
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

import aiohttp

from bot import db
from bot.areas import area_or_default
from bot.config import config

log = logging.getLogger("scraper.uybor")

SOURCE = "uybor"
API = "https://api.uybor.uz/api/v1/"
HEADERS = {
    "User-Agent": "ArendaUzBot/1.0 (student project; Telegram @Arenda1UzBot)",
    "Accept": "application/json",
    "Origin": "https://uybor.uz",
    "Referer": "https://uybor.uz/",
}
EMBED = "category,subCategory,region,city,district,zone,media,user"
PER_PAGE = 50
PAUSE = 0.4

# Chirchiq city_id -> bazadagi mavze nomi (Joymee bilan bir xil bo'lsin, filtr birlashsin)
_CITY_DISTRICT = {150: "Chirchiq shahar"}


class UyborError(RuntimeError):
    pass


async def _get(session: aiohttp.ClientSession, path: str) -> Any:
    async with session.get(API + path, timeout=aiohttp.ClientTimeout(total=30)) as r:
        if r.status != 200:
            raise UyborError(f"{path} -> HTTP {r.status}")
        return await r.json(content_type=None)


def _dec(v: Any) -> Decimal | None:
    if v in (None, ""):
        return None
    try:
        return Decimal(str(v))
    except InvalidOperation:
        return None


def _int(v: Any) -> int | None:
    try:
        n = int(str(v).strip())
        return n
    except (TypeError, ValueError):
        return None


def _dt(v: str | None) -> datetime | None:
    if not v:
        return None
    try:
        return datetime.fromisoformat(v.replace("Z", "+00:00"))
    except ValueError:
        return None


def _name(obj: Any, lang: str = "uz") -> str | None:
    if not isinstance(obj, dict):
        return None
    n = obj.get("name")
    if isinstance(n, dict):
        return n.get(lang) or n.get("ru") or n.get("en")
    return n


def map_listing(a: dict[str, Any]) -> dict[str, Any]:
    """Uybor e'lonini bizning houses maydonlariga o'giradi."""
    price = _dec(a.get("price")) or Decimal(0)
    currency = "USD" if str(a.get("priceCurrency", "")).lower() == "usd" else "UZS"
    rooms = _int(a.get("room"))
    city_id = a.get("cityId")
    region_id = a.get("regionId")
    sub = _name(a.get("subCategory")) or _name(a.get("category")) or "E'lon"
    street = (a.get("address") or "").strip()
    city_ru = _name(a.get("city"), "ru")
    district_ru = _name(a.get("district"), "ru")
    # tanilmagan posyolka/qishloq filtrni to'ldirib yubormasin — viloyat nomi ostida
    default_area = "Toshkent shahri" if region_id == 13 else "Toshkent viloyati"
    district = _CITY_DISTRICT.get(city_id) or area_or_default(default_area, district_ru, city_ru, street)
    city_name = "Chirchiq" if city_id == 150 else ("Toshkent" if region_id == 13 else (city_ru or ""))
    show_district = district and (not city_name or city_name.lower() not in district.lower())
    address = ", ".join(p for p in (city_name, district if show_district else "", street) if p) or district
    desc = (a.get("description") or "").strip()
    # Uybor'da alohida sarlavha yo'q: turkum + xona + tavsif boshidan yasaymiz
    first_line = desc.split("\n", 1)[0].strip()
    title = first_line[:80] if len(first_line) >= 12 else f"{sub}{f', {rooms} xona' if rooms else ''} — {city_name or 'Chirchiq'}"
    media = a.get("media") or []
    photos = [m["url"] for m in media if isinstance(m, dict) and m.get("url")]
    user = a.get("user") or {}
    seller = user.get("displayName") or " ".join(p for p in (user.get("firstName"), user.get("lastName")) if p) or None
    return {
        "rent_period": "day" if a.get("pricePeriodUnit") == "day" else "month",
        "title": title[:200],
        "address": address[:250],
        "rooms": rooms if rooms and 0 < rooms <= 50 else None,
        "price": price,
        "currency": currency,
        "description": desc[:4000],
        "contact_phone": None,
        "district": district,
        "area": _dec(a.get("square")),
        "floor": _int(a.get("floor")),
        "floors": _int(a.get("floorTotal")),
        "photo_urls": photos[:12],
        "seller_name": seller,
        "seller_username": None,
        "lat": a.get("lat"),
        "lon": a.get("lng"),
        "external_created_at": _dt(a.get("upAt") or a.get("createdAt")),
        "source_url": f"https://uybor.uz/listings/{a['id']}",
        "views": int(a.get("views") or 0),
    }


async def fetch_listings(session: aiohttp.ClientSession) -> dict[str, dict[str, Any]]:
    """UYBOR_REGIONS (region__eq) va UYBOR_CITIES (city__eq) bo'yicha eng yangi ijara e'lonlari."""
    found: dict[str, dict[str, Any]] = {}
    filters = [f"region__eq={r}" for r in config.uybor_regions] + [f"city__eq={c}" for c in config.uybor_cities]
    for flt in filters:
        for page in range(1, config.uybor_max_pages + 1):
            # order=upAt — eng yangi birinchi (saytning o'zi shunday so'raydi); sahifalash `page` bilan
            data = await _get(
                session,
                f"listings?mode=search&operationType__eq=rent&{flt}"
                f"&embed={EMBED}&order=upAt&limit={PER_PAGE}&page={page}",
            )
            res = data.get("results") or []
            for a in res:
                if a.get("isActive") is False or a.get("moderationStatus") not in (None, "approved"):
                    continue
                if a.get("categoryId") not in config.uybor_categories:
                    continue
                found[str(a["id"])] = a
            if not res or page * PER_PAGE >= int(data.get("total") or 0):
                break
            await asyncio.sleep(PAUSE)
    return found


async def sync() -> dict[str, int]:
    """Uybor bilan to'liq sinxronlash. Natija: added/updated/deactivated/seen."""
    log_id = await db.sync_started(SOURCE)
    added = updated = deactivated = 0
    seen_ids: list[str] = []
    try:
        async with aiohttp.ClientSession(headers=HEADERS) as session:
            listings = await fetch_listings(session)
        seen_ids = list(listings.keys())
        for sid, a in listings.items():
            _, inserted = await db.upsert_external_house(SOURCE, sid, map_listing(a))
            if inserted:
                added += 1
            else:
                updated += 1
        await db.touch_seen(SOURCE, seen_ids)
        deactivated = await db.deactivate_missing(SOURCE, seen_ids)
        await db.sync_finished(log_id, added=added, updated=updated, deactivated=deactivated, seen=len(seen_ids))
        log.info("Uybor sinx: ko'rildi %s, yangi %s, yangilandi %s, yopildi %s",
                 len(seen_ids), added, updated, deactivated)
    except Exception as exc:  # noqa: BLE001
        log.exception("Uybor sinx xatosi")
        await db.sync_finished(log_id, added=added, updated=updated, deactivated=deactivated,
                               seen=len(seen_ids), error=str(exc)[:500])
        raise
    return {"added": added, "updated": updated, "deactivated": deactivated, "seen": len(seen_ids)}
