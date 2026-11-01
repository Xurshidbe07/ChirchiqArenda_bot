"""Test sozlamalari.

Testlar haqiqiy PostgreSQL bilan ishlaydi (DATABASE_URL). Telegram'ga so'rov yuborilmaydi:
bot tokeni faqat initData/JWT imzolash uchun kerak, shuning uchun CI da soxta token yetarli.
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import os
import socket
import time
from urllib.parse import urlencode

import pytest
from dotenv import load_dotenv

load_dotenv()  # lokal: DATABASE_URL va ADMIN_IDS .env dan; CI: workflow env dan
# Bot tokeni testlarda HAR DOIM soxta — Telegram'ga hech qanday xabar ketmasin (initData/JWT imzosi uchun yetarli)
os.environ["BOT_TOKEN"] = "123456789:TEST_TOKEN_FOR_CI_ONLY"
os.environ.setdefault("ADMIN_IDS", "5170546966")
os.environ.setdefault("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/chirchiq_arenda")
os.environ["SYNC_INTERVAL_MIN"] = "0"
os.environ["KEEPALIVE_MIN"] = "0"
os.environ.setdefault("MODERATION", "0")

from bot.config import config  # noqa: E402

SUPER_ID = sorted(config.admin_ids)[0]


def sign_init_data(user_id: int, name: str = "Test", lang: str = "uz") -> str:
    """Telegram Web App initData ni bot tokeni bilan imzolaydi (server xuddi shunday tekshiradi)."""
    user = json.dumps({"id": user_id, "first_name": name, "username": f"u{user_id}", "language_code": lang},
                      separators=(",", ":"))
    fields = {"auth_date": str(int(time.time())), "query_id": f"AAE{user_id}", "user": user}
    dcs = "\n".join(f"{k}={v}" for k, v in sorted(fields.items()))
    secret = hmac.new(b"WebAppData", config.bot_token.encode(), hashlib.sha256).digest()
    fields["hash"] = hmac.new(secret, dcs.encode(), hashlib.sha256).hexdigest()
    return urlencode(fields)


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Server:
    """Test uchun aiohttp serverni ko'taradi va so'rov yuboradi."""

    def __init__(self) -> None:
        self.base = ""
        self._runner = None
        self._bot = None
        self._session = None

    async def start(self) -> "Server":
        import aiohttp
        from aiogram import Bot
        from aiohttp import web

        from bot import db
        from bot.webapp.server import create_app

        await db.init_db()
        self._bot = Bot(token=config.bot_token)
        self._runner = web.AppRunner(create_app(self._bot))
        await self._runner.setup()
        port = free_port()
        await web.TCPSite(self._runner, "127.0.0.1", port).start()
        self.base = f"http://127.0.0.1:{port}"
        self._session = aiohttp.ClientSession()
        return self

    async def stop(self) -> None:
        from bot import db

        await self._session.close()
        await self._runner.cleanup()
        await self._bot.session.close()
        await db.close_db()

    async def call(self, method: str, path: str, **kw):
        async with self._session.request(method, self.base + path, **kw) as r:
            body = await r.text()
            data = json.loads(body) if r.headers.get("Content-Type", "").startswith("application/json") else body
            return r.status, data


def headers_for(user_id: int, name: str = "Test", lang: str = "uz", jwt: str | None = None) -> dict:
    h = {"Authorization": "tma " + sign_init_data(user_id, name, lang)}
    if jwt:
        h["X-Admin-Token"] = jwt
    return h


JSON = {"Content-Type": "application/json"}


async def cleanup_ids(*user_ids: int) -> None:
    from bot import db

    p = db.pool()
    for uid in user_ids:
        await p.execute("DELETE FROM houses WHERE owner_id = $1 OR created_by = $1", uid)
        await p.execute("DELETE FROM favorites WHERE user_id = $1", uid)
        await p.execute("DELETE FROM admins WHERE telegram_id = $1", uid)
        await p.execute("DELETE FROM users WHERE telegram_id = $1", uid)


def run(coro):
    return asyncio.run(coro)


@pytest.fixture(scope="session", autouse=True)
def _check_db():
    """DB ga ulanib bo'lmasa testlarni tushunarli xabar bilan to'xtatamiz."""
    import asyncpg

    async def ping():
        conn = await asyncpg.connect(config.database_url)
        await conn.close()

    try:
        asyncio.run(ping())
    except Exception as exc:  # noqa: BLE001
        pytest.exit(f"PostgreSQL ga ulanib bo'lmadi ({config.database_url.split('@')[-1]}): {exc}", returncode=2)
