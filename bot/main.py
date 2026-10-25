"""Botni ishga tushirish nuqtasi: `python -m bot.main`"""
import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    BotCommand,
    BotCommandScopeChat,
    MenuButtonDefault,
    MenuButtonWebApp,
    WebAppInfo,
)

from bot import db, sync, tunnel
from bot.config import config
from bot.handlers import admin, user
from bot.middlewares import UserMiddleware
from bot.webapp.server import start_server

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
log = logging.getLogger("chirchiq_arenda")


async def set_commands(bot: Bot, webapp_url: str) -> None:
    await bot.set_my_commands([BotCommand(command="start", description="Botni ishga tushirish")])

    # Hamma uchun chat pastidagi "Menu" tugmasi -> uylar bozori (Mini App)
    try:
        if webapp_url:
            await bot.set_chat_menu_button(
                menu_button=MenuButtonWebApp(text="🏠 Uylar", web_app=WebAppInfo(url=webapp_url + "/market"))
            )
        else:
            await bot.set_chat_menu_button(menu_button=MenuButtonDefault())
    except Exception as exc:  # noqa: BLE001
        log.warning("Umumiy menyu tugmasi o'rnatilmadi: %s", exc)

    admin_cmds = [
        BotCommand(command="start", description="Botni ishga tushirish"),
        BotCommand(command="admin", description="Admin panel (Mini App)"),
        BotCommand(command="menu", description="Admin menyu (tugmali)"),
    ]
    for admin_id in config.admin_ids:
        try:
            await bot.set_my_commands(admin_cmds, scope=BotCommandScopeChat(chat_id=admin_id))
            if webapp_url:
                await bot.set_chat_menu_button(
                    chat_id=admin_id,
                    menu_button=MenuButtonWebApp(text="Admin", web_app=WebAppInfo(url=webapp_url)),
                )
        except Exception as exc:  # admin hali botga yozmagan bo'lishi mumkin
            log.warning("Admin %s uchun komandalar o'rnatilmadi: %s", admin_id, exc)


async def resolve_webapp_url() -> str:
    """WEBAPP_URL berilgan bo'lsa shuni, aks holda cloudflared tunnel manzilini qaytaradi."""
    if config.webapp_url:
        return config.webapp_url
    if tunnel.available():
        log.info("WEBAPP_URL yo'q — cloudflared tunnel ochilmoqda...")
        url = await tunnel.start(config.webapp_port)
        if url:
            return url
        log.warning("Tunnel ochilmadi; Mini App tugmalari ko'rinmaydi.")
    else:
        log.warning("WEBAPP_URL yo'q va cloudflared topilmadi; Mini App tugmalari ko'rinmaydi.")
    return ""


async def main() -> None:
    await db.init_db()
    log.info("PostgreSQL ulandi, sxema tayyor.")

    bot = Bot(token=config.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=MemoryStorage())

    dp.message.outer_middleware(UserMiddleware())
    dp.callback_query.outer_middleware(UserMiddleware())

    dp.include_router(admin.router)
    dp.include_router(user.router)

    runner = await start_server(bot)
    webapp_url = await resolve_webapp_url()
    dp["webapp_url"] = webapp_url  # handlerlarga `webapp_url` argumenti sifatida keladi
    if webapp_url:
        log.info("Admin Mini App: %s", webapp_url)
        log.info("Market Mini App: %s/market", webapp_url)

    await set_commands(bot, webapp_url)
    sync.start_background()
    log.info("Bot ishga tushdi. Adminlar: %s", sorted(config.admin_ids))

    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)
    finally:
        await sync.stop_background()
        await runner.cleanup()
        await tunnel.stop()
        await db.close_db()
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        log.info("Bot to'xtatildi.")
