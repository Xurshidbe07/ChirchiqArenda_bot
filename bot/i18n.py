"""Bot matnlari tarjimasi: uz / ru / en.

Ishlatish: t(lang, "welcome", name="Ali")
Mini App'lar o'z tarjimalarini HTML ichida saqlaydi (static/market.html, static/index.html).
"""
from __future__ import annotations

LANGS = ("uz", "ru", "en")
DEFAULT_LANG = "uz"

LANG_NAMES = {"uz": "🇺🇿 O'zbekcha", "ru": "🇷🇺 Русский", "en": "🇬🇧 English"}

_T: dict[str, dict[str, str]] = {
    "uz": {
        "choose_lang": "🌐 Tilni tanlang / Выберите язык / Choose a language:",
        "lang_set": "✅ Til: O'zbekcha",
        "welcome": (
            "Assalomu alaykum, <b>{name}</b>! 👋\n\n"
            "<b>Chirchiq Arenda</b> — Chirchiq shahridagi ijara uylar bir joyda.\n"
            "E'lonlar muntazam yangilanib turadi.\n\n"
            "Pastdagi tugma orqali bozorni oching 👇"
        ),
        "market_title": "🏠 Ijara uylar bozori:",
        "market_btn": "🏠 Uylar bozorini ochish",
        "menu_btn": "🏠 Uylar",
        "btn_houses": "🏠 Uylar",
        "btn_contact": "📞 Aloqa",
        "btn_lang": "🌐 Til",
        "contact": (
            "📞 <b>Aloqa</b>\n\n"
            "Savollar bo'yicha adminlarga murojaat qiling.\n"
            "Uy egasi bilan bog'lanish raqami har bir e'lon ichida ko'rsatilgan."
        ),
        "blocked": "⛔️ Siz botdan foydalanishdan bloklangansiz.",
        "blocked_reason": "Sabab: {reason}",
        "no_ads": "Hozircha e'lonlar yo'q. Keyinroq qayta urinib ko'ring.",
        "ad_not_found": "E'lon topilmadi.",
        "ads_left_none": "E'lonlar qolmadi",
        "rooms": "Xonalar",
        "per_month": "/ oy",
        "mod_approved": "✅ Sizning «{title}» e'loningiz tasdiqlandi va bozorda ko'rinmoqda!",
        "mod_rejected": "❌ Sizning «{title}» e'loningiz rad etildi.",
        "mod_reason": "Sabab: {reason}",
        "mod_deleted": "🗑 Sizning «{title}» e'loningiz admin tomonidan o'chirildi.",
        "ad_received": "📨 E'loningiz qabul qilindi va moderatsiyaga yuborildi. Tasdiqlangach xabar beramiz.",
        "ad_published": "📢 E'loningiz «{title}» bozorga joylandi!",
    },
    "ru": {
        "choose_lang": "🌐 Tilni tanlang / Выберите язык / Choose a language:",
        "lang_set": "✅ Язык: Русский",
        "welcome": (
            "Здравствуйте, <b>{name}</b>! 👋\n\n"
            "<b>Chirchiq Arenda</b> — аренда жилья в Чирчике в одном месте.\n"
            "Объявления регулярно обновляются.\n\n"
            "Откройте маркет кнопкой ниже 👇"
        ),
        "market_title": "🏠 Маркет аренды жилья:",
        "market_btn": "🏠 Открыть маркет жилья",
        "menu_btn": "🏠 Жильё",
        "btn_houses": "🏠 Жильё",
        "btn_contact": "📞 Контакты",
        "btn_lang": "🌐 Язык",
        "contact": (
            "📞 <b>Контакты</b>\n\n"
            "По вопросам обращайтесь к администраторам.\n"
            "Номер владельца указан внутри каждого объявления."
        ),
        "blocked": "⛔️ Вы заблокированы и не можете пользоваться ботом.",
        "blocked_reason": "Причина: {reason}",
        "no_ads": "Пока объявлений нет. Попробуйте позже.",
        "ad_not_found": "Объявление не найдено.",
        "ads_left_none": "Объявлений больше нет",
        "rooms": "Комнат",
        "per_month": "/ мес",
        "mod_approved": "✅ Ваше объявление «{title}» одобрено и опубликовано!",
        "mod_rejected": "❌ Ваше объявление «{title}» отклонено.",
        "mod_reason": "Причина: {reason}",
        "mod_deleted": "🗑 Ваше объявление «{title}» удалено администратором.",
        "ad_received": "📨 Объявление принято и отправлено на модерацию. Сообщим после проверки.",
        "ad_published": "📢 Ваше объявление «{title}» опубликовано!",
    },
    "en": {
        "choose_lang": "🌐 Tilni tanlang / Выберите язык / Choose a language:",
        "lang_set": "✅ Language: English",
        "welcome": (
            "Hello, <b>{name}</b>! 👋\n\n"
            "<b>Chirchiq Arenda</b> — rental housing in Chirchiq, all in one place.\n"
            "Listings are updated regularly.\n\n"
            "Open the market with the button below 👇"
        ),
        "market_title": "🏠 Rental housing market:",
        "market_btn": "🏠 Open housing market",
        "menu_btn": "🏠 Housing",
        "btn_houses": "🏠 Housing",
        "btn_contact": "📞 Contact",
        "btn_lang": "🌐 Language",
        "contact": (
            "📞 <b>Contact</b>\n\n"
            "For questions, contact the administrators.\n"
            "The owner's phone number is shown inside each listing."
        ),
        "blocked": "⛔️ You are blocked from using this bot.",
        "blocked_reason": "Reason: {reason}",
        "no_ads": "No listings yet. Please try again later.",
        "ad_not_found": "Listing not found.",
        "ads_left_none": "No more listings",
        "rooms": "Rooms",
        "per_month": "/ month",
        "mod_approved": "✅ Your listing “{title}” has been approved and is now live!",
        "mod_rejected": "❌ Your listing “{title}” was rejected.",
        "mod_reason": "Reason: {reason}",
        "mod_deleted": "🗑 Your listing “{title}” was removed by an administrator.",
        "ad_received": "📨 Your listing was received and sent for moderation. We'll notify you once reviewed.",
        "ad_published": "📢 Your listing “{title}” is now live!",
    },
}


def norm_lang(code: str | None) -> str:
    """Telegram language_code yoki saqlangan qiymatni uz/ru/en ga keltiradi."""
    if not code:
        return DEFAULT_LANG
    code = code.lower()[:2]
    return code if code in LANGS else DEFAULT_LANG


def t(lang: str | None, key: str, **kw) -> str:
    lang = norm_lang(lang)
    text = _T.get(lang, _T[DEFAULT_LANG]).get(key) or _T[DEFAULT_LANG].get(key, key)
    return text.format(**kw) if kw else text


def all_variants(key: str) -> set[str]:
    """Bitta tugma matnining barcha tillardagi variantlari (handler filtri uchun)."""
    return {_T[lang][key] for lang in LANGS if key in _T[lang]}
