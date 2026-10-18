import asyncio
import logging
import os
import re

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton,
    Message, ReplyKeyboardMarkup, ReplyKeyboardRemove,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder
from dotenv import load_dotenv

import db
from texts import REGIONS, region_name, t

load_dotenv()
router = Router()
TOTAL = 5


class Reg(StatesGroup):
    lang = State()
    role = State()
    name = State()
    phone = State()
    region = State()
    district = State()
    confirm = State()


def progress(step: int) -> str:
    return "🟦" * step + "⬜" * (TOTAL - step) + f"  {step}/{TOTAL}"


def normalize_phone(raw: str) -> str | None:
    digits = re.sub(r"\D", "", raw)
    if len(digits) == 9:
        digits = "998" + digits
    if len(digits) == 12 and digits.startswith("998"):
        return "+" + digits
    return None


def lang_kb(prefix: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🇺🇿 O'zbekcha", callback_data=f"{prefix}:uz"),
        InlineKeyboardButton(text="🇷🇺 Русский", callback_data=f"{prefix}:ru"),
    ]])

def roles_kb(lang: str) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for key in ("tenant", "landlord", "both"):
        b.button(text=t(lang, key), callback_data=f"role:{key}")
    return b.adjust(1).as_markup()


def regions_kb(lang: str) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for i, (uz, ru) in enumerate(REGIONS):
        b.button(text=ru if lang == "ru" else uz, callback_data=f"reg:{i}")
    return b.adjust(2).as_markup()


def phone_kb(lang: str) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=t(lang, "phone_btn"), request_contact=True)]],
        resize_keyboard=True, one_time_keyboard=True,
        input_field_placeholder=t(lang, "phone_ph"),
    )


def confirm_kb(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=t(lang, "ok_btn"), callback_data="ok"),
        InlineKeyboardButton(text=t(lang, "redo_btn"), callback_data="redo"),
    ]])


async def ask_language(message: Message, state: FSMContext):
    await state.clear()
    await state.set_state(Reg.lang)
    await message.answer(t("uz", "pick_lang"), reply_markup=lang_kb("lang"))


@router.message(CommandStart())
async def start(message: Message, state: FSMContext):
    user = await db.get_user(message.from_user.id)
    if user:
        await state.clear()
        await message.answer(t(user["lang"], "again", n=user["full_name"]))
        return
    await ask_language(message, state)


@router.message(Command("register"))
async def register(message: Message, state: FSMContext):
    await ask_language(message, state)


