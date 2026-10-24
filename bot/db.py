"""PostgreSQL bilan ishlash qatlami (asyncpg)."""
from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Any

import asyncpg

from bot.config import config

SCHEMA_PATH = Path(__file__).resolve().parent.parent / "sql" / "schema.sql"

_pool: asyncpg.Pool | None = None


async def init_db() -> None:
    """Ulanishlar pulini yaratadi va sxemani qo'llaydi."""
    global _pool
    _pool = await asyncpg.create_pool(config.database_url, min_size=1, max_size=10)
    async with _pool.acquire() as conn:
        await conn.execute(SCHEMA_PATH.read_text(encoding="utf-8"))


async def close_db() -> None:
    if _pool is not None:
        await _pool.close()


def pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("DB hali ishga tushirilmagan. Avval init_db() ni chaqiring.")
    return _pool


# ----------------------------------------------------------------- USERS ---

async def upsert_user(telegram_id: int, full_name: str, username: str | None) -> asyncpg.Record:
    """Foydalanuvchini ro'yxatga oladi yoki ismini/username ini yangilaydi."""
    return await pool().fetchrow(
        """
        INSERT INTO users (telegram_id, full_name, username)
        VALUES ($1, $2, $3)
        ON CONFLICT (telegram_id) DO UPDATE
            SET full_name = EXCLUDED.full_name,
                username  = EXCLUDED.username
        RETURNING *
        """,
        telegram_id, full_name, username,
    )


async def get_user(telegram_id: int) -> asyncpg.Record | None:
    return await pool().fetchrow("SELECT * FROM users WHERE telegram_id = $1", telegram_id)


async def is_blocked(telegram_id: int) -> bool:
    row = await pool().fetchval(
        "SELECT is_blocked FROM users WHERE telegram_id = $1", telegram_id
    )
    return bool(row)


async def set_phone(telegram_id: int, phone: str) -> None:
    await pool().execute("UPDATE users SET phone = $2 WHERE telegram_id = $1", telegram_id, phone)


async def list_users(
    offset: int = 0,
    limit: int = 10,
    blocked: bool | None = None,
    q: str | None = None,
) -> list[asyncpg.Record]:
    """Klientlar ro'yxati. `q` — ism, username yoki telegram_id bo'yicha qidiruv."""
    conds: list[str] = []
    args: list[Any] = [limit, offset]
    if blocked is not None:
        args.append(blocked)
        conds.append(f"is_blocked = ${len(args)}")
    if q:
        args.append(f"%{q.strip()}%")
        conds.append(
            f"(full_name ILIKE ${len(args)} OR username ILIKE ${len(args)} "
            f"OR telegram_id::text LIKE ${len(args)})"
        )
    where = f"WHERE {' AND '.join(conds)}" if conds else ""
    return await pool().fetch(
        f"SELECT * FROM users {where} ORDER BY created_at DESC LIMIT $1 OFFSET $2", *args
    )


async def count_users(blocked: bool | None = None) -> int:
    if blocked is None:
        return await pool().fetchval("SELECT COUNT(*) FROM users")
    return await pool().fetchval("SELECT COUNT(*) FROM users WHERE is_blocked = $1", blocked)


async def block_user(telegram_id: int, reason: str | None = None) -> bool:
    """Klientni bloklaydi. Foydalanuvchi topilsa True qaytaradi."""
    status = await pool().execute(
        """
        UPDATE users
           SET is_blocked = TRUE, block_reason = $2, blocked_at = NOW()
         WHERE telegram_id = $1
        """,
        telegram_id, reason,
    )
    return status.endswith(" 1")


async def unblock_user(telegram_id: int) -> bool:
    status = await pool().execute(
        """
        UPDATE users
           SET is_blocked = FALSE, block_reason = NULL, blocked_at = NULL
         WHERE telegram_id = $1
        """,
        telegram_id,
    )
    return status.endswith(" 1")


# ---------------------------------------------------------------- HOUSES ---

async def add_house(
    *,
    title: str,
    address: str,
    rooms: int,
    price: Decimal,
    description: str,
    photo_file_id: str | None,
    contact_phone: str | None,
    created_by: int,
) -> int:
    """Yangi uy qo'shadi va uning ID sini qaytaradi."""
    return await pool().fetchval(
        """
        INSERT INTO houses (title, address, rooms, price, description,
                            photo_file_id, contact_phone, created_by)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
        RETURNING id
        """,
        title, address, rooms, price, description, photo_file_id, contact_phone, created_by,
    )


async def get_house(house_id: int) -> asyncpg.Record | None:
    return await pool().fetchrow("SELECT * FROM houses WHERE id = $1", house_id)


async def list_houses(offset: int = 0, limit: int = 10, only_active: bool = True) -> list[asyncpg.Record]:
    where = "WHERE is_active" if only_active else ""
    return await pool().fetch(
        f"SELECT * FROM houses {where} ORDER BY created_at DESC LIMIT $1 OFFSET $2",
        limit, offset,
    )


async def count_houses(only_active: bool = True) -> int:
    where = "WHERE is_active" if only_active else ""
    return await pool().fetchval(f"SELECT COUNT(*) FROM houses {where}")


async def delete_house(house_id: int) -> bool:
    """Uyni bazadan butunlay o'chiradi."""
    status = await pool().execute("DELETE FROM houses WHERE id = $1", house_id)
    return status.endswith(" 1")


async def set_house_active(house_id: int, active: bool) -> bool:
    status = await pool().execute(
        "UPDATE houses SET is_active = $2 WHERE id = $1", house_id, active
    )
    return status.endswith(" 1")


async def stats() -> dict[str, int]:
    row = await pool().fetchrow(
        """
        SELECT
            (SELECT COUNT(*) FROM users)                          AS users_total,
            (SELECT COUNT(*) FROM users WHERE is_blocked)         AS users_blocked,
            (SELECT COUNT(*) FROM houses)                         AS houses_total,
            (SELECT COUNT(*) FROM houses WHERE is_active)         AS houses_active
        """
    )
    return dict(row)
