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

from bot import db, keepalive, sync, tunnel
from bot.config import config
from bot.handlers import admin, user
from bot.i18n import LANGS, t
from bot.middlewares import UserMiddleware
from bot.webapp.server import start_server

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
log = logging.getLogger("chirchiq_arenda")

_CMD_DESC = {
    "uz": {"start": "Botni ishga tushirish", "lang": "Tilni o'zgartirish"},
    "ru": {"start": "Запустить бота", "lang": "Сменить язык"},
    "en": {"start": "Start the bot", "lang": "Change language"},
}


async def set_commands(bot: Bot, webapp_url: str) -> None:
    # Hamma uchun: /start, /lang (har tilda)
    for code in LANGS:
        d = _CMD_DESC[code]
        try:
            await bot.set_my_commands(
                [BotCommand(command="start", description=d["start"]),
                 BotCommand(command="lang", description=d["lang"])],
                language_code=code,
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("Komandalar (%s) o'rnatilmadi: %s", code, exc)
    await bot.set_my_commands([BotCommand(command="start", description=_CMD_DESC["uz"]["start"]),
                               BotCommand(command="lang", description=_CMD_DESC["uz"]["lang"])])

    # Hamma uchun chat pastidagi "Menu" tugmasi -> uylar bozori (admin panel bu yerda ko'rinmaydi)
    try:
        if webapp_url:
            await bot.set_chat_menu_button(
                menu_button=MenuButtonWebApp(text=t("uz", "menu_btn"), web_app=WebAppInfo(url=webapp_url + "/market"))
            )
        else:
            await bot.set_chat_menu_button(menu_button=MenuButtonDefault())
    except Exception as exc:  # noqa: BLE001
        log.warning("Umumiy menyu tugmasi o'rnatilmadi: %s", exc)

    # Adminlar uchun qo'shimcha buyruqlar (faqat buyruqlar ro'yxatida, /start da ko'rinmaydi)
    admin_cmds = [
        BotCommand(command="start", description="Botni ishga tushirish"),
        BotCommand(command="admin", description="Admin panel (Mini App)"),
        BotCommand(command="menu", description="Admin menyu (tugmali)"),
        BotCommand(command="lang", description="Tilni o'zgartirish"),
    ]
    for admin_id in await db.all_admin_ids():
        try:
            await bot.set_my_commands(admin_cmds, scope=BotCommandScopeChat(chat_id=admin_id))
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
    dp["webapp_url"] = webapp_url
    if webapp_url:
        log.info("Admin Mini App: %s", webapp_url)
        log.info("Market Mini App: %s/market", webapp_url)

    await set_commands(bot, webapp_url)
    sync.start_background()
    keepalive.start_background(webapp_url)
    log.info("Bot ishga tushdi. Superadminlar: %s", sorted(config.admin_ids))

    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)
    finally:
        await keepalive.stop_background()
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
