"""Muhit o'zgaruvchilaridan (.env) konfiguratsiyani o'qish."""
import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Config:
    bot_token: str
    database_url: str
    admin_ids: frozenset[int] = field(default_factory=frozenset)
    # Mini App (Telegram Web App) sozlamalari
    webapp_url: str = ""          # tashqi HTTPS manzil; bo'sh bo'lsa cloudflared tunnel ochiladi
    webapp_host: str = "127.0.0.1"
    webapp_port: int = 8080


def _parse_admin_ids(raw: str) -> frozenset[int]:
    ids: set[int] = set()
    for part in raw.split(","):
        part = part.strip()
        if part:
            ids.add(int(part))
    return frozenset(ids)


def load_config() -> Config:
    token = os.getenv("BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("BOT_TOKEN topilmadi. .env faylini .env.example asosida yarating.")

    db_url = os.getenv("DATABASE_URL", "").strip()
    if not db_url:
        raise RuntimeError("DATABASE_URL topilmadi. .env faylini tekshiring.")

    return Config(
        bot_token=token,
        database_url=db_url,
        admin_ids=_parse_admin_ids(os.getenv("ADMIN_IDS", "")),
        webapp_url=os.getenv("WEBAPP_URL", "").strip().rstrip("/"),
        webapp_host=os.getenv("WEBAPP_HOST", "127.0.0.1").strip() or "127.0.0.1",
        webapp_port=int(os.getenv("WEBAPP_PORT", "8080") or 8080),
    )


config = load_config()
