"""OLX.uz dan Chirchiq ijara e'lonlarini olish (oddiy, yumshoq scraper, /olx buyrug'i uchun).

- Proksilar `PROXIES` muhit o'zgaruvchisidan (vergul yoki yangi qator bilan ajratilgan
  `ip:port:login:parol`) yoki `PROXIES_FILE` faylidan o'qiladi. Render'da Secret File sifatida
  `/etc/secrets/proxies.txt` qo'shilsa, avtomatik topiladi.
- So'rovlar proksilar orasida navbat bilan taqsimlanadi, natija OLX_CACHE_TTL soniya keshda turadi.
- OLX so'rovni rad etsa (403/429), bot-himoyani aylanib o'tishga urinilmaydi: bot foydalanuvchiga
  to'g'ridan-to'g'ri OLX havolasini beradi.
"""
from __future__ import annotations

import asyncio
import itertools
import logging
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path

import aiohttp

log = logging.getLogger("scraper.olx")

API_URL = "https://www.olx.uz/api/v1/offers/"
HEADERS = {
    "User-Agent": "ChirchiqArendaBot/1.0 (Telegram @chirchiqarenda_bot)",
    "Accept": "application/json",
    "Accept-Language": "uz,ru;q=0.9",
}
_SECRET_FILE = "/etc/secrets/proxies.txt"  # Render Secret Files joylashuvi


class OLXBlocked(RuntimeError):
    """OLX so'rovni rad etdi (403/429) — foydalanuvchini havolaga yo'naltiramiz."""


@dataclass(frozen=True)
class Offer:
    title: str
    price: str
    location: str
    url: str
    photo: str | None


def parse_proxy(line: str) -> str | None:
    """`ip:port:login:parol` yoki `ip:port` -> aiohttp proksi manzili."""
    line = line.strip()
    if not line or line.startswith("#"):
        return None
    if "://" in line:
        return line
    parts = line.split(":")
    if len(parts) == 4:
        ip, port, user, pwd = parts
        return f"http://{user}:{pwd}@{ip}:{port}"
    if len(parts) == 2:
        return f"http://{parts[0]}:{parts[1]}"
    return None


def load_proxies() -> list[str]:
    raw = os.getenv("PROXIES", "")
    if not raw.strip():
        path = os.getenv("PROXIES_FILE", "").strip() or _SECRET_FILE
        p = Path(path)
        if not p.is_absolute():
            p = Path.cwd() / p
        raw = p.read_text(encoding="utf-8") if p.is_file() else ""
    proxies = [px for px in map(parse_proxy, re.split(r"[\s,]+", raw)) if px]
    if not proxies:
        log.info("OLX: proksi berilmagan — to'g'ridan-to'g'ri so'rov yuboriladi")
    return proxies


def parse_offer(item: dict) -> Offer:
    price = next(
        (p.get("value", {}).get("label") for p in item.get("params", []) if p.get("key") == "price"),
        None,
    ) or "—"
    loc = item.get("location") or {}
    place = ", ".join(x["name"] for x in (loc.get("city"), loc.get("district")) if x and x.get("name"))
    photo = None
    if item.get("photos"):
        link = item["photos"][0].get("link") or ""
        photo = link.replace("{width}", "640").replace("{height}", "480") or None
    return Offer(
        title=(item.get("title") or "").strip(),
        price=price,
        location=place,
        url=item.get("url") or "",
        photo=photo,
    )


class OLXScraper:
    def __init__(self, proxies: list[str] | None = None, api_url: str | None = None) -> None:
        self.proxies = load_proxies() if proxies is None else proxies
        self.api_url = api_url or API_URL
        self._cycle = itertools.cycle(self.proxies) if self.proxies else None
        self._cache: tuple[float, list[Offer]] | None = None
        self._lock = asyncio.Lock()

    @staticmethod
    def _params(limit: int) -> dict:
        params: dict = {"offset": 0, "limit": limit, "sort_by": "created_at:desc"}
        if os.getenv("OLX_CATEGORY_ID"):
            params["category_id"] = os.environ["OLX_CATEGORY_ID"]
        if os.getenv("OLX_CITY_ID"):
            params["city_id"] = os.environ["OLX_CITY_ID"]
        if "category_id" not in params and "city_id" not in params:
            params["query"] = os.getenv("OLX_QUERY", "Chirchiq ijara")
        return params

    async def _fetch(self, limit: int) -> list[Offer]:
        timeout = aiohttp.ClientTimeout(total=20)
        attempts = max(1, min(3, len(self.proxies)))
        last_err: Exception | None = None
        async with aiohttp.ClientSession(headers=HEADERS, timeout=timeout) as s:
            for _ in range(attempts):
                proxy = next(self._cycle) if self._cycle else None
                try:
                    async with s.get(self.api_url, params=self._params(limit), proxy=proxy) as r:
                        if r.status in (403, 429):
                            raise OLXBlocked(f"HTTP {r.status}")
                        r.raise_for_status()
                        data = await r.json(content_type=None)
                    return [parse_offer(i) for i in data.get("data") or []]
                except OLXBlocked:
                    raise  # rad etilsa boshqa proksi bilan qayta urinmaymiz
                except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
                    log.warning("OLX: proksi ishlamadi (%s): %s", proxy and proxy.split("@")[-1], exc)
                    last_err = exc
        raise last_err or RuntimeError("OLX'dan javob olinmadi")

    async def latest(self, limit: int = 5) -> list[Offer]:
        ttl = int(os.getenv("OLX_CACHE_TTL", "600") or 0)
        async with self._lock:
            if self._cache and time.monotonic() - self._cache[0] < ttl:
                return self._cache[1][:limit]
            offers = await self._fetch(max(limit, 10))
            self._cache = (time.monotonic(), offers)
            return offers[:limit]


_scraper: OLXScraper | None = None


def get_scraper() -> OLXScraper:
    global _scraper
    if _scraper is None:
        _scraper = OLXScraper()
        log.info("OLX scraper: %d ta proksi", len(_scraper.proxies))
    return _scraper
