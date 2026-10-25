"""Oddiy foydalanuvchi (klient) qismi: /start, market Mini App, aloqa.

Asosiy klient interfeysi — Mini App (bot/webapp/static/market.html).
Bu yerdagi matnli varaqlash zaxira variant (Mini App ishlamasa).
"""
from __future__ import annotations

import html
from decimal import Decimal

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    WebAppInfo,
)

from bot import db
from bot import keyboards as kb

router = Router(name="user")


def market_kb(webapp_url: str) -> InlineKeyboardMarkup | None:
    if not webapp_url:
        return None
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🏠 Uylar bozorini ochish", web_app=WebAppInfo(url=webapp_url + "/market")),
    ]])


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, is_admin: bool, webapp_url: str = "") -> None:
    await state.clear()
    text = (
        f"Assalomu alaykum, <b>{html.escape(message.from_user.full_name)}</b>! 👋\n\n"
        "<b>Chirchiq Arenda</b> — Chirchiq shahridagi ijara uylar bir joyda.\n"
        "E'lonlar Joymee.uz dan avtomatik yig'iladi va muntazam yangilanadi.\n\n"
        "Pastdagi tugma orqali bozorni oching 👇"
    )
    if is_admin:
        text += "\n\n🛠 Siz adminsiz. Admin panel: /admin"
    await message.answer(text, reply_markup=kb.user_menu())
    markup = market_kb(webapp_url)
    if markup:
        await message.answer("🏠 Ijara uylar bozori:", reply_markup=markup)


@router.message(F.text == kb.BTN_USER_CONTACT)
async def contact(message: Message) -> None:
    await message.answer(
        "📞 <b>Aloqa</b>\n\n"
        "Savollar bo'yicha adminlarga murojaat qiling.\n"
        "Uy egasi bilan bog'lanish raqami har bir e'lon ichida ko'rsatilgan."
    )


@router.message(F.text == kb.BTN_USER_HOUSES)
async def houses_start(message: Message, webapp_url: str = "") -> None:
    markup = market_kb(webapp_url)
    if markup:
        await message.answer("🏠 Ijara uylar bozori:", reply_markup=markup)
        return
    total = await db.count_houses(only_active=True)
    if total == 0:
        await message.answer("Hozircha e'lonlar yo'q. Keyinroq qayta urinib ko'ring.")
        return
    await _send_house(message, index=0, total=total)


@router.callback_query(F.data.startswith("uh:"))
async def houses_nav(call: CallbackQuery) -> None:
    arg = call.data.split(":")[1]
    if arg == "noop":
        await call.answer()
        return
    index = int(arg)
    total = await db.count_houses(only_active=True)
    if total == 0:
        await call.answer("E'lonlar qolmadi", show_alert=True)
        return
    index = min(index, total - 1)
    await call.answer()
    try:
        await call.message.delete()
    except Exception:
        pass
    await _send_house(call.message, index=index, total=total)


async def _send_house(message: Message, index: int, total: int) -> None:
    rows = await db.list_houses(offset=index, limit=1, only_active=True)
    if not rows:
        await message.answer("E'lon topilmadi.")
        return
    h = rows[0]
    price = f"{Decimal(h['price']):,.0f}".replace(",", " ")
    unit = "y.e" if h["currency"] == "USD" else "so'm"
    caption = (
        f"🏠 <b>{html.escape(h['title'])}</b>\n"
        f"📍 {html.escape(h['address'])}\n"
        + (f"🚪 Xonalar: {h['rooms']}\n" if h["rooms"] else "")
        + f"💰 {price} {unit} / oy\n"
    )
    if h["description"]:
        caption += f"\n📝 {html.escape(h['description'][:600])}\n"
    if h["contact_phone"]:
        caption += f"\n📞 {html.escape(h['contact_phone'])}"
    if h["source_url"]:
        caption += f"\n🔗 {h['source_url']}"
    markup = kb.house_nav_kb(index, total)
    photos = list(h["photo_urls"] or [])
    first = photos[0] if photos else (f"tg:{h['photo_file_id']}" if h["photo_file_id"] else None)
    if first:
        media = first[3:] if first.startswith("tg:") else first  # file_id yoki URL — ikkalasini ham aiogram qabul qiladi
        try:
            await message.answer_photo(media, caption=caption[:1024], reply_markup=markup)
            return
        except Exception:
            pass
    await message.answer(caption, reply_markup=markup)
