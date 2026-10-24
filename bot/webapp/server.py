"""Admin Mini App uchun HTTP server (aiohttp): statik sahifa + JSON API.

Autentifikatsiya: Telegram Web App `initData` (HMAC-SHA256, bot tokeni bilan tekshiriladi).
Faqat ADMIN_IDS dagi foydalanuvchilar ruxsat oladi.
"""
from __future__ import annotations

import logging
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from aiogram import Bot
from aiogram.types import BufferedInputFile
from aiogram.utils.web_app import safe_parse_webapp_init_data
from aiohttp import web

from bot import db
from bot.config import config

log = logging.getLogger("webapp")

STATIC_DIR = Path(__file__).resolve().parent / "static"
INIT_DATA_MAX_AGE = 60 * 60 * 12  # 12 soat


# ------------------------------------------------------------------ auth ---

def _extract_init_data(request: web.Request) -> str | None:
    auth = request.headers.get("Authorization", "")
    if auth.startswith("tma "):
        return auth[4:].strip()
    # <img src="..."> uchun header qo'yib bo'lmaydi — query orqali
    return request.query.get("_auth") or None


@web.middleware
async def auth_middleware(request: web.Request, handler):
    if not request.path.startswith("/api/"):
        return await handler(request)

    raw = _extract_init_data(request)
    if not raw:
        raise web.HTTPUnauthorized(text="initData yo'q. Sahifani Telegram orqali oching.")
    try:
        data = safe_parse_webapp_init_data(config.bot_token, raw)
    except ValueError:
        raise web.HTTPUnauthorized(text="initData noto'g'ri yoki buzilgan.")

    import time
    if data.auth_date and time.time() - data.auth_date.timestamp() > INIT_DATA_MAX_AGE:
        raise web.HTTPUnauthorized(text="Sessiya eskirgan. Mini App'ni qayta oching.")
    if data.user is None or data.user.id not in config.admin_ids:
        raise web.HTTPForbidden(text="Siz admin emassiz.")

    request["tg_user"] = data.user
    return await handler(request)


# --------------------------------------------------------------- helpers ---

def _house_json(h) -> dict[str, Any]:
    return {
        "id": h["id"],
        "title": h["title"],
        "address": h["address"],
        "rooms": h["rooms"],
        "price": float(h["price"]),
        "description": h["description"],
        "photo_file_id": h["photo_file_id"],
        "contact_phone": h["contact_phone"],
        "is_active": h["is_active"],
        "created_at": h["created_at"].isoformat(),
    }


def _user_json(u) -> dict[str, Any]:
    return {
        "telegram_id": u["telegram_id"],
        "full_name": u["full_name"],
        "username": u["username"],
        "phone": u["phone"],
        "is_blocked": u["is_blocked"],
        "block_reason": u["block_reason"],
        "created_at": u["created_at"].isoformat(),
    }


def _bad(msg: str) -> web.HTTPBadRequest:
    return web.HTTPBadRequest(text=msg)


# ---------------------------------------------------------------- routes ---

async def index(request: web.Request) -> web.FileResponse:
    return web.FileResponse(STATIC_DIR / "index.html")


async def api_me(request: web.Request) -> web.Response:
    u = request["tg_user"]
    name = " ".join(p for p in (u.first_name, u.last_name) if p)
    return web.json_response({"id": u.id, "name": name, "username": u.username})


async def api_stats(request: web.Request) -> web.Response:
    return web.json_response(await db.stats())


async def api_houses(request: web.Request) -> web.Response:
    houses = await db.list_houses(offset=0, limit=200, only_active=False)
    return web.json_response([_house_json(h) for h in houses])


async def api_house_add(request: web.Request) -> web.Response:
    """multipart/form-data: title, address, rooms, price, description, contact_phone, photo(file)."""
    form = await request.post()
    title = str(form.get("title", "")).strip()[:120]
    address = str(form.get("address", "")).strip()[:250]
    description = str(form.get("description", "")).strip()[:1500]
    contact_phone = str(form.get("contact_phone", "")).strip()[:30] or None
    if not title or not address:
        raise _bad("Nom va manzil majburiy.")
    try:
        rooms = int(str(form.get("rooms", "")).strip())
        if not 1 <= rooms <= 50:
            raise ValueError
    except ValueError:
        raise _bad("Xonalar soni 1..50 oralig'ida bo'lsin.")
    try:
        price = Decimal(str(form.get("price", "")).replace(" ", "").replace(",", "."))
        if price < 0:
            raise InvalidOperation
    except InvalidOperation:
        raise _bad("Narx noto'g'ri.")

    photo_file_id: str | None = None
    photo = form.get("photo")
    if isinstance(photo, web.FileField) and photo.filename:
        content = photo.file.read()
        if len(content) > 10 * 1024 * 1024:
            raise _bad("Rasm 10 MB dan katta.")
        if content:
            # file_id olish uchun rasmni admin chatiga yuboramiz
            bot: Bot = request.app["bot"]
            msg = await bot.send_photo(
                chat_id=request["tg_user"].id,
                photo=BufferedInputFile(content, filename=photo.filename or "photo.jpg"),
                caption=f"📎 Mini App orqali yuklandi: {title}",
                disable_notification=True,
            )
            photo_file_id = msg.photo[-1].file_id

    house_id = await db.add_house(
        title=title, address=address, rooms=rooms, price=price,
        description=description, photo_file_id=photo_file_id,
        contact_phone=contact_phone, created_by=request["tg_user"].id,
    )
    house = await db.get_house(house_id)
    return web.json_response(_house_json(house), status=201)


