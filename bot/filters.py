"""Maxsus filtrlar."""
from aiogram.filters import BaseFilter
from aiogram.types import CallbackQuery, Message

from bot.config import config


class IsAdmin(BaseFilter):
    """Faqat ADMIN_IDS ro'yxatidagi foydalanuvchilarni o'tkazadi."""

    async def __call__(self, event: Message | CallbackQuery) -> bool:
        return event.from_user is not None and event.from_user.id in config.admin_ids
