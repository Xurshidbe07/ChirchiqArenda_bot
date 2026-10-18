from pathlib import Path
import asyncpg

pool: asyncpg.Pool | None = None


async def init_db(dsn: str) -> None:
    global pool
    pool = await asyncpg.create_pool(dsn, min_size=1, max_size=10)
    schema = (Path(__file__).parent / "schema.sql").read_text(encoding="utf-8")
    async with pool.acquire() as conn:
        await conn.execute(schema)


async def get_user(telegram_id: int):
    async with pool.acquire() as conn:
        return await conn.fetchrow(
            "SELECT * FROM users WHERE telegram_id = $1", telegram_id
        )


async def set_lang(telegram_id: int, lang: str) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE users SET lang = $2, updated_at = NOW() WHERE telegram_id = $1",
            telegram_id, lang,
        )


async def save_user(telegram_id: int, username: str | None, d: dict) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO users (telegram_id, username, full_name, phone, role, region, district, lang)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            ON CONFLICT (telegram_id) DO UPDATE SET
                username = EXCLUDED.username,
                full_name = EXCLUDED.full_name,
                phone = EXCLUDED.phone,
                role = EXCLUDED.role,
                region = EXCLUDED.region,
                district = EXCLUDED.district,
                lang = EXCLUDED.lang,
                updated_at = NOW()
            """,
            telegram_id, username, d["full_name"], d["phone"],
            d["role"], d["region"], d["district"], d["lang"],
        )
