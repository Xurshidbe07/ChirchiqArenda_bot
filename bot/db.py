"""PostgreSQL bilan ishlash qatlami (asyncpg)."""
from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Any

import asyncpg

from bot.config import config

SCHEMA_PATH = Path(__file__).resolve().parent.parent / "sql" / "schema.sql"

_pool: asyncpg.Pool | None = None

# Uy + sevimli belgisi + egasi bilan tanlash ($1 = ko'ruvchi telegram_id bo'lishi shart)
_HOUSE_SELECT = """
    SELECT h.*,
           EXISTS(SELECT 1 FROM favorites f WHERE f.user_id = $1 AND f.house_id = h.id) AS is_favorite,
           u.username AS owner_username, u.full_name AS owner_name, u.lang AS owner_lang
      FROM houses h
 LEFT JOIN users u ON u.telegram_id = h.owner_id
"""
# Klientlar ko'radigan e'lonlar
PUBLIC_COND = "h.is_active AND NOT h.admin_hidden AND h.status = 'approved'"


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
    """Foydalanuvchini ro'yxatga oladi yoki username ini yangilaydi.

    Ro'yxatdan o'tgandan keyin ismni Telegram'dan qayta yozmaymiz — klient o'zi kiritgan ism qoladi.
    """
    return await pool().fetchrow(
        """
        INSERT INTO users (telegram_id, full_name, username)
        VALUES ($1, $2, $3)
        ON CONFLICT (telegram_id) DO UPDATE
            SET username  = EXCLUDED.username,
                full_name = CASE WHEN users.registered_at IS NULL THEN EXCLUDED.full_name
                                 ELSE users.full_name END
        RETURNING *
        """,
        telegram_id, full_name, username,
    )


async def get_user(telegram_id: int) -> asyncpg.Record | None:
    return await pool().fetchrow("SELECT * FROM users WHERE telegram_id = $1", telegram_id)


async def set_lang(telegram_id: int, lang: str) -> None:
    await pool().execute("UPDATE users SET lang = $2 WHERE telegram_id = $1", telegram_id, lang)


async def is_blocked(telegram_id: int) -> bool:
    row = await pool().fetchval("SELECT is_blocked FROM users WHERE telegram_id = $1", telegram_id)
    return bool(row)


async def set_phone(telegram_id: int, phone: str) -> None:
    await pool().execute("UPDATE users SET phone = $2 WHERE telegram_id = $1", telegram_id, phone)


async def complete_registration(telegram_id: int, full_name: str, phone: str, role: str) -> asyncpg.Record:
    """Market ro'yxatdan o'tishini yakunlaydi (yoki profilni yangilaydi)."""
    return await pool().fetchrow(
        """
        UPDATE users
           SET full_name = $2, phone = $3, role = $4,
               registered_at = COALESCE(registered_at, NOW())
         WHERE telegram_id = $1
        RETURNING *
        """,
        telegram_id, full_name, phone, role,
    )


async def list_users(offset: int = 0, limit: int = 10, blocked: bool | None = None,
                     q: str | None = None) -> list[asyncpg.Record]:
    """Klientlar ro'yxati. `q` — ism, username yoki telegram_id bo'yicha qidiruv."""
    conds: list[str] = []
    args: list[Any] = [limit, offset]
    if blocked is not None:
        args.append(blocked)
        conds.append(f"is_blocked = ${len(args)}")
    if q:
        args.append(f"%{q.strip()}%")
        conds.append(f"(full_name ILIKE ${len(args)} OR username ILIKE ${len(args)} "
                     f"OR telegram_id::text LIKE ${len(args)})")
    where = f"WHERE {' AND '.join(conds)}" if conds else ""
    return await pool().fetch(
        f"SELECT * FROM users {where} ORDER BY created_at DESC LIMIT $1 OFFSET $2", *args
    )


async def count_users(blocked: bool | None = None) -> int:
    if blocked is None:
        return await pool().fetchval("SELECT COUNT(*) FROM users")
    return await pool().fetchval("SELECT COUNT(*) FROM users WHERE is_blocked = $1", blocked)


async def block_user(telegram_id: int, reason: str | None = None) -> bool:
    status = await pool().execute(
        "UPDATE users SET is_blocked = TRUE, block_reason = $2, blocked_at = NOW() WHERE telegram_id = $1",
        telegram_id, reason,
    )
    return status.endswith(" 1")


async def unblock_user(telegram_id: int) -> bool:
    status = await pool().execute(
        "UPDATE users SET is_blocked = FALSE, block_reason = NULL, blocked_at = NULL WHERE telegram_id = $1",
        telegram_id,
    )
    return status.endswith(" 1")


# ---------------------------------------------------------------- ADMINS ---

def is_superadmin(telegram_id: int) -> bool:
    return telegram_id in config.admin_ids