async def api_house_delete(request: web.Request) -> web.Response:
    house_id = int(request.match_info["id"])
    ok = await db.delete_house(house_id)
    if not ok:
        raise web.HTTPNotFound(text="Uy topilmadi.")
    return web.json_response({"ok": True})


async def api_house_patch(request: web.Request) -> web.Response:
    house_id = int(request.match_info["id"])
    body = await request.json()
    if "is_active" not in body:
        raise _bad("is_active kerak.")
    ok = await db.set_house_active(house_id, bool(body["is_active"]))
    if not ok:
        raise web.HTTPNotFound(text="Uy topilmadi.")
    return web.json_response(_house_json(await db.get_house(house_id)))


async def api_users(request: web.Request) -> web.Response:
    q = request.query.get("q", "").strip() or None
    blocked_raw = request.query.get("blocked")
    blocked = None if blocked_raw in (None, "", "all") else blocked_raw == "1"
    page = max(0, int(request.query.get("page", "0") or 0))
    per_page = 50
    users = await db.list_users(offset=page * per_page, limit=per_page, blocked=blocked, q=q)
    return web.json_response({"items": [_user_json(u) for u in users], "page": page, "per_page": per_page})


async def api_user_block(request: web.Request) -> web.Response:
    tg_id = int(request.match_info["id"])
    if tg_id == request["tg_user"].id:
        raise _bad("O'zingizni bloklay olmaysiz.")
    body = await request.json() if request.can_read_body else {}
    reason = (body.get("reason") or "").strip()[:300] or "Admin tomonidan bloklangan"
    ok = await db.block_user(tg_id, reason)
    if not ok:
        raise web.HTTPNotFound(text="Klient topilmadi.")
    return web.json_response(_user_json(await db.get_user(tg_id)))


async def api_user_unblock(request: web.Request) -> web.Response:
    tg_id = int(request.match_info["id"])
    ok = await db.unblock_user(tg_id)
    if not ok:
        raise web.HTTPNotFound(text="Klient topilmadi.")
    return web.json_response(_user_json(await db.get_user(tg_id)))


async def api_photo(request: web.Request) -> web.Response:
    """Telegram file_id bo'yicha rasmni proksilaydi (Mini App'da ko'rsatish uchun)."""
    bot: Bot = request.app["bot"]
    file_id = request.match_info["file_id"]
    try:
        tg_file = await bot.get_file(file_id)
        buf = await bot.download_file(tg_file.file_path)
    except Exception as exc:  # noqa: BLE001
        log.warning("Rasm yuklanmadi %s: %s", file_id, exc)
        raise web.HTTPNotFound(text="Rasm topilmadi.")
    return web.Response(
        body=buf.read(),
        content_type="image/jpeg",
        headers={"Cache-Control": "private, max-age=86400"},
    )


# ------------------------------------------------------------------- app ---

def create_app(bot: Bot) -> web.Application:
    app = web.Application(middlewares=[auth_middleware], client_max_size=12 * 1024 * 1024)
    app["bot"] = bot
    app.add_routes([
        web.get("/", index),
        web.get("/api/me", api_me),
        web.get("/api/stats", api_stats),
        web.get("/api/houses", api_houses),
        web.post("/api/houses", api_house_add),
        web.delete("/api/houses/{id:\\d+}", api_house_delete),
        web.patch("/api/houses/{id:\\d+}", api_house_patch),
        web.get("/api/users", api_users),
        web.post("/api/users/{id:\\d+}/block", api_user_block),
        web.post("/api/users/{id:\\d+}/unblock", api_user_unblock),
        web.get("/api/photo/{file_id}", api_photo),
    ])
    app.router.add_static("/static/", STATIC_DIR, show_index=False)
    return app


async def start_server(bot: Bot) -> web.AppRunner:
    runner = web.AppRunner(create_app(bot), access_log=None)
    await runner.setup()
    site = web.TCPSite(runner, host=config.webapp_host, port=config.webapp_port)
    await site.start()
    log.info("Mini App server: http://%s:%s", config.webapp_host, config.webapp_port)
    return runner
