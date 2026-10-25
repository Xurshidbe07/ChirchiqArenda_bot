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
    # Market: tashqi manbalardan sinxronlash
    sync_interval_min: int = 30                 # 0 = avtomatik sinxronlash o'chiq
    joymee_districts: tuple[int, ...] = (166,)  # 166 = Chirchiq shahar
    joymee_categories: tuple[int, ...] = (4, 5) # 4 = Kvartira, 5 = Uy/dacha
    usd_rate: int = 12500                       # 1 y.e necha so'm (filtr uchun)


def _parse_admin_ids(raw: str) -> frozenset[int]:
    ids: set[int] = set()
    for part in raw.split(","):
        part = part.strip()
        if part:
            ids.add(int(part))
    return frozenset(ids)


def _parse_int_list(raw: str, default: tuple[int, ...]) -> tuple[int, ...]:
    vals = tuple(int(p) for p in raw.split(",") if p.strip())
    return vals or default


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
        sync_interval_min=int(os.getenv("SYNC_INTERVAL_MIN", "30") or 0),
        joymee_districts=_parse_int_list(os.getenv("JOYMEE_DISTRICTS", ""), (166,)),
        joymee_categories=_parse_int_list(os.getenv("JOYMEE_CATEGORIES", ""), (4, 5)),
        usd_rate=int(os.getenv("USD_RATE", "12500") or 12500),
    )


config = load_config()
