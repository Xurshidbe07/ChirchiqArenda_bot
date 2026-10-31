"""Keep-alive: bepul hostingda (Render) server uxlab qolmasligi uchun o'z manziliga so'rov yuboradi.

Render bepul Web Service 15 daqiqa so'rov bo'lmasa uxlaydi, uxlaganda bot Telegram'ni
polling qila olmaydi. Har KEEPALIVE_MIN daqiqada {WEBAPP_URL}/health ga GET yuboramiz —
bu Render uchun "faollik" hisoblanadi.

Eslatma: bu faqat server uyg'oq bo'lganda ishlaydi. Qo'shimcha kafolat uchun tashqi
pinger (masalan UptimeRobot, har 5 daqiqada /health) ham ulab qo'yish tavsiya etiladi.
"""
from __future__ import annotations

import asyncio
import logging

import aiohttp

from bot.config import config

log = logging.getLogger("keepalive")

_task: asyncio.Task | None = None


async def _loop(url: str, interval_min: int) -> None:
    await asyncio.sleep(60)  # bot to'liq ko'tarilsin
    while True:
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as s:
                async with s.get(url) as r:
                    log.info("Keep-alive ping -> %s", r.status)
        except Exception as exc:  # noqa: BLE001
            log.warning("Keep-alive ping xatosi: %s", exc)
        await asyncio.sleep(interval_min * 60)


def start_background(webapp_url: str) -> None:
    """WEBAPP_URL bor va KEEPALIVE_MIN > 0 bo'lsa fon vazifasini ishga tushiradi."""
    global _task
    if config.keepalive_min <= 0 or not webapp_url:
        log.info("Keep-alive o'chiq.")
        return
    _task = asyncio.create_task(_loop(webapp_url + "/health", config.keepalive_min), name="keepalive")
    log.info("Keep-alive har %s daqiqada: %s/health", config.keepalive_min, webapp_url)


async def stop_background() -> None:
    if _task is not None and not _task.done():
        _task.cancel()
        try:
            await _task
        except (asyncio.CancelledError, Exception):  # noqa: BLE001
            pass
