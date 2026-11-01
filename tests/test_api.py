"""Mini App API testlari: JWT, admin panel, market, rollar, moderatsiya.

Ishga tushirish:  pytest -q
Kerak: ishlayotgan PostgreSQL (DATABASE_URL). Telegram'ga so'rov yuborilmaydi.
"""
from __future__ import annotations

import aiohttp

from bot.auth import make_admin_token
from tests.conftest import JSON, SUPER_ID, Server, cleanup_ids, headers_for, run

CLIENT = 900000101
ADMIN2 = 900000102
OTHER = 900000103


def _house_form(**over) -> aiohttp.FormData:
    d = dict(title="Test uy", address="Chirchiq, test ko'chasi 1", rooms="2", price="300", currency="USD",
             description="pytest", floor="3", floors="5", area="52.5")
    d.update(over)
    f = aiohttp.FormData()
    for k, v in d.items():
        f.add_field(k, v)
    return f


# ------------------------------------------------------------------ JWT ---

def test_admin_page_and_api_require_jwt():
    async def go():
        s = await Server().start()
        try:
            good = make_admin_token(SUPER_ID)
            expired = make_admin_token(SUPER_ID, hours=-1)
            other = make_admin_token(OTHER)
            assert (await s.call("GET", "/"))[0] == 404
            assert (await s.call("GET", "/admin"))[0] == 403
            assert (await s.call("GET", "/admin?t=a.b.c"))[0] == 403
            assert (await s.call("GET", "/admin?t=" + expired))[0] == 403
            assert (await s.call("GET", "/admin?t=" + good))[0] == 200
            assert (await s.call("GET", "/health"))[0] == 200
            assert (await s.call("GET", "/market"))[0] == 200

            st, body = await s.call("GET", "/api/me", headers=headers_for(SUPER_ID))
            assert st == 401 and body == "TOKEN_REQUIRED"
            st, body = await s.call("GET", "/api/me", headers=headers_for(SUPER_ID, jwt=expired))
            assert st == 401 and body == "TOKEN_EXPIRED"
            st, body = await s.call("GET", "/api/me", headers=headers_for(SUPER_ID, jwt=other))
            assert st == 403 and body == "TOKEN_OTHER_USER"
            st, me = await s.call("GET", "/api/me", headers=headers_for(SUPER_ID, jwt=good))
            assert st == 200 and me["is_superadmin"] is True
            # tokeni bor, lekin admin emas
            st, _ = await s.call("GET", "/api/me", headers=headers_for(OTHER, jwt=other))
            assert st == 403
            # initData yo'q / buzilgan
            assert (await s.call("GET", "/api/me"))[0] == 401
            bad = headers_for(SUPER_ID, jwt=good)
            bad["Authorization"] = bad["Authorization"][:-4] + "dead"
            assert (await s.call("GET", "/api/me", headers=bad))[0] == 401
        finally:
            await cleanup_ids(OTHER)
            await s.stop()

    run(go())


# ---------------------------------------------------- admin: uylar, klientlar ---

def test_admin_house_crud_and_market_visibility():
    async def go():
        s = await Server().start()
        A = headers_for(SUPER_ID, jwt=make_admin_token(SUPER_ID))
        C = headers_for(CLIENT, "Klient")
        try:
            st, h = await s.call("POST", "/api/houses", headers=A, data=_house_form(title="Admin uyi", currency="UZS", price="2 500 000"))
            assert st == 201 and h["status"] == "approved" and h["price_uzs"] == 2500000 and h["source"] == "admin"
            hid = h["id"]
            st, _ = await s.call("POST", "/api/houses", headers=A, data=_house_form(rooms="0"))
            assert st == 400

            st, feed = await s.call("GET", "/api/market/houses?q=Admin uyi", headers=C)
            assert st == 200 and any(x["id"] == hid for x in feed["items"])
            st, det = await s.call("GET", f"/api/market/houses/{hid}", headers=C)
            assert st == 200 and det["title"] == "Admin uyi"

            st, p = await s.call("PATCH", f"/api/houses/{hid}", headers={**A, **JSON}, json={"is_active": False})
            assert st == 200 and p["is_active"] is False
            st, _ = await s.call("GET", f"/api/market/houses/{hid}", headers=C)
            assert st == 404  # yashirilgan uy klientga ko'rinmaydi
            st, _ = await s.call("PATCH", f"/api/houses/{hid}", headers={**A, **JSON}, json={"is_active": True})
            assert st == 200

            st, lst = await s.call("GET", "/api/houses?source=admin", headers=A)
            assert st == 200 and any(x["id"] == hid for x in lst)
            st, stats = await s.call("GET", "/api/stats", headers=A)
            assert st == 200 and stats["houses_total"] >= 1 and "last_sync" in stats

            st, _ = await s.call("DELETE", f"/api/houses/{hid}", headers=A)
            assert st == 200
            st, _ = await s.call("DELETE", f"/api/houses/{hid}", headers=A)
            assert st == 404
        finally:
            await cleanup_ids(CLIENT)
            await s.stop()

    run(go())


