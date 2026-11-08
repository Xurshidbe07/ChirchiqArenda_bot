"""OLX.uz e'lonlarini proksilar orqali olish (oddiy, yumshoq scraper).

- Proksilar `proxies.txt` faylidan o'qiladi (har qatorda ip:port:login:parol).
- So'rovlar proksilar orasida navbat bilan taqsimlanadi.
- Natija bir necha daqiqa keshda saqlanadi, OLX'ga ortiqcha yuk tushmaydi.
- OLX so'rovni rad etsa (403/429), aylanib o'tishga urinilmaydi:
  bot foydalanuvchiga to'g'ridan-to'g'ri OLX havolasini ko'rsatadi.
"""
import asyncio
import itertools
import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path

import aiohttp

log = logging.getLogger(__name__)

API_URL = "https://www.olx.uz/api/v1/offers/"
HEADERS = {
    "User-Agent": "ChirchiqArendaBot/1.0 (+https://t.me/)",
    "Accept": "application/json",
    "Accept-Language": "uz,ru;q=0.9",
}
def cache_ttl() -> int:
    return int(os.getenv("OLX_CACHE_TTL", "600"))  # soniya

# Foydalanuvchi bosganda ochiladigan sahifa (Chirchiq, uzoq muddatli ijara)
OLX_PAGE = {
    "uz": "https://www.olx.uz/oz/nedvizhimost/kvartiry/arenda-dolgosrochnaya/chirchik/",
    "ru": "https://www.olx.uz/nedvizhimost/kvartiry/arenda-dolgosrochnaya/chirchik/",
}


def olx_url(lang: str) -> str:
    return os.getenv("OLX_URL") or OLX_PAGE.get(lang, OLX_PAGE["uz"])


class OLXBlocked(Exception):
    """OLX so'rovni rad etdi (403/429) — havolaga yo'naltiramiz."""


@dataclass
class Offer:
    title: str
    price: str
    location: str
    url: str
    photo: str | None


def load_proxies(path: str | None = None) -> list[str]:
    path = path or os.getenv("PROXIES_FILE", "proxies.txt")
    p = Path(path)
    if not p.is_absolute():
        p = Path(__file__).parent / p
    if not p.exists():
        log.warning("Proksi fayli topilmadi: %s — proksisiz ishlaymiz", p)
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        parts = line.strip().split(":")
        if len(parts) == 4:
            ip, port, user, pwd = parts
            out.append(f"http://{user}:{pwd}@{ip}:{port}")
        elif len(parts) == 2:
            out.append(f"http://{parts[0]}:{parts[1]}")
    return out


def _parse(item: dict) -> Offer:
    price = next(
        (p.get("value", {}).get("label") for p in item.get("params", [])
         if p.get("key") == "price"),
        None,
    ) or "—"
    loc = item.get("location") or {}
    place = ", ".join(
        x["name"] for x in (loc.get("city"), loc.get("district")) if x and x.get("name")
    )
    photo = None
    if item.get("photos"):
        photo = (item["photos"][0].get("link") or "").replace("{width}", "640") \
            .replace("{height}", "480") or None
    return Offer(
        title=item.get("title", "").strip(),
        price=price,
        location=place,
        url=item.get("url", ""),
        photo=photo,
    )


class OLXScraper:
    def __init__(self, proxies: list[str] | None = None):
        self.proxies = proxies if proxies is not None else load_proxies()
        self._cycle = itertools.cycle(self.proxies) if self.proxies else None
        self._cache: tuple[float, list[Offer]] | None = None
        self._lock = asyncio.Lock()

    def _params(self, limit: int) -> dict:
        params = {"offset": 0, "limit": limit, "sort_by": "created_at:desc"}
        if os.getenv("OLX_CATEGORY_ID"):
            params["category_id"] = os.environ["OLX_CATEGORY_ID"]
        if os.getenv("OLX_CITY_ID"):
            params["city_id"] = os.environ["OLX_CITY_ID"]
        if not params.keys() & {"category_id", "city_id"}:
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
                    async with s.get(API_URL, params=self._params(limit), proxy=proxy) as r:
                        if r.status in (403, 429):
                            raise OLXBlocked(f"HTTP {r.status}")
                        r.raise_for_status()
                        data = await r.json(content_type=None)
                    return [_parse(i) for i in data.get("data", [])]
                except OLXBlocked:
                    raise
                except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                    # Faqat tarmoq xatosida keyingi proksini sinaymiz
                    log.warning("Proksi ishlamadi (%s): %s", proxy and proxy.split("@")[-1], e)
                    last_err = e
        raise last_err or RuntimeError("OLX'dan javob olinmadi")

    async def latest(self, limit: int = 5) -> list[Offer]:
        async with self._lock:
            if self._cache and time.monotonic() - self._cache[0] < cache_ttl():
                return self._cache[1][:limit]
            offers = await self._fetch(max(limit, 10))
            self._cache = (time.monotonic(), offers)
            return offers[:limit]