async def is_admin(telegram_id: int) -> bool:
    """Superadmin (ADMIN_IDS) yoki admins jadvalidagi foydalanuvchi."""
    if is_superadmin(telegram_id):
        return True
    return bool(await pool().fetchval("SELECT 1 FROM admins WHERE telegram_id = $1", telegram_id))


async def all_admin_ids() -> list[int]:
    rows = await pool().fetch("SELECT telegram_id FROM admins")
    return sorted(set(config.admin_ids) | {r["telegram_id"] for r in rows})


async def list_admins() -> list[asyncpg.Record]:
    return await pool().fetch(
        """
        SELECT a.telegram_id, a.note, a.added_by, a.created_at, u.full_name, u.username
          FROM admins a LEFT JOIN users u ON u.telegram_id = a.telegram_id
         ORDER BY a.created_at
        """
    )


async def add_admin(telegram_id: int, added_by: int, note: str | None = None) -> None:
    await pool().execute(
        """
        INSERT INTO admins (telegram_id, added_by, note) VALUES ($1, $2, $3)
        ON CONFLICT (telegram_id) DO UPDATE SET note = COALESCE(EXCLUDED.note, admins.note)
        """,
        telegram_id, added_by, note,
    )


async def remove_admin(telegram_id: int) -> bool:
    status = await pool().execute("DELETE FROM admins WHERE telegram_id = $1", telegram_id)
    return status.endswith(" 1")


# ---------------------------------------------------------------- HOUSES ---

def to_uzs(price: Decimal, currency: str) -> Decimal:
    return price * config.usd_rate if currency == "USD" else price


async def add_house(
    *,
    title: str,
    address: str,
    rooms: int | None,
    price: Decimal,
    description: str,
    photo_file_id: str | None,
    contact_phone: str | None,
    created_by: int,
    district: str | None = None,
    photo_file_ids: list[str] | None = None,
    currency: str = "UZS",
    area: Decimal | None = None,
    floor: int | None = None,
    floors: int | None = None,
    owner_id: int | None = None,
    status: str = "approved",
) -> int:
    """Admin yoki klient qo'shgan uy. Rasmlar Telegram file_id (photo_urls da tg: prefiksi bilan)."""
    ids = list(photo_file_ids or [])
    if photo_file_id and photo_file_id not in ids:
        ids.insert(0, photo_file_id)
    return await pool().fetchval(
        """
        INSERT INTO houses (title, address, rooms, price, currency, price_uzs, description,
                            photo_file_id, photo_urls, contact_phone, created_by, district,
                            area, floor, floors, owner_id, status, source, last_seen_at)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, 'admin', NOW())
        RETURNING id
        """,
        title, address, rooms, price, currency, to_uzs(price, currency), description,
        ids[0] if ids else None, [f"tg:{i}" for i in ids], contact_phone, created_by, district,
        area, floor, floors, owner_id, status,
    )


async def upsert_external_house(source: str, source_id: str, d: dict[str, Any]) -> tuple[int, bool]:
    """Tashqi manbadan kelgan e'lonni qo'shadi yoki yangilaydi. (id, yangi_qo'shildimi) qaytaradi."""
    price: Decimal = d["price"]
    row = await pool().fetchrow(
        """
        INSERT INTO houses (title, address, rooms, price, currency, price_uzs, description,
                            contact_phone, district, area, floor, floors, photo_urls,
                            seller_name, seller_username, lat, lon, external_created_at,
                            source, source_id, source_url, last_seen_at, is_active, views, status)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18,
                $19, $20, $21, NOW(), TRUE, $22, 'approved')
        ON CONFLICT (source, source_id) WHERE source_id IS NOT NULL DO UPDATE SET
            title = EXCLUDED.title, address = EXCLUDED.address, rooms = EXCLUDED.rooms,
            price = EXCLUDED.price, currency = EXCLUDED.currency, price_uzs = EXCLUDED.price_uzs,
            description = EXCLUDED.description, contact_phone = EXCLUDED.contact_phone,
            district = EXCLUDED.district, area = EXCLUDED.area, floor = EXCLUDED.floor,
            floors = EXCLUDED.floors, photo_urls = EXCLUDED.photo_urls,
            seller_name = EXCLUDED.seller_name, seller_username = EXCLUDED.seller_username,
            lat = EXCLUDED.lat, lon = EXCLUDED.lon, external_created_at = EXCLUDED.external_created_at,
            source_url = EXCLUDED.source_url, last_seen_at = NOW(),
            is_active = NOT houses.admin_hidden,
            views = GREATEST(houses.views, EXCLUDED.views),
            updated_at = NOW()
        RETURNING id, (xmax = 0) AS inserted
        """,
        d["title"], d["address"], d.get("rooms"), price, d["currency"], to_uzs(price, d["currency"]),
        d.get("description", ""), d.get("contact_phone"), d.get("district"), d.get("area"),
        d.get("floor"), d.get("floors"), d.get("photo_urls", []), d.get("seller_name"),
        d.get("seller_username"), d.get("lat"), d.get("lon"), d.get("external_created_at"),
        source, source_id, d.get("source_url"), d.get("views", 0),
    )
    return row["id"], bool(row["inserted"])


