"""Instagram'ga e'lon chiqarish (qo'lda): PostgreSQL'dagi e'lon -> Instagram post -> instagram_posts holati.

Ishlatish (loyiha papkasidan):
  python scripts/ig_post.py                      # nomzodlar ro'yxati + post matni (HECH NARSA CHIQMAYDI)
  python scripts/ig_post.py --house 123          # bitta e'lonni ko'rish
  python scripts/ig_post.py --check-images       # rasm havolalari ochilishini va JPEG ekanini tekshirish
  python scripts/ig_post.py --house 123 --publish   # haqiqatan Instagram'ga chiqarish
  python scripts/ig_post.py --status             # instagram_posts jadvali

Sozlamalar .env dan: IG_ACCESS_TOKEN, IG_ACCOUNT_ID, DATABASE_URL, PUBLIC_BASE_URL (yoki WEBAPP_URL).
Instagram rasmni ochiq serverdan (Render) yuklaydi, shuning uchun DATABASE_URL server ishlatadigan baza
(Neon) bo'lishi kerak — aks holda e'lon raqamlari mos kelmaydi.
"""
from __future__ import annotations

import argparse
import asyncio
import io
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import aiohttp  # noqa: E402

from bot import db, instagram  # noqa: E402
from bot.config import config  # noqa: E402


async def check_image(session: aiohttp.ClientSession, url: str) -> str:
    from PIL import Image

    async with session.get(url, timeout=aiohttp.ClientTimeout(total=90)) as r:
        body = await r.read()
        if r.status != 200:
            return f"HTTP {r.status}"
        ctype = r.headers.get("Content-Type", "")
    with Image.open(io.BytesIO(body)) as im:
        ratio = im.width / im.height
        ok = im.format == "JPEG" and instagram.MIN_RATIO - 0.01 <= ratio <= instagram.MAX_RATIO + 0.01
        return f"{'OK' if ok else 'XATO'} {im.format} {im.width}x{im.height} nisbat {ratio:.2f} {len(body) // 1024} KB ({ctype})"


async def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--house", type=int, help="faqat shu e'lon (id)")
    ap.add_argument("--limit", type=int, default=5)
    ap.add_argument("--sources", help="vergul bilan, masalan admin,uybor (default IG_SOURCES)")
    ap.add_argument("--max-age-days", type=int, help="0 = cheklovsiz (default IG_MAX_AGE_DAYS)")
    ap.add_argument("--retry", action="store_true", help="xato bilan tugaganlarini ham qayta urinish")
    ap.add_argument("--check-images", action="store_true", help="rasm havolalarini yuklab tekshirish")
    ap.add_argument("--publish", action="store_true", help="HAQIQATAN Instagram'ga chiqarish")
    ap.add_argument("--status", action="store_true", help="instagram_posts jadvalini ko'rsatish")
    a = ap.parse_args()

    if not config.ig_enabled:
        print("IG_ACCESS_TOKEN / IG_ACCOUNT_ID .env da yo'q.")
        return 2
    await db.init_db()
    try:
        if a.status:
            rows = await db.pool().fetch("SELECT * FROM instagram_posts ORDER BY updated_at DESC LIMIT 30")
            for r in rows:
                print(f"#{r['house_id']} {r['status']:<10} urinish={r['attempts']} {r['permalink'] or ''} {r['error'] or ''}")
            print(f"jami ko'rsatildi: {len(rows)}")
            return 0

        sources = tuple(s.strip() for s in a.sources.split(",")) if a.sources else config.ig_sources
        age = config.ig_max_age_days if a.max_age_days is None else (a.max_age_days or None)
        houses = await db.ig_candidates(sources, age, 1 if a.house else a.limit, a.house, a.retry)
        if not houses:
            print(f"Nomzod yo'q (manbalar: {', '.join(sources)}; yosh: {age or 'cheklovsiz'} kun). "
                  "E'lon ochiq, rasmli va hali chiqmagan bo'lishi kerak.")
            return 1

        async with aiohttp.ClientSession() as session:
            for h in houses:
                refs = instagram.photo_refs(h)
                n = min(len(refs), instagram.MAX_CAROUSEL)
                print("=" * 70)
                print(f"#{h['id']}  manba={h['source']}  rasmlar={len(refs)} -> post: "
                      f"{'karusel ' + str(n) if n > 1 else '1 rasm'}  holat={h['ig_status'] or 'yangi'}")
                print("-" * 70)
                print(instagram.build_caption(h))
                print("-" * 70)
                if a.check_images:
                    for i in range(n):
                        print(f"  rasm {i}: {await check_image(session, instagram.image_url(h['id'], i, ttl=600))}")
                if a.publish:
                    try:
                        res = await instagram.publish_house(h)
                        print(f"  CHIQDI: {res['permalink'] or res['media_id']}")
                    except Exception as exc:  # noqa: BLE001
                        print(f"  XATO: {exc}")
                    row = await db.ig_get(h["id"])
                    print(f"  bazada: status={row['status']} media_id={row['media_id']} urinish={row['attempts']}")
        if not a.publish:
            print("\n(Ko'rish rejimi — hech narsa chiqmadi. Chiqarish uchun --publish qo'shing.)")
        return 0
    finally:
        await db.close_db()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
