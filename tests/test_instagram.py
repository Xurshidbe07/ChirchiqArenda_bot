"""Instagram avtopost: rasm tayyorlash, imzoli havola, post matni, nashr oqimi va bazadagi holat.

Graph API chaqiruvlari almashtiriladi (mock) — Instagram'ga hech narsa yuborilmaydi.
"""
from __future__ import annotations

import dataclasses
import io
import time
from decimal import Decimal

import pytest
from PIL import Image

from bot import db, instagram
from bot.config import config
from tests.conftest import Server, cleanup_ids, run

OWNER = 900000201


def _png(w: int, h: int) -> bytes:
    buf = io.BytesIO()
    Image.new("RGBA", (w, h), (200, 30, 30, 255)).save(buf, "PNG")
    return buf.getvalue()


def _size(jpeg: bytes) -> tuple[int, int, str]:
    with Image.open(io.BytesIO(jpeg)) as im:
        return im.width, im.height, im.format


@pytest.fixture(autouse=True)
def _ig_config(monkeypatch):
    cfg = dataclasses.replace(config, ig_access_token="test-ig-token", ig_account_id="17800000000000000",
                              public_base_url="https://example.test")
    monkeypatch.setattr(instagram, "config", cfg)
    yield cfg


def test_prepare_jpeg_fits_instagram_ratio():
    w, h, fmt = _size(instagram.prepare_jpeg(_png(300, 900)))        # 1:3 telefon rasmi
    assert fmt == "JPEG" and w >= 320 and abs(w / h - 0.8) < 0.01
    w, h, fmt = _size(instagram.prepare_jpeg(_png(3000, 600)))       # panorama
    assert w == 1440 and abs(w / h - 1.91) < 0.01
    w, h, _ = _size(instagram.prepare_jpeg(_png(1000, 1000)))        # kvadrat o'zgarmaydi
    assert (w, h) == (1000, 1000)


def test_signed_image_link():
    url = instagram.image_url(42, 1)
    assert url.startswith("https://example.test/ig/img/42/1.jpg?exp=")
    exp = int(url.split("exp=")[1].split("&")[0])
    sig = url.split("sig=")[1]
    assert instagram.verify(42, 1, str(exp), sig)
    assert not instagram.verify(43, 1, str(exp), sig)                # boshqa e'lon
    assert not instagram.verify(42, 2, str(exp), sig)                # boshqa rasm
    assert not instagram.verify(42, 1, str(exp + 1), sig)            # muddat o'zgartirilgan
    old = int(time.time()) - 10
    assert not instagram.verify(42, 1, str(old), instagram.sign(42, 1, old))  # muddati o'tgan


def test_caption():
    h = {"title": "Chilonzorda 2 xonali kvartira", "rent_period": "month", "price": Decimal("4500000"),
         "currency": "UZS", "rooms": 2, "area": Decimal("54.0"), "floor": 3, "floors": 9,
         "address": "Chilonzor 9-kvartal", "district": "Chilonzor tumani", "description": "Yaxshi ta'mirlangan. " * 200}
    c = instagram.build_caption(h)
    assert len(c) <= 2200
    assert "4 500 000 so'm / oy" in c and "2 xonali" in c and "54 m²" in c and "3/9 qavat" in c
    assert "t.me/" in c and "#chilonzor" in c and "Chilonzor tumani, Chilonzor 9-kvartal" in c
    c2 = instagram.build_caption({**h, "currency": "USD", "price": Decimal("350"), "rent_period": "day",
                                  "district": None, "description": "", "floor": None, "area": None})
    assert "$350 / kun" in c2 and "qavat" not in c2


async def _new_house(photos: list[str], **over) -> int:
    cols = {"title": "IG test uy", "address": "Chirchiq, test 1", "rooms": 2, "price": Decimal(300),
            "currency": "USD", "description": "pytest", "photo_urls": photos, "created_by": OWNER,
            "source": "admin", "status": "approved"}
    cols.update(over)
    keys = list(cols)
    return await db.pool().fetchval(
        f"INSERT INTO houses ({', '.join(keys)}) VALUES ({', '.join(f'${i + 1}' for i in range(len(keys)))}) RETURNING id",
        *cols.values())