async def external_snapshot(source: str) -> dict[str, tuple[Decimal, str]]:
    rows = await pool().fetch(
        "SELECT source_id, price, title FROM houses WHERE source = $1 AND source_id IS NOT NULL", source
    )
    return {r["source_id"]: (r["price"], r["title"]) for r in rows}


async def touch_seen(source: str, source_ids: list[str]) -> None:
    if source_ids:
        await pool().execute(
            "UPDATE houses SET last_seen_at = NOW() WHERE source = $1 AND source_id = ANY($2::text[])",
            source, source_ids,
        )


async def deactivate_missing(source: str, seen_ids: list[str]) -> int:
    status = await pool().execute(
        """
        UPDATE houses SET is_active = FALSE, updated_at = NOW()
         WHERE source = $1 AND source_id IS NOT NULL AND is_active
           AND NOT (source_id = ANY($2::text[]))
        """,
        source, seen_ids,
    )
    return int(status.split()[-1])


async def get_house(house_id: int, viewer_id: int = 0) -> asyncpg.Record | None:
    return await pool().fetchrow(_HOUSE_SELECT + "WHERE h.id = $2", viewer_id, house_id)


async def list_houses(offset: int = 0, limit: int = 10, only_active: bool = True,
                      source: str | None = None, status: str | None = None,
                      viewer_id: int = 0) -> list[asyncpg.Record]:
    """Admin uchun ro'yxat (moderatsiyadagilar oldinda)."""
    conds: list[str] = []
    args: list[Any] = [viewer_id, limit, offset]
    if only_active:
        conds.append(PUBLIC_COND)
    if source:
        args.append(source)
        conds.append(f"h.source = ${len(args)}")
    if status:
        args.append(status)
        conds.append(f"h.status = ${len(args)}")
    where = f"WHERE {' AND '.join(conds)}" if conds else ""
    return await pool().fetch(
        _HOUSE_SELECT + f"{where} ORDER BY (h.status = 'pending') DESC, h.created_at DESC LIMIT $2 OFFSET $3",
        *args,
    )


async def count_houses(only_active: bool = True) -> int:
    where = f"WHERE {PUBLIC_COND}" if only_active else ""
    return await pool().fetchval(f"SELECT COUNT(*) FROM houses h {where}")


async def count_pending() -> int:
    return await pool().fetchval("SELECT COUNT(*) FROM houses WHERE status = 'pending'")


async def delete_house(house_id: int) -> bool:
    status = await pool().execute("DELETE FROM houses WHERE id = $1", house_id)
    return status.endswith(" 1")


async def set_house_active(house_id: int, active: bool) -> bool:
    status = await pool().execute(
        """
        UPDATE houses
           SET is_active = $2,
               admin_hidden = CASE WHEN source <> 'admin' THEN NOT $2 ELSE admin_hidden END,
               updated_at = NOW()
         WHERE id = $1
        """,
        house_id, active,
    )
    return status.endswith(" 1")


async def set_house_status(house_id: int, status: str, reason: str | None, moderated_by: int) -> asyncpg.Record | None:
    """Moderatsiya: pending -> approved / rejected."""
    return await pool().fetchrow(
        """
        UPDATE houses
           SET status = $2, reject_reason = $3, moderated_by = $4, moderated_at = NOW(), updated_at = NOW()
         WHERE id = $1
        RETURNING *
        """,
        house_id, status, reason, moderated_by,
    )


async def my_houses(owner_id: int) -> list[asyncpg.Record]:
    return await pool().fetch(
        _HOUSE_SELECT + "WHERE h.owner_id = $1 ORDER BY h.created_at DESC", owner_id
    )


async def delete_own_house(owner_id: int, house_id: int) -> bool:
    status = await pool().execute(
        "DELETE FROM houses WHERE id = $1 AND owner_id = $2", house_id, owner_id
    )
    return status.endswith(" 1")


