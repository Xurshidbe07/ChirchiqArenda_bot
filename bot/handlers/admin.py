"""Admin panel: uy qo'shish, uy o'chirish, klient bloklash/blokdan chiqarish, statistika."""
from __future__ import annotations

import html
from decimal import Decimal, InvalidOperation

from aiogram import F, Router
from aiogram.filters import Command, StateFilter
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
from bot.filters import IsAdmin
from bot.states import AddHouse, BlockClient, UnblockClient

router = Router(name="admin")
# Bu routerdagi barcha handlerlar faqat adminlar uchun
router.message.filter(IsAdmin())
router.callback_query.filter(IsAdmin())

PER_PAGE = 8

# Menyu tugmasi bosilganda u FSM javobi sifatida qabul qilinmasin —
# pastdagi menyu handlerlariga o'tib ketsin (ular state ni tozalaydi).
NOT_MENU = ~F.text.in_(kb.ADMIN_MENU_BUTTONS)


# ====================================================================== MENU ===

@router.message(Command("admin"))
async def cmd_admin(message: Message, state: FSMContext, webapp_url: str = "") -> None:
    """Mini App tugmasini yuboradi; manzil bo'lmasa oddiy menyuga o'tadi."""
    await state.clear()
    if not webapp_url:
        await message.answer(
            "⚠️ Mini App manzili sozlanmagan (WEBAPP_URL yoki cloudflared yo'q).\n"
            "Oddiy menyu ochildi:",
            reply_markup=kb.admin_menu(),
        )
        return
    markup = InlineKeyboardMarkup(
        inline_keyboard=[[
            InlineKeyboardButton(text="🛠 Admin panelni ochish", web_app=WebAppInfo(url=webapp_url)),
        ]]
    )
    await message.answer(
        "🛠 <b>Admin panel</b>\n\n"
        "Tugmani bosing — interfeys ochiladi.\n"
        "<i>Oddiy tugmali menyu: /menu</i>",
        reply_markup=markup,
    )


@router.message(Command("menu"))
async def cmd_menu(message: Message, state: FSMContext) -> None:
    """Eski (tugmali) admin menyusi — zaxira variant."""
    await state.clear()
    await message.answer(
        "🛠 <b>Admin menyu</b>\n\nKerakli bo'limni tanlang:",
        reply_markup=kb.admin_menu(),
    )


