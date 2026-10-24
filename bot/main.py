"""Botni ishga tushirish nuqtasi: `python -m bot.main`"""
import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand, BotCommandScopeChat

from bot import db
from bot.config import config
from bot.handlers import admin, user
from bot.middlewares import UserMiddleware

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
log = logging.getLogger("chirchiq_arenda")


async def set_commands(bot: Bot) -> None:
    await bot.set_my_commands([BotCommand(command="start", description="Botni ishga tushirish")])
    for admin_id in config.admin_ids:
        try:
            await bot.set_my_commands(
                [
                    BotCommand(command="start", description="Botni ishga tushirish"),
                    BotCommand(command="admin", description="Admin panel"),
                ],
                scope=BotCommandScopeChat(chat_id=admin_id),
            )
        except Exception as exc:  # admin hali botga yozmagan bo'lishi mumkin
            log.warning("Admin %s uchun komandalar o'rnatilmadi: %s", admin_id, exc)


async def main() -> None:
    await db.init_db()
    log.info("PostgreSQL ulandi, sxema tayyor.")

    bot = Bot(token=config.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=MemoryStorage())

    # Middleware: ro'yxatga olish + bloklanganlarni to'xtatish
    dp.message.outer_middleware(UserMiddleware())
    dp.callback_query.outer_middleware(UserMiddleware())

    # Admin router birinchi — admin tugmalari user routerdan oldin ushlansin
    dp.include_router(admin.router)
    dp.include_router(user.router)

    await set_commands(bot)
    log.info("Bot ishga tushdi. Adminlar: %s", sorted(config.admin_ids))

    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)
    finally:
        await db.close_db()
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        log.info("Bot to'xtatildi.")
