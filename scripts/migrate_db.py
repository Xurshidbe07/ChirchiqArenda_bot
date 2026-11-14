"""Render PostgreSQL -> Neon PostgreSQL ko'chirish.

Ishlatish:  python scripts/migrate_db.py [--check]
Manzillar .env.migrate faylidan olinadi (RENDER_DB_URL, NEON_DB_URL) — parollar ekranga chiqmaydi.

  --check   faqat ikkala bazaga ulanib, jadval qatorlari sonini ko'rsatadi
  (default) pg_dump (Render) -> pg_restore (Neon), keyin qatorlar sonini solishtiradi.
            Neon'dagi mavjud jadvallar tozalanib qayta yoziladi (--clean --if-exists).
"""
from __future__ import annotations

import asyncio
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import asyncpg

ROOT = Path(__file__).resolve().parent.parent
PG_BIN = Path(os.getenv("PG_BIN", r"C:\Program Files\PostgreSQL\18\bin"))
TABLES = ("users", "houses", "favorites", "admins", "sync_log", "scrape_skip")


def load_urls() -> tuple[str, str]:
    env = {}
    for line in (ROOT / ".env.migrate").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip().strip('"').strip("'")
    src, dst = env.get("RENDER_DB_URL", ""), env.get("NEON_DB_URL", "")
    if not src or not dst:
        sys.exit(".env.migrate da RENDER_DB_URL va NEON_DB_URL to'ldirilmagan.")
    if "neon.tech" not in dst:
        sys.exit("NEON_DB_URL Neon manziliga o'xshamaydi (neon.tech yo'q).")
    if "sslmode" not in dst:
        dst += ("&" if "?" in dst else "?") + "sslmode=require"
    if "sslmode" not in src:
        src += ("&" if "?" in src else "?") + "sslmode=require"
    return src, dst


def masked(url: str) -> str:
    return re.sub(r"://([^:]+):[^@]*@", r"://\1:***@", url).split("?")[0]


async def counts(url: str) -> dict[str, int | None]:
    conn = await asyncpg.connect(url, timeout=30)
    try:
        out: dict[str, int | None] = {"_server": await conn.fetchval("SHOW server_version")}
        for t in TABLES:
            exists = await conn.fetchval("SELECT to_regclass($1)", f"public.{t}")
            out[t] = await conn.fetchval(f"SELECT COUNT(*) FROM {t}") if exists else None
        return out
    finally:
        await conn.close()


def run(cmd: list[str]) -> None:
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        # xato matnida parol bo'lmasligi uchun manzillarni yashiramiz
        err = re.sub(r"postgres(?:ql)?://\S+", "<url>", r.stderr)
        sys.exit(f"{Path(cmd[0]).name} xato ({r.returncode}):\n{err[-2000:]}")


def main() -> None:
    src, dst = load_urls()
    print("Manba (Render):", masked(src))
    print("Maqsad (Neon): ", masked(dst))
    before_src = asyncio.run(counts(src))
    before_dst = asyncio.run(counts(dst))
    print("Render:", before_src)
    print("Neon:  ", before_dst)
    if "--check" in sys.argv:
        return

    with tempfile.TemporaryDirectory() as tmp:
        dump = str(Path(tmp) / "chirchiq.dump")
        print("pg_dump (Render) ...")
        run([str(PG_BIN / "pg_dump.exe"), "--format=custom", "--no-owner", "--no-privileges", "--file", dump, src])
        print("pg_restore (Neon) ...")
        run([str(PG_BIN / "pg_restore.exe"), "--clean", "--if-exists", "--no-owner", "--no-privileges",
             "--single-transaction", "--dbname", dst, dump])

    after = asyncio.run(counts(dst))
    print("Neon (keyin):", after)
    bad = [t for t in TABLES if before_src.get(t) is not None and after.get(t) != before_src.get(t)]
    if bad:
        sys.exit(f"MOS EMAS: {bad}")
    print("OK: barcha jadvallar qatorlari soni mos.")


if __name__ == "__main__":
    main()
