"""Qayoda (qayoda.uz) dan Chirchiq ijara e'lonlarini tortish.

Qayoda — agregator: Uybor, Realt24, Joymee va boshqa saytlardagi e'lonlarni bir katalogda ko'rsatadi.
robots.txt ochiq sahifalarni ruxsat etadi, lekin /api/, qidiruv (/poisk) va kabinetni yopadi hamda
Crawl-delay: 10 talab qiladi. Shuning uchun:
  * faqat ochiq katalog sahifalari (/ru/arenda/..., /ru/posutochno/...) va e'lon sahifalari
    (/ru/obyavlenie/...) o'qiladi, /api/ ga murojaat qilinmaydi;
  * HAR bir so'rovdan oldin kamida 10 soniya kutiladi;
  * tafsilot faqat yangi e'lonlar uchun yuklanadi, bir sinxronda ko'pi bilan QAYODA_MAX_NEW ta.

E'lon ma'lumoti sahifadagi schema.org RealEstateListing (JSON-LD) dan olinadi.
Asl manbasi Joymee yoki Uybor bo'lgan e'lonlar o'tkazib yuboriladi — ular to'g'ridan-to'g'ri tortiladi.
Har e'londa asl manbaga havola saqlanadi (market'da «Bog'lanish ↗»).
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

import aiohttp

from bot import db
from bot.config import config

log = logging.getLogger("scraper.qayoda")

SOURCE = "qayoda"
BASE = "https://qayoda.uz"
HEADERS = {"User-Agent": "ChirchiqArendaBot/1.0 (student project; Telegram @chirchiqarenda_bot)"}
CRAWL_DELAY = 10.5      # robots.txt: Crawl-delay: 10
MAX_LIST_PAGES = 10

# (katalog yo'li, ijara turi)
SECTIONS = (("arenda", "month"), ("posutochno", "day"))

# Turar joy bo'lmagan e'lonlar (slug bo'yicha)
_SKIP_SLUG = ("tijorat", "yer-uchastka", "ofis", "ombor", "dokon", "biznes", "ishlab-chiqarish", "bino-")
_AD_RE = re.compile(r'href="(/ru/obyavlenie/([a-z0-9-]+)-(\d+))"')
_ORIGIN_RE = re.compile(r'https?://(?:www\.)?(olx\.uz|joymee\.uz|uybor\.uz|realt24\.uz)/[^"\'<>\s\\]+')
_LD_RE = re.compile(r'<script type="application/ld\+json"[^>]*>(.*?)</script>', re.S)

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
        if r.status == 429:
            raise QayodaError(f"{path} -> HTTP 429 (sekinlashtirish so'raldi)")
        if r.status != 200:
            raise QayodaError(f"{path} -> HTTP {r.status}")
        return await r.text()


def _dec(v: Any) -> Decimal | None:
    try:
        return Decimal(str(v)) if v not in (None, "") else None
    except InvalidOperation:
        return None


def parse_list_page(html: str) -> dict[str, str]:
    """Katalog sahifasidan e'lonlar: qayoda_id -> yo'l. Turar joy bo'lmaganlar tashlanadi."""
    out: dict[str, str] = {}
    for path, slug, qid in _AD_RE.findall(html):
        if any(k in slug for k in _SKIP_SLUG):
            continue
        out[qid] = path
    return out


