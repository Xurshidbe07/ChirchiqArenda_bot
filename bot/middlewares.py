"""Middleware'lar: foydalanuvchini ro'yxatga olish va bloklanganlarni to'xtatish."""
from __future__ import annotations

from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from bot import db
from bot.config import config


class UserMiddleware(BaseMiddleware):
    """
    Har bir xabar/callback uchun:
      1. foydalanuvchini bazaga yozadi (yoki ismini yangilaydi);
      2. agar bloklangan bo'lsa va admin bo'lmasa — javob berib, handlerga o'tkazmaydi.
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        tg_user = data.get("event_from_user")
        if tg_user is None:
            return await handler(event, data)

        user_row = await db.upsert_user(
            tg_user.id,
            tg_user.full_name,
            tg_user.username,
        )
        data["db_user"] = user_row
        data["is_admin"] = tg_user.id in config.admin_ids

        if user_row["is_blocked"] and not data["is_admin"]:
            text = "⛔️ Siz botdan foydalanishdan bloklangansiz."
            if user_row["block_reason"]:
                text += f"\nSabab: {user_row['block_reason']}"
            if isinstance(event, Message):
                await event.answer(text)
            elif isinstance(event, CallbackQuery):
                await event.answer(text, show_alert=True)
            return None

        return await handler(event, data)
