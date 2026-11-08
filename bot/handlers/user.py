"""Oddiy foydalanuvchi (klient) qismi: /start, til tanlash, market Mini App, aloqa.

Asosiy klient interfeysi — Mini App (bot/webapp/static/market.html).
Matnli varaqlash zaxira variant (Mini App ishlamasa).
Admin panel bu yerda ko'rsatilmaydi — faqat /admin buyrug'i orqali (bot/handlers/admin.py).
"""
from __future__ import annotations

import html
import logging
from decimal import Decimal

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
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
from bot.config import config
from bot.i18n import LANGS, all_variants, t
from bot.scrapers.olx import OLXBlocked, get_scraper

log = logging.getLogger("handlers.user")
router = Router(name="user")


def market_kb(lang: str, webapp_url: str) -> InlineKeyboardMarkup | None:
    """Market Mini App tugmasi + (sozlangan bo'lsa) OLX'ga o'tish tugmasi."""
    rows: list[list[InlineKeyboardButton]] = []
    if webapp_url:
        rows.append([InlineKeyboardButton(text=t(lang, "market_btn"), web_app=WebAppInfo(url=webapp_url + "/market"))])
    if config.olx_url:
        rows.append([InlineKeyboardButton(text=t(lang, "olx_btn"), url=config.olx_url)])
    return InlineKeyboardMarkup(inline_keyboard=rows) if rows else None


def olx_kb(lang: str) -> InlineKeyboardMarkup | None:
    """Bosilganda to'g'ridan-to'g'ri OLX sahifasini ochadigan «OLXda» tugmasi."""
    if not config.olx_url:
        return None
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=t(lang, "olx_btn"), url=config.olx_url)]])


async def send_welcome(message: Message, lang: str, webapp_url: str) -> None:
    await message.answer(
        t(lang, "welcome", name=html.escape(message.from_user.full_name)),
        reply_markup=kb.user_menu(lang),
    )
    markup = market_kb(lang, webapp_url)
    if markup:
        await message.answer(t(lang, "market_title"), reply_markup=markup)


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, lang: str, lang_chosen: bool,
                    webapp_url: str = "") -> None:
    await state.clear()
    if not lang_chosen:
        await message.answer(t(lang, "choose_lang"), reply_markup=kb.lang_kb())
        return
    await send_welcome(message, lang, webapp_url)


@router.message(Command("lang"))
@router.message(F.text.in_(all_variants("btn_lang")))
async def cmd_lang(message: Message, lang: str) -> None:
    await message.answer(t(lang, "choose_lang"), reply_markup=kb.lang_kb())


@router.callback_query(F.data.startswith("lang:"))
async def set_lang(call: CallbackQuery, webapp_url: str = "") -> None:
    code = call.data.split(":")[1]
    if code not in LANGS:
        await call.answer()
        return
    await db.set_lang(call.from_user.id, code)
    await call.answer(t(code, "lang_set"))
    try:
        await call.message.edit_text(t(code, "lang_set"))
    except Exception:
        pass
    # call.message.from_user — bot; ismni call.from_user dan olamiz
    await call.message.answer(
        t(code, "welcome", name=html.escape(call.from_user.full_name)),
        reply_markup=kb.user_menu(code),
    )
    markup = market_kb(code, webapp_url)
    if markup:
        await call.message.answer(t(code, "market_title"), reply_markup=markup)


@router.message(Command("olx"))
@router.message(F.text.in_(all_variants("btn_olx")))
async def olx_offers(message: Message, lang: str) -> None:
    """OLX'dagi so'nggi Chirchiq ijara e'lonlari; OLX javob bermasa — OLX havolasi."""
    wait = await message.answer(t(lang, "olx_loading"))
    try:
        offers = await get_scraper().latest(5)
    except OLXBlocked as exc:
        log.warning("OLX so'rovni rad etdi: %s", exc)
        offers = []
    except Exception:  # noqa: BLE001
        log.exception("OLX'dan e'lon olishda xato")
        offers = []

    if not offers:
        await wait.edit_text(t(lang, "olx_fail"), reply_markup=olx_kb(lang))
        return

    blocks = [t(lang, "olx_head")]
    for i, o in enumerate(offers, 1):
        place = f"\n📍 {html.escape(o.location)}" if o.location else ""
        blocks.append(
            f'{i}. <a href="{html.escape(o.url)}">{html.escape(o.title)}</a>\n'
            f"💰 {html.escape(o.price)}{place}"
        )
    blocks.append(t(lang, "olx_more"))
    await wait.edit_text("\n\n".join(blocks), reply_markup=olx_kb(lang), disable_web_page_preview=True)


@router.message(F.text.in_(all_variants("btn_contact")))
async def contact(message: Message, lang: str) -> None:
    await message.answer(t(lang, "contact"))


@router.message(F.text.in_(all_variants("btn_houses")))
async def houses_start(message: Message, lang: str, webapp_url: str = "") -> None:
    markup = market_kb(lang, webapp_url)
    if markup:
        await message.answer(t(lang, "market_title"), reply_markup=markup)
        return
    total = await db.count_houses(only_active=True)
    if total == 0:
        await message.answer(t(lang, "no_ads"))
        return
    await _send_house(message, lang, index=0, total=total)


@router.callback_query(F.data.startswith("uh:"))
async def houses_nav(call: CallbackQuery, lang: str) -> None:
    arg = call.data.split(":")[1]
    if arg == "noop":
        await call.answer()
        return
    index = int(arg)
    total = await db.count_houses(only_active=True)
    if total == 0:
        await call.answer(t(lang, "ads_left_none"), show_alert=True)
        return
    index = min(index, total - 1)
    await call.answer()
    try:
        await call.message.delete()
    except Exception:
        pass
    await _send_house(call.message, lang, index=index, total=total)


async def _send_house(message: Message, lang: str, index: int, total: int) -> None:
    rows = await db.list_houses(offset=index, limit=1, only_active=True)
    if not rows:
        await message.answer(t(lang, "ad_not_found"))
        return
    h = rows[0]
    price = f"{Decimal(h['price']):,.0f}".replace(",", " ")
    unit = "y.e" if h["currency"] == "USD" else "so'm"
    caption = (
        f"🏠 <b>{html.escape(h['title'])}</b>\n"
        f"📍 {html.escape(h['address'])}\n"
        + (f"🚪 {t(lang, 'rooms')}: {h['rooms']}\n" if h["rooms"] else "")
        + f"💰 {price} {unit} {t(lang, 'per_month')}\n"
    )
    if h["description"]:
        caption += f"\n📝 {html.escape(h['description'][:600])}\n"
    if h["contact_phone"]:
        caption += f"\n📞 {html.escape(h['contact_phone'])}"
    markup = kb.house_nav_kb(index, total)
    photos = list(h["photo_urls"] or [])
    first = photos[0] if photos else (f"tg:{h['photo_file_id']}" if h["photo_file_id"] else None)
    if first:
        media = first[3:] if first.startswith("tg:") else first
        try:
            await message.answer_photo(media, caption=caption[:1024], reply_markup=markup)
            return
        except Exception:
            pass
    await message.answer(caption, reply_markup=markup)