def parse_detail(html: str, path: str, rent_period: str) -> dict[str, Any] | None:
    """E'lon sahifasidagi RealEstateListing (JSON-LD) ni houses maydonlariga o'giradi."""
    listing = None
    for raw in _LD_RE.findall(html):
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        for item in data if isinstance(data, list) else [data]:
            if isinstance(item, dict) and item.get("@type") == "RealEstateListing":
                listing = item
    if listing is None:
        return None

    name = (listing.get("name") or "").strip()
    offer = listing.get("offers") or {}
    price = _dec(offer.get("price")) or Decimal(0)
    currency = "USD" if str(offer.get("priceCurrency", "USD")).upper() == "USD" else "UZS"
    addr = ((listing.get("about") or {}).get("address") or {})
    street = (addr.get("streetAddress") or "").strip()
    locality = (addr.get("addressLocality") or "").strip()
    address = "Chirchiq" + (f", {street}" if street and street != locality else "")

    rooms = re.search(r"(\d+)\s*-?\s*комн", name)
    area = re.search(r"([\d]+(?:[.,]\d+)?)\s*м²", name)
    floors = re.search(r"(\d+)\s*/\s*(\d+)\s*эт", name)
    origin = _ORIGIN_RE.search(html)

    posted = listing.get("datePosted")
    try:
        posted_dt = datetime.fromisoformat(posted.replace("Z", "+00:00")) if posted else None
    except ValueError:
        posted_dt = None

    title = re.sub(r"\s+—\s+Чирчик\s*$", "", name) or "E'lon"
    return {
        "rent_period": rent_period,
        "title": title[:200],
        "address": address[:250],
        "rooms": int(rooms.group(1)) if rooms and 0 < int(rooms.group(1)) <= 50 else None,
        "price": price,
        "currency": currency,
        "description": (listing.get("description") or "").strip()[:4000],
        "contact_phone": None,
        "district": "Chirchiq shahar",
        "area": _dec(area.group(1).replace(",", ".")) if area else None,
        "floor": int(floors.group(1)) if floors else None,
        "floors": int(floors.group(2)) if floors else None,
        "photo_urls": [u for u in (listing.get("image") or []) if isinstance(u, str)][:12],
        "seller_name": None,
        "seller_username": None,
        "lat": None,
        "lon": None,
        "external_created_at": posted_dt,
        # Bog'lanish uchun asl e'lon (bo'lmasa qayoda sahifasi)
        "source_url": origin.group(0) if origin else BASE + path,
        "origin_site": origin.group(1) if origin else "qayoda.uz",
        "views": 0,
    }


async def sync() -> dict[str, int]:
    """Qayoda bilan sinxronlash (sekin: Crawl-delay 10s). Natija: added/updated/deactivated/seen."""
    log_id = await db.sync_started(SOURCE)
    added = skipped = deactivated = 0
    seen: dict[str, tuple[str, str]] = {}  # qid -> (path, rent_period)
    try:
        async with aiohttp.ClientSession(headers=HEADERS) as session:
            for city_path in config.qayoda_cities:
                for section, period in SECTIONS:
                    for page in range(1, MAX_LIST_PAGES + 1):
                        q = f"/ru/{section}/{city_path}" + (f"?page={page}" if page > 1 else "")
                        try:
                            html = await _get(session, q)
                        except QayodaError as exc:
                            if "404" in str(exc):
                                break
                            raise
                        found = parse_list_page(html)
                        new = {k: v for k, v in found.items() if k not in seen}
                        for qid, path in new.items():
                            seen[qid] = (path, period)
                        if not new or f"page={page + 1}" not in html:
                            break

            existing = await db.external_snapshot(SOURCE)
            skip = await db.skipped_ids(SOURCE)
            for qid in skip:
                seen.pop(qid, None)
            fresh = [qid for qid in seen if qid not in existing]
            for qid in fresh[: config.qayoda_max_new]:
                path, period = seen[qid]
                try:
                    html = await _get(session, path)
                except QayodaError as exc:
                    log.warning("Tafsilot olinmadi %s: %s", qid, exc)
                    continue
                data = parse_detail(html, path, period)
                if data is None:
                    continue
                origin = data.pop("origin_site")
                if origin in ("joymee.uz", "uybor.uz"):
                    # bu manbalar to'g'ridan-to'g'ri tortiladi — takror bo'lmasin va qayta yuklanmasin
                    await db.mark_skipped(SOURCE, qid, f"dupe:{origin}")
                    skipped += 1
                    seen.pop(qid, None)
                    continue
                _, inserted = await db.upsert_external_house(SOURCE, qid, data)
                added += int(inserted)

        seen_ids = list(seen.keys())
        await db.touch_seen(SOURCE, seen_ids)
        deactivated = await db.deactivate_missing(SOURCE, seen_ids)
        await db.sync_finished(log_id, added=added, updated=0, deactivated=deactivated, seen=len(seen_ids))
        log.info("Qayoda sinx: ko'rildi %s, yangi %s, takror (joymee/uybor) %s, yopildi %s",
                 len(seen_ids), added, skipped, deactivated)
    except Exception as exc:  # noqa: BLE001
        log.exception("Qayoda sinx xatosi")
        await db.sync_finished(log_id, added=added, updated=0, deactivated=deactivated,
                               seen=len(seen), error=str(exc)[:500])
        raise
    return {"added": added, "updated": 0, "deactivated": deactivated, "seen": len(seen), "skipped_dupes": skipped}