def test_admin_blocks_client_and_blocked_client_is_rejected():
    async def go():
        s = await Server().start()
        A = headers_for(SUPER_ID, jwt=make_admin_token(SUPER_ID))
        C = headers_for(CLIENT, "Klient")
        try:
            assert (await s.call("GET", "/api/market/me", headers=C))[0] == 200  # bazaga yoziladi
            st, users = await s.call("GET", f"/api/users?q={CLIENT}", headers=A)
            assert st == 200 and any(u["telegram_id"] == CLIENT for u in users["items"])
            st, u = await s.call("POST", f"/api/users/{CLIENT}/block", headers={**A, **JSON}, json={"reason": "spam"})
            assert st == 200 and u["is_blocked"] and u["block_reason"] == "spam"
            assert (await s.call("GET", "/api/market/houses", headers=C))[0] == 403
            st, _ = await s.call("POST", f"/api/users/{SUPER_ID}/block", headers={**A, **JSON}, json={})
            assert st == 400  # o'zini bloklay olmaydi
            st, u = await s.call("POST", f"/api/users/{CLIENT}/unblock", headers=A)
            assert st == 200 and u["is_blocked"] is False
            assert (await s.call("GET", "/api/market/houses", headers=C))[0] == 200
        finally:
            await cleanup_ids(CLIENT)
            await s.stop()

    run(go())


# ------------------------------------------------- market: ro'yxat, e'lon, sevimli ---

def test_market_registration_posting_and_favorites():
    async def go():
        s = await Server().start()
        C = headers_for(CLIENT, "Klient", "ru")
        try:
            st, me = await s.call("GET", "/api/market/me", headers=C)
            assert st == 200 and me["registered"] is False and me["lang"] == "ru"
            st, _ = await s.call("POST", "/api/market/lang", headers={**C, **JSON}, json={"lang": "en"})
            assert st == 200
            st, me = await s.call("GET", "/api/market/me", headers=C)
            assert me["lang"] == "en"
            assert (await s.call("POST", "/api/market/lang", headers={**C, **JSON}, json={"lang": "fr"}))[0] == 400

            st, body = await s.call("POST", "/api/market/my", headers=C, data=_house_form())
            assert st == 403 and "REGISTER_REQUIRED" in body
            st, body = await s.call("POST", "/api/market/register", headers={**C, **JSON},
                                    json={"full_name": "Sinov", "role": "tenant", "phone": "12345"})
            assert st == 400 and "PHONE_INVALID" in body
            st, u = await s.call("POST", "/api/market/register", headers={**C, **JSON},
                                 json={"full_name": "Sinov Klient", "role": "landlord", "phone": "90 123 45 67"})
            assert st == 200 and u["registered"] and u["phone"] == "+998901234567"

            st, ad = await s.call("POST", "/api/market/my", headers=C, data=_house_form(title="Klient uyi"))
            assert st == 201 and ad["currency"] == "USD" and ad["contact_phone"] == "+998901234567"
            assert ad["status"] in ("approved", "pending")
            st, mine = await s.call("GET", "/api/market/my", headers=C)
            assert st == 200 and [h["id"] for h in mine] == [ad["id"]]
            st, own = await s.call("GET", f"/api/market/houses/{ad['id']}", headers=C)
            assert st == 200  # egasi har doim ko'radi

            st, fav = await s.call("POST", f"/api/market/favorites/{ad['id']}", headers=C)
            assert st == 200 and fav["is_favorite"] is True
            st, favs = await s.call("GET", "/api/market/favorites", headers=C)
            assert st == 200 and (ad["status"] != "approved" or [h["id"] for h in favs] == [ad["id"]])
            st, fav = await s.call("POST", f"/api/market/favorites/{ad['id']}", headers=C)
            assert fav["is_favorite"] is False

            st, _ = await s.call("DELETE", f"/api/market/my/{ad['id']}", headers=C)
            assert st == 200
            assert (await s.call("DELETE", f"/api/market/my/{ad['id']}", headers=C))[0] == 404
            assert (await s.call("GET", "/api/market/districts", headers=C))[0] == 200
        finally:
            await cleanup_ids(CLIENT)
            await s.stop()

    run(go())


# ------------------------------------------------------ rollar va moderatsiya ---

