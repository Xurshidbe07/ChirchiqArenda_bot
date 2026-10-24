"""Oddiy foydalanuvchi (klient) qismi: /start, uylarni ko'rish, aloqa.

Eslatma: bu qism minimal qilib yozilgan — jamoadagi boshqa a'zolar
klient funksiyalarini shu yerda kengaytirishi mumkin.
"""
from __future__ import annotations

import html
from decimal import Decimal

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot import db
from bot import keyboards as kb

router = Router(name="user")


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, is_admin: bool) -> None:
    await state.clear()
    text = (
        f"Assalomu alaykum, <b>{html.escape(message.from_user.full_name)}</b>! 👋\n\n"
        "<b>ChirchiqArendabot</b> — Chirchiq shahrida ijaraga uylar.\n"
        "Quyidagi menyudan foydalaning."
    )
    if is_admin:
        text += "\n\n🛠 Siz adminsiz. Admin panel: /admin"
    await message.answer(text, reply_markup=kb.user_menu())


@router.message(F.text == kb.BTN_USER_CONTACT)
async def contact(message: Message) -> None:
    await message.answer(
        "📞 <b>Aloqa</b>\n\n"
        "Savollar bo'yicha adminlarga murojaat qiling.\n"
        "Uy bo'yicha bog'lanish raqami har bir e'lon ostida ko'rsatilgan."
    )


@router.message(F.text == kb.BTN_USER_HOUSES)
async def houses_start(message: Message) -> None:
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
    caption = (
        f"🏠 <b>{html.escape(h['title'])}</b>\n"
        f"📍 {html.escape(h['address'])}\n"
        f"🚪 Xonalar: {h['rooms']}\n"
        f"💰 {price} so'm / oy\n"
    )
    if h["description"]:
        caption += f"\n📝 {html.escape(h['description'])}\n"
    if h["contact_phone"]:
        caption += f"\n📞 {html.escape(h['contact_phone'])}"
    markup = kb.house_nav_kb(index, total)
    if h["photo_file_id"]:
        await message.answer_photo(h["photo_file_id"], caption=caption[:1024], reply_markup=markup)
    else:
        await message.answer(caption, reply_markup=markup)
