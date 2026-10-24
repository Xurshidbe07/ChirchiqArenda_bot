"""Lokal serverni HTTPS orqali ochish uchun vaqtinchalik cloudflared tunnel.

Telegram Mini App faqat HTTPS manzilni qabul qiladi. WEBAPP_URL berilmagan bo'lsa
va kompyuterda `cloudflared` o'rnatilgan bo'lsa, bot ishga tushganda
`cloudflared tunnel --url http://127.0.0.1:PORT` ni ochib, bergan manzilni ishlatadi.
Manzil har ishga tushirishda o'zgaradi (bu faqat dev uchun; serverda WEBAPP_URL yozing).
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
import shutil
from pathlib import Path

log = logging.getLogger("tunnel")

_URL_RE = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")
_proc: asyncio.subprocess.Process | None = None

# winget o'rnatgandan keyin PATH yangilanmagan bo'lishi mumkin — odatiy joylarni ham tekshiramiz
_CANDIDATES = (
    r"C:\Program Files (x86)\cloudflared\cloudflared.exe",
    r"C:\Program Files\cloudflared\cloudflared.exe",
    "/usr/local/bin/cloudflared",
    "/usr/bin/cloudflared",
)


def find_exe() -> str | None:
    custom = os.getenv("CLOUDFLARED_PATH", "").strip()
    if custom and Path(custom).is_file():
        return custom
    found = shutil.which("cloudflared")
    if found:
        return found
    for c in _CANDIDATES:
        if Path(c).is_file():
            return c
    return None


def available() -> bool:
    return find_exe() is not None


async def start(port: int, timeout: float = 40.0) -> str | None:
    """Tunnel ochadi va tashqi HTTPS manzilni qaytaradi (yoki None)."""
    global _proc
    exe = find_exe()
    if exe is None:
        return None

    _proc = await asyncio.create_subprocess_exec(
        exe, "tunnel", "--url", f"http://127.0.0.1:{port}", "--no-autoupdate",
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
    )
    assert _proc.stderr is not None

    async def _read_url() -> str | None:
        while True:
            line = await _proc.stderr.readline()
            if not line:
                return None
            m = _URL_RE.search(line.decode("utf-8", "ignore"))
            if m:
                return m.group(0)

    try:
        url = await asyncio.wait_for(_read_url(), timeout)
    except asyncio.TimeoutError:
        log.warning("cloudflared %s soniyada manzil bermadi.", timeout)
        await stop()
        return None

    if url:
        # Qolgan stderr'ni o'qib turamiz, aks holda bufer to'lib qolishi mumkin
        asyncio.create_task(_drain())
        log.info("Tunnel ochildi: %s", url)
    return url


async def _drain() -> None:
    if _proc is None or _proc.stderr is None:
        return
    while await _proc.stderr.readline():
        pass


async def stop() -> None:
    global _proc
    if _proc is not None and _proc.returncode is None:
        _proc.terminate()
        try:
            await asyncio.wait_for(_proc.wait(), 5)
        except asyncio.TimeoutError:
            _proc.kill()
    _proc = None
