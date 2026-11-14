"""Tashqi manbalarni davriy sinxronlash (fon vazifasi): Joymee + Uybor."""
from __future__ import annotations

import asyncio
import logging

from bot.config import config
from bot.scrapers import joymee, qayoda, uybor

log = logging.getLogger("sync")

_lock = asyncio.Lock()
_task: asyncio.Task | None = None
_qayoda_task: asyncio.Task | None = None


def is_running() -> bool:
    return _lock.locked()


def _sources():
    out = [("joymee", joymee.sync)]
    if config.uybor_cities:
        out.append(("uybor", uybor.sync))
    return out


async def run_once() -> dict:
    """Barcha manbalarni bir marta sinxronlaydi. Bitta manba yiqilsa, qolganlari baribir ishlaydi.

    Natija: jami added/updated/deactivated/seen + har manba bo'yicha (sources) + xatolar (errors).
    """
    async with _lock:
        total = {"added": 0, "updated": 0, "deactivated": 0, "seen": 0}
        per_source: dict[str, dict] = {}
        errors: dict[str, str] = {}
        for name, fn in _sources():
            try:
                res = await fn()
                per_source[name] = res
                for k in total:
                    total[k] += res.get(k, 0)
            except Exception as exc:  # noqa: BLE001 — xato manbaning o'zida loglangan
                errors[name] = str(exc)[:300]
        if errors and not per_source:
            raise RuntimeError("; ".join(f"{k}: {v}" for k, v in errors.items()))
        return {**total, "sources": per_source, "errors": errors}


async def _loop(interval_min: int) -> None:
    await asyncio.sleep(5)  # bot to'liq ko'tarilsin
    while True:
        try:
            await run_once()
        except Exception:  # noqa: BLE001
            pass
        await asyncio.sleep(interval_min * 60)


async def _qayoda_loop(interval_min: int) -> None:
    """Qayoda sekin (Crawl-delay 10s) — admin «Yangilash» tugmasini kutdirmaslik uchun alohida."""
    await asyncio.sleep(90)  # tezkor manbalar avval ishlasin
    while True:
        try:
            await qayoda.sync()
        except Exception:  # noqa: BLE001 — xato loglangan
            pass
        await asyncio.sleep(interval_min * 60)


def start_background() -> None:
    global _task, _qayoda_task
    if config.sync_interval_min <= 0:
        log.info("Avtomatik sinxronlash o'chiq (SYNC_INTERVAL_MIN=0).")
        return
    _task = asyncio.create_task(_loop(config.sync_interval_min), name="market-sync")
    log.info("Sinxronlash har %s daqiqada: %s.", config.sync_interval_min, ", ".join(n for n, _ in _sources()))
    if config.qayoda_cities and config.qayoda_interval_min > 0:
        _qayoda_task = asyncio.create_task(_qayoda_loop(config.qayoda_interval_min), name="qayoda-sync")
        log.info("Qayoda sinxronlash har %s daqiqada (Crawl-delay 10s).", config.qayoda_interval_min)


async def stop_background() -> None:
    for t in (_task, _qayoda_task):
        if t is not None and not t.done():
            t.cancel()
            try:
                await t
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
