"""Reply va inline klaviaturalar."""
from __future__ import annotations

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

# -------------------------------------------------------- Admin reply menu ---

BTN_ADD_HOUSE = "➕ Uy qo'shish"
BTN_DEL_HOUSE = "🗑 Uy o'chirish"
BTN_LIST_HOUSES = "🏠 Uylar ro'yxati"
BTN_BLOCK = "🚫 Klient bloklash"
BTN_UNBLOCK = "✅ Blokdan chiqarish"
BTN_CLIENTS = "👥 Klientlar"
BTN_STATS = "📊 Statistika"
BTN_EXIT = "⬅️ Admin paneldan chiqish"

BTN_CANCEL = "❌ Bekor qilish"
BTN_SKIP = "⏭ O'tkazib yuborish"

# FSM holatida turganda ham menyu tugmalari ishlashi uchun
ADMIN_MENU_BUTTONS = frozenset({
    BTN_ADD_HOUSE, BTN_DEL_HOUSE, BTN_LIST_HOUSES, BTN_BLOCK,
    BTN_UNBLOCK, BTN_CLIENTS, BTN_STATS, BTN_EXIT, BTN_CANCEL,
})


def admin_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_ADD_HOUSE), KeyboardButton(text=BTN_DEL_HOUSE)],
            [KeyboardButton(text=BTN_LIST_HOUSES), KeyboardButton(text=BTN_CLIENTS)],
            [KeyboardButton(text=BTN_BLOCK), KeyboardButton(text=BTN_UNBLOCK)],
            [KeyboardButton(text=BTN_STATS)],
            [KeyboardButton(text=BTN_EXIT)],
        ],
        resize_keyboard=True,
    )


def cancel_kb(skip: bool = False) -> ReplyKeyboardMarkup:
    row = [KeyboardButton(text=BTN_CANCEL)]
    if skip:
        row.insert(0, KeyboardButton(text=BTN_SKIP))
    return ReplyKeyboardMarkup(keyboard=[row], resize_keyboard=True)


def remove_kb() -> ReplyKeyboardRemove:
    return ReplyKeyboardRemove()


# ---------------------------------------------------------- User reply menu ---

from bot.i18n import LANG_NAMES, LANGS, t  # noqa: E402

# Eski nomlar (o'zbekcha) — moslik uchun
BTN_USER_HOUSES = "🏠 Uylar"
BTN_USER_CONTACT = "📞 Aloqa"


def user_menu(lang: str = "uz") -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=t(lang, "btn_houses")), KeyboardButton(text=t(lang, "btn_contact"))],
            [KeyboardButton(text=t(lang, "btn_lang"))],
        ],
        resize_keyboard=True,
    )


def lang_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=LANG_NAMES[code], callback_data=f"lang:{code}")]
                         for code in LANGS]
    )


# ------------------------------------------------------------- Inline keys ---

def confirm_house_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Saqlash", callback_data="house:save"),
                InlineKeyboardButton(text="❌ Bekor qilish", callback_data="house:cancel"),
            ]
        ]
    )


def houses_delete_kb(houses, page: int, total: int, per_page: int) -> InlineKeyboardMarkup:
    """O'chirish uchun uylar ro'yxati (har biri alohida tugma) + sahifalash."""
    b = InlineKeyboardBuilder()
    for h in houses:
        b.row(
            InlineKeyboardButton(
                text=f"🗑 #{h['id']} · {h['title'][:30]} · {h['rooms']} xona",
                callback_data=f"delhouse:ask:{h['id']}:{page}",
            )
        )
    _add_pagination(b, "delhouse:page", page, total, per_page)
    return b.as_markup()


def confirm_delete_kb(house_id: int, page: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Ha, o'chirish", callback_data=f"delhouse:yes:{house_id}:{page}"),
                InlineKeyboardButton(text="⬅️ Orqaga", callback_data=f"delhouse:page:{page}"),
            ]
        ]
    )


def clients_kb(users, page: int, total: int, per_page: int) -> InlineKeyboardMarkup:
    """Klientlar ro'yxati: bosilsa bloklash/blokdan chiqarish."""
    b = InlineKeyboardBuilder()
    for u in users:
        mark = "🚫" if u["is_blocked"] else "✅"
        uname = f"@{u['username']}" if u["username"] else str(u["telegram_id"])
        action = "unblock" if u["is_blocked"] else "block"
        b.row(
            InlineKeyboardButton(
                text=f"{mark} {u['full_name'][:25]} ({uname})",
                callback_data=f"client:{action}:{u['telegram_id']}:{page}",
            )
        )
    _add_pagination(b, "client:page", page, total, per_page)
    return b.as_markup()


def blocked_list_kb(users, page: int, total: int, per_page: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for u in users:
        uname = f"@{u['username']}" if u["username"] else str(u["telegram_id"])
        b.row(
            InlineKeyboardButton(
                text=f"✅ {u['full_name'][:25]} ({uname})",
                callback_data=f"client:unblock:{u['telegram_id']}:{page}",
            )
        )
    _add_pagination(b, "blocked:page", page, total, per_page)
    return b.as_markup()


def house_nav_kb(index: int, total: int) -> InlineKeyboardMarkup:
    """Foydalanuvchi uchun uylarni varaqlash."""
    row: list[InlineKeyboardButton] = []
    if index > 0:
        row.append(InlineKeyboardButton(text="⬅️", callback_data=f"uh:{index - 1}"))
    row.append(InlineKeyboardButton(text=f"{index + 1}/{total}", callback_data="uh:noop"))
    if index < total - 1:
        row.append(InlineKeyboardButton(text="➡️", callback_data=f"uh:{index + 1}"))
    return InlineKeyboardMarkup(inline_keyboard=[row])


def _add_pagination(b: InlineKeyboardBuilder, prefix: str, page: int, total: int, per_page: int) -> None:
    pages = max(1, (total + per_page - 1) // per_page)
    if pages <= 1:
        return
    nav: list[InlineKeyboardButton] = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="⬅️", callback_data=f"{prefix}:{page - 1}"))
    nav.append(InlineKeyboardButton(text=f"{page + 1}/{pages}", callback_data=f"{prefix}:noop"))
    if page < pages - 1:
        nav.append(InlineKeyboardButton(text="➡️", callback_data=f"{prefix}:{page + 1}"))
    b.row(*nav)
