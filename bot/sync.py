"""Tashqi manbalarni davriy sinxronlash (fon vazifasi)."""
from __future__ import annotations

import asyncio
import logging

from bot.config import config
from bot.scrapers import joymee

log = logging.getLogger("sync")

_lock = asyncio.Lock()
_task: asyncio.Task | None = None


def is_running() -> bool:
    return _lock.locked()


async def run_once() -> dict[str, int]:
    """Barcha manbalarni bir marta sinxronlaydi. Parallel chaqirilsa navbat kutadi."""
    async with _lock:
        return await joymee.sync()


async def _loop(interval_min: int) -> None:
    await asyncio.sleep(5)  # bot to'liq ko'tarilsin
    while True:
        try:
            await run_once()
        except Exception:  # noqa: BLE001 — xato allaqachon loglangan
            pass
        await asyncio.sleep(interval_min * 60)


def start_background() -> None:
    """SYNC_INTERVAL_MIN > 0 bo'lsa fon vazifasini ishga tushiradi."""
    global _task
    if config.sync_interval_min <= 0:
        log.info("Avtomatik sinxronlash o'chiq (SYNC_INTERVAL_MIN=0).")
        return
    _task = asyncio.create_task(_loop(config.sync_interval_min), name="market-sync")
    log.info("Sinxronlash har %s daqiqada.", config.sync_interval_min)


async def stop_background() -> None:
    if _task is not None and not _task.done():
        _task.cancel()
        try:
            await _task
        except (asyncio.CancelledError, Exception):  # noqa: BLE001
            pass