@router.message(Command("til", "lang"))
async def change_lang(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(t("uz", "pick_lang"), reply_markup=lang_kb("setlang"))


@router.callback_query(F.data.startswith("setlang:"))
async def set_lang(cb: CallbackQuery):
    lang = cb.data.split(":")[1]
    await db.set_lang(cb.from_user.id, lang)
    await cb.message.edit_text(t(lang, "lang_changed"))
    await cb.answer()


@router.message(Command("profile"))
async def profile(message: Message):
    u = await db.get_user(message.from_user.id)
    if not u:
        await message.answer(t("uz", "no_reg"))
        return
    lang = u["lang"]
    await message.answer(t(
        lang, "profile", name=u["full_name"], phone=u["phone"],
        role=t(lang, u["role"]), region=region_name(lang, u["region"]),
        district=u["district"], date=f"{u['created_at']:%d.%m.%Y}",
    ))


@router.callback_query(Reg.lang, F.data.startswith("lang:"))
async def got_lang(cb: CallbackQuery, state: FSMContext):
    lang = cb.data.split(":")[1]
    await state.update_data(lang=lang)
    await state.set_state(Reg.role)
    await cb.message.edit_text(t(lang, "welcome"))
    await cb.message.answer(
        f"{progress(1)}\n{t(lang, 'ask_role')}", reply_markup=roles_kb(lang)
    )
    await cb.answer()


@router.callback_query(Reg.role, F.data.startswith("role:"))
async def got_role(cb: CallbackQuery, state: FSMContext):
    lang = (await state.get_data())["lang"]
    role = cb.data.split(":")[1]
    await state.update_data(role=role)
    await state.set_state(Reg.name)
    await cb.message.edit_text(t(lang, "chosen", x=t(lang, role)))
    await cb.message.answer(f"{progress(2)}\n{t(lang, 'ask_name')}")
    await cb.answer()


@router.message(Reg.name, F.text)
async def got_name(message: Message, state: FSMContext):
    lang = (await state.get_data())["lang"]
    name = " ".join(message.text.split())
    if len(name) < 3 or len(name) > 60 or re.search(r"[\d@#$%^&*()_+=<>/\\]", name):
        await message.answer(t(lang, "bad_name"))
        return
    await state.update_data(full_name=name.title())
    await state.set_state(Reg.phone)
    await message.answer(
        f"{progress(3)}\n" + t(lang, "ask_phone", n=name.split()[0].title()),
        reply_markup=phone_kb(lang),
    )


async def ask_region(message: Message, state: FSMContext, phone: str):
    lang = (await state.get_data())["lang"]
    await state.update_data(phone=phone)
    await state.set_state(Reg.region)
    await message.answer(t(lang, "phone_ok"), reply_markup=ReplyKeyboardRemove())
    await message.answer(
        f"{progress(4)}\n{t(lang, 'ask_region')}", reply_markup=regions_kb(lang)
    )


@router.message(Reg.phone, F.contact)
async def got_contact(message: Message, state: FSMContext):
    lang = (await state.get_data())["lang"]
    if message.contact.user_id != message.from_user.id:
        await message.answer(t(lang, "not_own"))
        return
    phone = normalize_phone(message.contact.phone_number)
    if not phone:
        await message.answer(t(lang, "bad_phone"))
        return
    await ask_region(message, state, phone)


@router.message(Reg.phone, F.text)
async def got_phone_text(message: Message, state: FSMContext):
    lang = (await state.get_data())["lang"]
    phone = normalize_phone(message.text)
    if not phone:
        await message.answer(t(lang, "bad_phone"))
        return
    await ask_region(message, state, phone)


@router.callback_query(Reg.region, F.data.startswith("reg:"))
async def got_region(cb: CallbackQuery, state: FSMContext):
    lang = (await state.get_data())["lang"]
    uz_name = REGIONS[int(cb.data.split(":")[1])][0]
    await state.update_data(region=uz_name)
    await state.set_state(Reg.district)
    await cb.message.edit_text(t(lang, "region_chosen", x=region_name(lang, uz_name)))
    await cb.message.answer(t(lang, "ask_district"))
    await cb.answer()


@router.message(Reg.district, F.text)
async def got_district(message: Message, state: FSMContext):
    lang = (await state.get_data())["lang"]
    district = " ".join(message.text.split())
    if len(district) < 2 or len(district) > 60:
        await message.answer(t(lang, "bad_district"))
        return
    await state.update_data(district=district.title())
    d = await state.get_data()
    await state.set_state(Reg.confirm)
    await message.answer(
        f"{progress(5)}\n{t(lang, 'check')}\n\n"
        f"👤 {d['full_name']}\n📱 {d['phone']}\n🎯 {t(lang, d['role'])}\n"
        f"📍 {region_name(lang, d['region'])}, {d['district']}",
        reply_markup=confirm_kb(lang),
    )


@router.callback_query(Reg.confirm, F.data == "ok")
async def confirm(cb: CallbackQuery, state: FSMContext):
    d = await state.get_data()
    await db.save_user(cb.from_user.id, cb.from_user.username, d)
    await state.clear()
    await cb.message.edit_text(t(d["lang"], "done"))
    await cb.answer(t(d["lang"], "saved"))


@router.callback_query(Reg.confirm, F.data == "redo")
async def redo(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    await ask_language(cb.message, state)


@router.message(Reg.lang)
@router.message(Reg.role)
@router.message(Reg.region)
@router.message(Reg.confirm)
async def use_buttons(message: Message, state: FSMContext):
    lang = (await state.get_data()).get("lang", "uz")
    await message.answer(t(lang, "use_buttons"))


async def main():
    logging.basicConfig(level=logging.INFO)
    await db.init_db(os.environ["DATABASE_URL"])
    bot = Bot(os.environ["BOT_TOKEN"],
              default=DefaultBotProperties(parse_mode="HTML"))
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