@router.message(F.text == kb.BTN_EXIT)
async def admin_exit(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Admin paneldan chiqdingiz.", reply_markup=kb.user_menu())


@router.message(StateFilter("*"), F.text == kb.BTN_CANCEL)
async def cancel_any(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("❌ Bekor qilindi.", reply_markup=kb.admin_menu())


@router.message(F.text == kb.BTN_STATS)
async def show_stats(message: Message) -> None:
    s = await db.stats()
    await message.answer(
        "📊 <b>Statistika</b>\n\n"
        f"👥 Klientlar: <b>{s['users_total']}</b> (bloklangan: {s['users_blocked']})\n"
        f"🏠 Uylar: <b>{s['houses_total']}</b> (faol: {s['houses_active']})"
    )


# ============================================================= ADD HOUSE (FSM) ===

@router.message(F.text == kb.BTN_ADD_HOUSE)
async def add_house_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(AddHouse.title)
    await message.answer(
        "➕ <b>Yangi uy qo'shish</b>\n\n1/7. Uy nomini (sarlavha) kiriting:\n"
        "<i>Masalan: 2 xonali, markazda</i>",
        reply_markup=kb.cancel_kb(),
    )


@router.message(AddHouse.title, F.text, NOT_MENU)
async def add_house_title(message: Message, state: FSMContext) -> None:
    await state.update_data(title=message.text.strip()[:120])
    await state.set_state(AddHouse.address)
    await message.answer("2/7. Manzilni kiriting:\n<i>Masalan: Chirchiq, Yoshlik mavzesi 12-uy</i>")


@router.message(AddHouse.address, F.text, NOT_MENU)
async def add_house_address(message: Message, state: FSMContext) -> None:
    await state.update_data(address=message.text.strip()[:250])
    await state.set_state(AddHouse.rooms)
    await message.answer("3/7. Xonalar sonini kiriting (raqam):")


@router.message(AddHouse.rooms, F.text, NOT_MENU)
async def add_house_rooms(message: Message, state: FSMContext) -> None:
    txt = message.text.strip()
    if not txt.isdigit() or not (1 <= int(txt) <= 50):
        await message.answer("❗️ 1 dan 50 gacha bo'lgan butun son kiriting.")
        return
    await state.update_data(rooms=int(txt))
    await state.set_state(AddHouse.price)
    await message.answer("4/7. Oylik narxni kiriting (so'mda, faqat raqam):\n<i>Masalan: 2500000</i>")


@router.message(AddHouse.price, F.text, NOT_MENU)
async def add_house_price(message: Message, state: FSMContext) -> None:
    txt = message.text.replace(" ", "").replace(",", ".")
    try:
        price = Decimal(txt)
        if price < 0 or price > Decimal("999999999999"):
            raise InvalidOperation
    except InvalidOperation:
        await message.answer("❗️ Narxni to'g'ri kiriting, masalan: 2500000")
        return
    await state.update_data(price=str(price))
    await state.set_state(AddHouse.description)
    await message.answer(
        "5/7. Qo'shimcha tavsif kiriting (remont, mebel, qavat va h.k.):",
        reply_markup=kb.cancel_kb(skip=True),
    )


@router.message(AddHouse.description, F.text, NOT_MENU)
async def add_house_description(message: Message, state: FSMContext) -> None:
    desc = "" if message.text == kb.BTN_SKIP else message.text.strip()[:1500]
    await state.update_data(description=desc)
    await state.set_state(AddHouse.contact_phone)
    await message.answer(
        "6/7. Bog'lanish uchun telefon raqam:\n<i>Masalan: +998901234567</i>",
        reply_markup=kb.cancel_kb(skip=True),
    )


@router.message(AddHouse.contact_phone, F.text, NOT_MENU)
async def add_house_phone(message: Message, state: FSMContext) -> None:
    phone = None if message.text == kb.BTN_SKIP else message.text.strip()[:30]
    await state.update_data(contact_phone=phone)
    await state.set_state(AddHouse.photo)
    await message.answer(
        "7/7. Uy rasmini yuboring (bitta rasm):",
        reply_markup=kb.cancel_kb(skip=True),
    )


@router.message(AddHouse.photo, F.photo)
async def add_house_photo(message: Message, state: FSMContext) -> None:
    await state.update_data(photo_file_id=message.photo[-1].file_id)
    await _show_house_preview(message, state)


@router.message(AddHouse.photo, F.text == kb.BTN_SKIP)
async def add_house_photo_skip(message: Message, state: FSMContext) -> None:
    await state.update_data(photo_file_id=None)
    await _show_house_preview(message, state)


@router.message(AddHouse.photo, NOT_MENU)
async def add_house_photo_invalid(message: Message) -> None:
    await message.answer("❗️ Rasm yuboring yoki «O'tkazib yuborish» tugmasini bosing.")


async def _show_house_preview(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    await state.set_state(AddHouse.confirm)
    caption = _format_house(data, house_id=None)
    await message.answer("Ma'lumotlarni tekshiring:", reply_markup=kb.remove_kb())
    if data.get("photo_file_id"):
        await message.answer_photo(data["photo_file_id"], caption=caption, reply_markup=kb.confirm_house_kb())
    else:
        await message.answer(caption, reply_markup=kb.confirm_house_kb())


@router.callback_query(AddHouse.confirm, F.data == "house:save")
async def add_house_save(call: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    house_id = await db.add_house(
        title=data["title"],
        address=data["address"],
        rooms=data["rooms"],
        price=Decimal(data["price"]),
        description=data.get("description", ""),
        photo_file_id=data.get("photo_file_id"),
        contact_phone=data.get("contact_phone"),
        created_by=call.from_user.id,
    )
    await state.clear()
    await call.answer("Saqlandi ✅")
    await _remove_markup(call)
    await call.message.answer(f"✅ Uy <b>#{house_id}</b> muvaffaqiyatli qo'shildi.", reply_markup=kb.admin_menu())


@router.callback_query(AddHouse.confirm, F.data == "house:cancel")
async def add_house_cancel(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await call.answer("Bekor qilindi")
    await _remove_markup(call)
    await call.message.answer("❌ Uy qo'shish bekor qilindi.", reply_markup=kb.admin_menu())


# ================================================================= LIST HOUSES ===

@router.message(F.text == kb.BTN_LIST_HOUSES)
async def list_houses(message: Message) -> None:
    houses = await db.list_houses(limit=30, only_active=False)
    if not houses:
        await message.answer("Hozircha uylar yo'q.")
        return
    lines = ["🏠 <b>Uylar ro'yxati</b> (oxirgi 30 ta):\n"]
    for h in houses:
        status = "🟢" if h["is_active"] else "🔴"
        lines.append(
            f"{status} <b>#{h['id']}</b> — {html.escape(h['title'])} · "
            f"{h['rooms']} xona · {_fmt_price(h['price'])} so'm"
        )
    await message.answer("\n".join(lines))


# ================================================================ DELETE HOUSE ===

@router.message(F.text == kb.BTN_DEL_HOUSE)
async def delete_house_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    total = await db.count_houses(only_active=False)
    if total == 0:
        await message.answer("O'chirish uchun uylar yo'q.")
        return
    houses = await db.list_houses(offset=0, limit=PER_PAGE, only_active=False)
    await message.answer(
        "🗑 <b>Uy o'chirish</b>\n\nO'chirmoqchi bo'lgan uyni tanlang:",
        reply_markup=kb.houses_delete_kb(houses, 0, total, PER_PAGE),
    )


@router.callback_query(F.data.startswith("delhouse:page:"))
async def delete_house_page(call: CallbackQuery) -> None:
    arg = call.data.split(":")[2]
    if arg == "noop":
        await call.answer()
        return
    page = int(arg)
    total = await db.count_houses(only_active=False)
    houses = await db.list_houses(offset=page * PER_PAGE, limit=PER_PAGE, only_active=False)
    await call.answer()
    await _edit(call, "🗑 <b>Uy o'chirish</b>\n\nO'chirmoqchi bo'lgan uyni tanlang:",
                kb.houses_delete_kb(houses, page, total, PER_PAGE))


@router.callback_query(F.data.startswith("delhouse:ask:"))
async def delete_house_ask(call: CallbackQuery) -> None:
    _, _, house_id, page = call.data.split(":")
    house = await db.get_house(int(house_id))
    if house is None:
        await call.answer("Bu uy allaqachon o'chirilgan.", show_alert=True)
        return
    await call.answer()
    text = "⚠️ <b>Rostdan ham o'chirmoqchimisiz?</b>\n\n" + _format_house(dict(house), house_id=house["id"])
    await _edit(call, text, kb.confirm_delete_kb(house["id"], int(page)))


@router.callback_query(F.data.startswith("delhouse:yes:"))
async def delete_house_yes(call: CallbackQuery) -> None:
    _, _, house_id, page = call.data.split(":")
    ok = await db.delete_house(int(house_id))
    await call.answer("O'chirildi ✅" if ok else "Topilmadi", show_alert=not ok)
    page = int(page)
    total = await db.count_houses(only_active=False)
    if total == 0:
        await _edit(call, "🗑 Barcha uylar o'chirildi. Ro'yxat bo'sh.", None)
        return
    if page * PER_PAGE >= total:
        page = max(0, page - 1)
    houses = await db.list_houses(offset=page * PER_PAGE, limit=PER_PAGE, only_active=False)
    await _edit(call, f"✅ Uy #{house_id} o'chirildi.\n\nYana o'chirish uchun tanlang:",
                kb.houses_delete_kb(houses, page, total, PER_PAGE))


# ================================================================ CLIENTS LIST ===

@router.message(F.text == kb.BTN_CLIENTS)
async def clients_list(message: Message, state: FSMContext) -> None:
    await state.clear()
    total = await db.count_users()
    users = await db.list_users(offset=0, limit=PER_PAGE)
    await message.answer(
        f"👥 <b>Klientlar</b> (jami {total})\n\n"
        "✅ — faol, 🚫 — bloklangan. Bosib holatini o'zgartiring:",
        reply_markup=kb.clients_kb(users, 0, total, PER_PAGE),
    )


@router.callback_query(F.data.startswith("client:page:"))
async def clients_page(call: CallbackQuery) -> None:
    arg = call.data.split(":")[2]
    if arg == "noop":
        await call.answer()
        return
    page = int(arg)
    await call.answer()
    await _render_clients(call, page)


@router.callback_query(F.data.startswith("client:block:"))
async def client_block_cb(call: CallbackQuery) -> None:
    _, _, tg_id, page = call.data.split(":")
    tg_id = int(tg_id)
    if tg_id == call.from_user.id:
        await call.answer("O'zingizni bloklay olmaysiz 🙂", show_alert=True)
        return
    ok = await db.block_user(tg_id, reason="Admin tomonidan bloklangan")
    await call.answer("Bloklandi 🚫" if ok else "Topilmadi")
    await _render_clients(call, int(page))


@router.callback_query(F.data.startswith("client:unblock:"))
async def client_unblock_cb(call: CallbackQuery) -> None:
    _, _, tg_id, page = call.data.split(":")
    ok = await db.unblock_user(int(tg_id))
    await call.answer("Blokdan chiqarildi ✅" if ok else "Topilmadi")
    # Qaysi ro'yxatdan kelganiga qarab yangilaymiz
    if call.message and call.message.text and call.message.text.startswith("🚫"):
        await _render_blocked(call, int(page))
    else:
        await _render_clients(call, int(page))


async def _render_clients(call: CallbackQuery, page: int) -> None:
    total = await db.count_users()
    users = await db.list_users(offset=page * PER_PAGE, limit=PER_PAGE)
    await _edit(
        call,
        f"👥 <b>Klientlar</b> (jami {total})\n\n"
        "✅ — faol, 🚫 — bloklangan. Bosib holatini o'zgartiring:",
        kb.clients_kb(users, page, total, PER_PAGE),
    )


# ================================================================ BLOCK CLIENT ===

@router.message(F.text == kb.BTN_BLOCK)
async def block_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(BlockClient.waiting_id)
    await message.answer(
        "🚫 <b>Klient bloklash</b>\n\n"
        "Klientning Telegram ID sini yuboring yoki uning xabarini forward qiling.\n"
        "<i>Ro'yxatdan tanlash uchun «👥 Klientlar» bo'limidan foydalaning.</i>",
        reply_markup=kb.cancel_kb(),
    )


@router.message(BlockClient.waiting_id, NOT_MENU)
async def block_get_id(message: Message, state: FSMContext) -> None:
    tg_id = _extract_tg_id(message)
    if tg_id is None:
        await message.answer("❗️ Telegram ID (raqam) yuboring yoki klient xabarini forward qiling.")
        return
    if tg_id == message.from_user.id:
        await message.answer("❗️ O'zingizni bloklay olmaysiz.")
        return
    user = await db.get_user(tg_id)
    if user is None:
        await message.answer(
            "❗️ Bunday klient bazada yo'q. U avval botga /start yuborgan bo'lishi kerak."
        )
        return
    if user["is_blocked"]:
        await message.answer("ℹ️ Bu klient allaqachon bloklangan.", reply_markup=kb.admin_menu())
        await state.clear()
        return
    await state.update_data(block_tg_id=tg_id)
    await state.set_state(BlockClient.waiting_reason)
    await message.answer(
        f"Klient: <b>{html.escape(user['full_name'])}</b> (ID: <code>{tg_id}</code>)\n\n"
        "Bloklash sababini yozing:",
        reply_markup=kb.cancel_kb(skip=True),
    )


@router.message(BlockClient.waiting_reason, F.text, NOT_MENU)
async def block_get_reason(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    reason = None if message.text == kb.BTN_SKIP else message.text.strip()[:300]
    ok = await db.block_user(data["block_tg_id"], reason)
    await state.clear()
    if ok:
        await message.answer(
            f"🚫 Klient <code>{data['block_tg_id']}</code> bloklandi.",
            reply_markup=kb.admin_menu(),
        )
    else:
        await message.answer("❗️ Klient topilmadi.", reply_markup=kb.admin_menu())


# ============================================================== UNBLOCK CLIENT ===

@router.message(F.text == kb.BTN_UNBLOCK)
async def unblock_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    total = await db.count_users(blocked=True)
    if total == 0:
        await message.answer("✅ Bloklangan klientlar yo'q.")
        return
    users = await db.list_users(offset=0, limit=PER_PAGE, blocked=True)
    await state.set_state(UnblockClient.waiting_id)
    await message.answer(
        f"🚫 <b>Bloklangan klientlar</b> (jami {total})\n\n"
        "Blokdan chiqarish uchun bosing yoki ID yuboring:",
        reply_markup=kb.blocked_list_kb(users, 0, total, PER_PAGE),
    )


@router.callback_query(F.data.startswith("blocked:page:"))
async def blocked_page(call: CallbackQuery) -> None:
    arg = call.data.split(":")[2]
    if arg == "noop":
        await call.answer()
        return
    await call.answer()
    await _render_blocked(call, int(arg))


@router.message(UnblockClient.waiting_id, NOT_MENU)
async def unblock_get_id(message: Message, state: FSMContext) -> None:
    tg_id = _extract_tg_id(message)
    if tg_id is None:
        await message.answer("❗️ Telegram ID (raqam) yuboring.")
        return
    ok = await db.unblock_user(tg_id)
    await state.clear()
    await message.answer(
        f"✅ Klient <code>{tg_id}</code> blokdan chiqarildi." if ok else "❗️ Klient topilmadi.",
        reply_markup=kb.admin_menu(),
    )


async def _render_blocked(call: CallbackQuery, page: int) -> None:
    total = await db.count_users(blocked=True)
    if total == 0:
        await _edit(call, "✅ Bloklangan klientlar qolmadi.", None)
        return
    if page * PER_PAGE >= total:
        page = max(0, page - 1)
    users = await db.list_users(offset=page * PER_PAGE, limit=PER_PAGE, blocked=True)
    await _edit(
        call,
        f"🚫 <b>Bloklangan klientlar</b> (jami {total})\n\nBlokdan chiqarish uchun bosing yoki ID yuboring:",
        kb.blocked_list_kb(users, page, total, PER_PAGE),
    )


# ===================================================================== HELPERS ===

def _extract_tg_id(message: Message) -> int | None:
    """Forward qilingan xabardan yoki matndan Telegram ID ni oladi."""
    if message.forward_from is not None:
        return message.forward_from.id
    if message.text and message.text.strip().lstrip("-").isdigit():
        return int(message.text.strip())
    return None


def _fmt_price(price) -> str:
    return f"{Decimal(price):,.0f}".replace(",", " ")


def _format_house(data: dict, house_id: int | None) -> str:
    head = f"🏠 <b>{html.escape(str(data['title']))}</b>"
    if house_id is not None:
        head = f"🏠 <b>#{house_id} · {html.escape(str(data['title']))}</b>"
    lines = [
        head,
        f"📍 Manzil: {html.escape(str(data['address']))}",
        f"🚪 Xonalar: {data['rooms']}",
        f"💰 Narx: {_fmt_price(data['price'])} so'm / oy",
    ]
    if data.get("description"):
        lines.append(f"📝 {html.escape(str(data['description']))}")
    if data.get("contact_phone"):
        lines.append(f"📞 {html.escape(str(data['contact_phone']))}")
    return "\n".join(lines)


async def _edit(call: CallbackQuery, text: str, markup) -> None:
    """Xabarni tahrirlaydi (matn yoki rasm sarlavhasi bo'lishi mumkin)."""
    if call.message is None:
        return
    try:
        if call.message.photo:
            await call.message.edit_caption(caption=text, reply_markup=markup)
        else:
            await call.message.edit_text(text, reply_markup=markup)
    except Exception:
        # "message is not modified" kabi xatolarni e'tiborsiz qoldiramiz
        pass


async def _remove_markup(call: CallbackQuery) -> None:
    try:
        await call.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