def test_image_endpoint(monkeypatch):
    async def fake_fetch(bot, ref):
        assert ref == "https://cdn.example/a.png"
        return _png(300, 900)

    monkeypatch.setattr(instagram, "fetch_photo", fake_fetch)

    async def go():
        s = await Server().start()
        try:
            hid = await _new_house(["https://cdn.example/a.png"])
            url = instagram.image_url(hid, 0).replace("https://example.test", "")
            async with s._session.get(s.base + url) as r:
                body = await r.read()
                assert r.status == 200 and r.headers["Content-Type"] == "image/jpeg"
            w, h, fmt = _size(body)
            assert fmt == "JPEG" and abs(w / h - 0.8) < 0.01

            st, _ = await s.call("GET", url.replace("sig=", "sig=0"))
            assert st == 403                                          # imzo buzilgan
            st, _ = await s.call("GET", instagram.image_url(hid, 1).replace("https://example.test", ""))
            assert st == 404                                          # bunday rasm yo'q
            hidden = await _new_house(["https://cdn.example/a.png"], is_active=False)
            st, _ = await s.call("GET", instagram.image_url(hidden, 0).replace("https://example.test", ""))
            assert st == 404                                          # yashirilgan e'lon berilmaydi
        finally:
            await cleanup_ids(OWNER)
            await s.stop()

    run(go())


def test_publish_flow_updates_status(monkeypatch):
    calls: list[tuple[str, str, dict]] = []
    fail = {"on": False}

    async def fake_graph(session, method, path, **params):
        calls.append((method, path, params))
        if fail["on"] and path.endswith("/media_publish"):
            raise instagram.IgError("media_publish: test xatosi")
        if path.endswith("/media"):
            return {"id": f"c{len(calls)}"}
        if path.endswith("/media_publish"):
            return {"id": "m999"}
        if params.get("fields", "").startswith("status_code"):
            return {"status_code": "FINISHED"}
        if params.get("fields") == "permalink":
            return {"permalink": "https://www.instagram.com/p/TEST/"}
        raise AssertionError(path)

    monkeypatch.setattr(instagram, "_graph", fake_graph)

    async def go():
        await db.init_db()
        try:
            one = await _new_house(["tg:FILEID"])
            many = await _new_house(["https://cdn.example/1.jpg", "https://cdn.example/2.jpg", "tg:X"])
            nophoto = await _new_house([])

            cands = await db.ig_candidates(("admin",), 3, 50)
            ids = {h["id"] for h in cands}
            assert one in ids and many in ids and nophoto not in ids
            assert all(h["source"] == "uybor" for h in await db.ig_candidates(("uybor",), 3, 50))

            # 1 rasm -> oddiy post
            res = await instagram.publish_house(next(h for h in cands if h["id"] == one))
            assert res == {"house_id": one, "media_id": "m999", "permalink": "https://www.instagram.com/p/TEST/", "photos": 1}
            row = await db.ig_get(one)
            assert row["status"] == "published" and row["media_id"] == "m999" and row["published_at"] is not None
            media = [c for c in calls if c[1].endswith("/media")]
            assert len(media) == 1 and media[0][2]["image_url"].startswith("https://example.test/ig/img/")
            assert "caption" in media[0][2]

            # takror chiqmaydi
            with pytest.raises(instagram.IgError):
                await instagram.publish_house(next(h for h in cands if h["id"] == one))
            assert one not in {h["id"] for h in await db.ig_candidates(("admin",), 3, 50)}

            # 3 rasm -> karusel (3 bola + 1 ota konteyner), publish xatosi -> failed
            calls.clear()
            fail["on"] = True
            with pytest.raises(instagram.IgError):
                await instagram.publish_house(next(h for h in cands if h["id"] == many))
            media = [c for c in calls if c[1].endswith("/media")]
            assert len(media) == 4 and media[-1][2]["media_type"] == "CAROUSEL"
            assert sum(1 for c in media if c[2].get("is_carousel_item") == "true") == 3
            row = await db.ig_get(many)
            assert row["status"] == "failed" and "test xatosi" in row["error"] and row["attempts"] == 1

            # failed -> faqat --retry bilan qayta nomzod, qayta urinishda chiqadi
            assert many not in {h["id"] for h in await db.ig_candidates(("admin",), 3, 50)}
            retry = await db.ig_candidates(("admin",), 3, 50, many, True)
            fail["on"] = False
            await instagram.publish_house(retry[0])
            row = await db.ig_get(many)
            assert row["status"] == "published" and row["attempts"] == 2 and row["error"] is None
        finally:
            await cleanup_ids(OWNER)
            await db.close_db()

    run(go())
