"""Middleware'lar: foydalanuvchini ro'yxatga olish, til, rol va bloklanganlarni to'xtatish."""
from __future__ import annotations

from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from bot import db
from bot.i18n import norm_lang, t


class UserMiddleware(BaseMiddleware):
    """
    Har bir xabar/callback uchun:
      1. foydalanuvchini bazaga yozadi;
      2. handlerlarga `db_user`, `lang`, `is_admin`, `is_superadmin` beradi;
      3. bloklangan (admin bo'lmagan) foydalanuvchini to'xtatadi.
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

        user_row = await db.upsert_user(tg_user.id, tg_user.full_name, tg_user.username)
        data["db_user"] = user_row
        # Saqlangan til; bo'lmasa Telegram tili; bo'lmasa o'zbekcha
        data["lang"] = user_row["lang"] or norm_lang(tg_user.language_code)
        data["lang_chosen"] = user_row["lang"] is not None
        data["is_superadmin"] = db.is_superadmin(tg_user.id)
        data["is_admin"] = data["is_superadmin"] or await db.is_admin(tg_user.id)

        if user_row["is_blocked"] and not data["is_admin"]:
            text = t(data["lang"], "blocked")
            if user_row["block_reason"]:
                text += "\n" + t(data["lang"], "blocked_reason", reason=user_row["block_reason"])
            if isinstance(event, Message):
                await event.answer(text)
            elif isinstance(event, CallbackQuery):
                await event.answer(text, show_alert=True)
            return None

        return await handler(event, data)