def test_superadmin_manages_admins_and_moderation():
    async def go():
        s = await Server().start()
        S = headers_for(SUPER_ID, "Super", jwt=make_admin_token(SUPER_ID))
        A = headers_for(ADMIN2, "Admin2", jwt=make_admin_token(ADMIN2))
        C = headers_for(CLIENT, "Klient")
        try:
            assert (await s.call("GET", "/api/houses", headers=A))[0] == 403          # hali admin emas
            assert (await s.call("GET", "/api/admins", headers=C))[0] == 403
            assert (await s.call("GET", "/api/market/me", headers=A))[0] == 200       # botga /start ekvivalenti
            st, _ = await s.call("POST", "/api/admins", headers={**S, **JSON}, json={"telegram_id": 123})
            assert st == 400                                                           # botga yozmagan odam
            st, _ = await s.call("POST", "/api/admins", headers={**S, **JSON}, json={"telegram_id": ADMIN2, "note": "Jamoadosh"})
            assert st == 200
            st, lst = await s.call("GET", "/api/admins", headers=S)
            assert st == 200 and any(a["telegram_id"] == ADMIN2 for a in lst["items"])
            st, me = await s.call("GET", "/api/me", headers=A)
            assert st == 200 and me["is_superadmin"] is False
            assert (await s.call("GET", "/api/admins", headers=A))[0] == 403          # oddiy admin adminlarni boshqarmaydi
            assert (await s.call("POST", f"/api/users/{SUPER_ID}/block", headers={**A, **JSON}, json={}))[0] == 403

            # Klient e'loni + moderatsiya API (MODERATION o'chiq bo'lsa ham API ishlaydi)
            assert (await s.call("POST", "/api/market/register", headers={**C, **JSON},
                                 json={"full_name": "Sinov", "role": "tenant", "phone": "901112233"}))[0] == 200
            st, ad = await s.call("POST", "/api/market/my", headers=C, data=_house_form(title="Moderatsiya uyi"))
            assert st == 201
            st, rej = await s.call("POST", f"/api/houses/{ad['id']}/moderate", headers={**A, **JSON},
                                   json={"status": "rejected", "reason": "Rasm yo'q"})
            assert st == 200 and rej["status"] == "rejected" and rej["reject_reason"] == "Rasm yo'q"
            st, feed = await s.call("GET", "/api/market/houses?q=Moderatsiya uyi", headers=C)
            assert all(h["id"] != ad["id"] for h in feed["items"])
            st, mine = await s.call("GET", "/api/market/my", headers=C)
            assert mine[0]["status"] == "rejected" and mine[0]["reject_reason"] == "Rasm yo'q"
            st, ok = await s.call("POST", f"/api/houses/{ad['id']}/moderate", headers={**A, **JSON}, json={"status": "approved"})
            assert st == 200 and ok["status"] == "approved" and ok["reject_reason"] is None
            st, feed = await s.call("GET", "/api/market/houses?q=Moderatsiya uyi", headers=C)
            assert any(h["id"] == ad["id"] for h in feed["items"])
            assert (await s.call("POST", f"/api/houses/{ad['id']}/moderate", headers={**A, **JSON}, json={"status": "x"}))[0] == 400

            st, _ = await s.call("DELETE", f"/api/admins/{ADMIN2}", headers=S)
            assert st == 200
            assert (await s.call("GET", "/api/houses", headers=A))[0] == 403          # olib tashlangach darhol yopiladi
            assert (await s.call("DELETE", f"/api/admins/{SUPER_ID}", headers=S))[0] == 400
        finally:
            await cleanup_ids(CLIENT, ADMIN2)
            await s.stop()

    run(go())


# ------------------------------------------------------------ scraper mapping ---

def test_joymee_detail_mapping():
    from decimal import Decimal

    from bot.scrapers.joymee import map_detail

    det = {
        "id": 42, "title": "  Kvartira  ", "description": "d", "address_line": "Toshkent viloyati, Chirchiq",
        "phone_number": "+998901234567", "location": {"latitude": 41.1, "longitude": 69.2},
        "district": {"id": 166, "name": "Chirchiq shahar"}, "region": {"name": "Toshkent viloyati"},
        "media": [{"file": {"url": "https://cdn/2.jpg"}, "order": 2, "is_cover": False},
                  {"file": {"url": "https://cdn/1.jpg"}, "order": 1, "is_cover": True}],
        "pricing": {"currency": 2, "price": "400.00", "currency_display": "y.e"},
        "seller": {"first_name": "Ali", "last_name": "V", "username": "ali"},
        "detail": {"area_m2": "46.60", "room_quantity": 2, "floor_number": 5, "floors_count": 7},
        "stats": {"views": 60}, "ads_at": "2026-10-24T15:41:10+05:00",
    }
    m = map_detail(det)
    assert m["title"] == "Kvartira" and m["price"] == Decimal("400.00") and m["currency"] == "USD"
    assert m["photo_urls"] == ["https://cdn/1.jpg", "https://cdn/2.jpg"]  # muqova birinchi
    assert m["rooms"] == 2 and m["area"] == Decimal("46.60") and m["floor"] == 5 and m["floors"] == 7
    assert m["district"] == "Chirchiq shahar" and m["seller_name"] == "Ali V" and m["views"] == 60
    assert m["source_url"] == "https://joymee.uz/announcements/42" and m["external_created_at"] is not None