async def stats() -> dict[str, Any]:
    row = await pool().fetchrow(
        """
        SELECT
            (SELECT COUNT(*) FROM users)                                 AS users_total,
            (SELECT COUNT(*) FROM users WHERE is_blocked)                AS users_blocked,
            (SELECT COUNT(*) FROM users WHERE registered_at IS NOT NULL) AS users_registered,
            (SELECT COUNT(*) FROM houses)                                AS houses_total,
            (SELECT COUNT(*) FROM houses h WHERE %s)                     AS houses_active,
            (SELECT COUNT(*) FROM houses WHERE source = 'admin' AND owner_id IS NULL) AS houses_admin,
            (SELECT COUNT(*) FROM houses WHERE owner_id IS NOT NULL)     AS houses_clients,
            (SELECT COUNT(*) FROM houses WHERE source = 'joymee')        AS houses_joymee,
            (SELECT COUNT(*) FROM houses WHERE status = 'pending')       AS houses_pending,
            (SELECT COUNT(*) FROM favorites)                             AS favorites_total,
            (SELECT COUNT(*) FROM admins)                                AS admins_total
        """ % PUBLIC_COND
    )
    out = dict(row)
    out["last_sync"] = await last_sync()
    return out


# ---------------------------------------------------------------- MARKET ---

async def market_houses(
    *,
    viewer_id: int,
    q: str | None = None,
    rooms: int | None = None,
    price_min: Decimal | None = None,
    price_max: Decimal | None = None,
    district: str | None = None,
    source: str | None = None,
    sort: str = "new",
    offset: int = 0,
    limit: int = 20,
) -> list[asyncpg.Record]:
    conds = [PUBLIC_COND]
    args: list[Any] = [viewer_id, limit, offset]
    if q:
        args.append(f"%{q.strip()}%")
        conds.append(f"(h.title ILIKE ${len(args)} OR h.address ILIKE ${len(args)} "
                     f"OR h.description ILIKE ${len(args)} OR h.district ILIKE ${len(args)})")
    if rooms:
        args.append(rooms)
        conds.append(f"h.rooms >= ${len(args)}" if rooms >= 4 else f"h.rooms = ${len(args)}")
    if price_min is not None:
        args.append(price_min)
        conds.append(f"h.price_uzs >= ${len(args)}")
    if price_max is not None:
        args.append(price_max)
        conds.append(f"h.price_uzs <= ${len(args)}")
    if district:
        args.append(district)
        conds.append(f"h.district = ${len(args)}")
    if source:
        args.append(source)
        conds.append(f"h.source = ${len(args)}")
    order = {
        "cheap": "h.price_uzs ASC NULLS LAST, h.created_at DESC",
        "expensive": "h.price_uzs DESC NULLS LAST, h.created_at DESC",
        "popular": "h.views DESC, h.created_at DESC",
    }.get(sort, "COALESCE(h.external_created_at, h.created_at) DESC")
    return await pool().fetch(
        _HOUSE_SELECT + f"WHERE {' AND '.join(conds)} ORDER BY {order} LIMIT $2 OFFSET $3", *args
    )


async def increment_views(house_id: int) -> None:
    await pool().execute("UPDATE houses SET views = views + 1 WHERE id = $1", house_id)


async def districts() -> list[str]:
    rows = await pool().fetch(
        f"""
        SELECT district FROM houses h
         WHERE district IS NOT NULL AND district <> '' AND {PUBLIC_COND}
         GROUP BY district ORDER BY COUNT(*) DESC, district
        """
    )
    return [r["district"] for r in rows]


async def toggle_favorite(user_id: int, house_id: int) -> bool:
    deleted = await pool().execute(
        "DELETE FROM favorites WHERE user_id = $1 AND house_id = $2", user_id, house_id
    )
    if deleted.endswith(" 1"):
        return False
    await pool().execute(
        "INSERT INTO favorites (user_id, house_id) VALUES ($1, $2) ON CONFLICT DO NOTHING", user_id, house_id
    )
    return True


async def list_favorites(user_id: int) -> list[asyncpg.Record]:
    return await pool().fetch(
        _HOUSE_SELECT + f"""
          JOIN favorites f2 ON f2.house_id = h.id AND f2.user_id = $1
         WHERE {PUBLIC_COND}
         ORDER BY f2.created_at DESC
        """,
        user_id,
    )


# -------------------------------------------------------------- SYNC LOG ---

async def sync_started(source: str) -> int:
    return await pool().fetchval("INSERT INTO sync_log (source) VALUES ($1) RETURNING id", source)


async def sync_finished(log_id: int, *, added: int, updated: int, deactivated: int, seen: int,
                        error: str | None = None) -> None:
    await pool().execute(
        """
        UPDATE sync_log SET finished_at = NOW(), added = $2, updated = $3, deactivated = $4,
                            seen = $5, error = $6
         WHERE id = $1
        """,
        log_id, added, updated, deactivated, seen, error,
    )


async def last_sync(source: str = "joymee") -> dict[str, Any] | None:
    row = await pool().fetchrow(
        "SELECT * FROM sync_log WHERE source = $1 ORDER BY started_at DESC LIMIT 1", source
    )
    if row is None:
        return None
    d = dict(row)
    for k in ("started_at", "finished_at"):
        if d[k] is not None:
            d[k] = d[k].isoformat()
    return d
