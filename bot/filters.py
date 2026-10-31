"""Maxsus filtrlar."""
from aiogram.filters import BaseFilter
from aiogram.types import CallbackQuery, Message

from bot import db


class IsAdmin(BaseFilter):
    """Superadmin (ADMIN_IDS) yoki admins jadvalidagi foydalanuvchi."""

    async def __call__(self, event: Message | CallbackQuery) -> bool:
        return event.from_user is not None and await db.is_admin(event.from_user.id)


class IsSuperAdmin(BaseFilter):
    """Faqat ADMIN_IDS ro'yxatidagilar."""

    async def __call__(self, event: Message | CallbackQuery) -> bool:
        return event.from_user is not None and db.is_superadmin(event.from_user.id)
