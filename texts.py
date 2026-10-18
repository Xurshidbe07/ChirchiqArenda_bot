REGIONS = [  # (uz, ru); bazada o'zbekcha nom saqlanadi
    ("Toshkent shahri", "г. Ташкент"), ("Toshkent viloyati", "Ташкентская обл."),
    ("Samarqand", "Самарканд"), ("Buxoro", "Бухара"),
    ("Andijon", "Андижан"), ("Farg'ona", "Фергана"),
    ("Namangan", "Наманган"), ("Qashqadaryo", "Кашкадарья"),
    ("Surxondaryo", "Сурхандарья"), ("Xorazm", "Хорезм"),
    ("Navoiy", "Навои"), ("Jizzax", "Джизак"),
    ("Sirdaryo", "Сырдарья"), ("Qoraqalpog'iston", "Каракалпакстан"),
]

T = {
    "uz": {
        "pick_lang": "🌐 Tilni tanlang / Выберите язык",
        "welcome": ("👋 <b>Assalomu alaykum! Ijara olamiga xush kelibsiz!</b>\n\n"
                    "Bu yerda siz uy, kvartira, mashina yoki jihozlarni "
                    "<b>tez va ishonchli</b> ijaraga olish yoki berishingiz mumkin.\n\n"
                    "Keling, 1 daqiqada tanishib olamiz 🚀"),
        "ask_role": "<b>Siz kimsiz?</b>",
        "tenant": "🔑 Ijaraga olaman", "landlord": "🏠 Ijaraga beraman", "both": "🔄 Ikkalasi ham",
        "chosen": "Tanlovingiz: <b>{x}</b> ✅",
        "ask_name": "<b>Ismingiz va familiyangiz?</b>\nMasalan: <i>Aziz Karimov</i>",
        "bad_name": "🙅 Iltimos, haqiqiy ism-familiyani yozing (faqat harflar).",
        "ask_phone": ("Rahmat, <b>{n}</b>! 🤝\n\n<b>Telefon raqamingiz?</b>\n"
                      "Pastdagi tugma orqali yuboring yoki o'zingiz yozing."),
        "phone_btn": "📱 Raqamni yuborish", "phone_ph": "yoki +998901234567 deb yozing",
        "not_own": "⚠️ Iltimos, o'zingizning raqamingizni yuboring.",
        "bad_phone": "⚠️ Format noto'g'ri. Faqat O'zbekiston raqami: <code>+998901234567</code>",
        "phone_ok": "📞 Raqam saqlandi!",
        "ask_region": "<b>Qaysi hududdasiz?</b> 📍",
        "region_chosen": "Hudud: <b>{x}</b> ✅",
        "ask_district": "🏘 <b>Tuman yoki shahringiz?</b>\nMasalan: <i>Chilonzor</i>",
        "bad_district": "🙅 Tuman nomini to'g'ri yozing.",
        "check": "<b>Ma'lumotlaringizni tekshiring:</b>",
        "ok_btn": "✅ Tasdiqlash", "redo_btn": "✏️ Qaytadan",
        "done": ("🎉 <b>Tabriklaymiz! Ro'yxatdan muvaffaqiyatli o'tdingiz!</b>\n\n"
                 "Endi sizga ijara olamining barcha imkoniyatlari ochiq.\nProfilingiz: /profile"),
        "saved": "Saqlandi ✅",
        "again": ("😊 Qaytganingiz bilan, <b>{n}</b>!\nSiz allaqachon ro'yxatdan o'tgansiz.\n\n"
                  "Ma'lumotlarni yangilash: /register\nProfil: /profile\nTilni o'zgartirish: /til"),
        "no_reg": "Avval ro'yxatdan o'ting: /start",
        "profile": ("👤 <b>Sizning profilingiz</b>\n\nIsm: {name}\nTelefon: {phone}\n"
                    "Maqsad: {role}\nHudud: {region}, {district}\nRo'yxatdan o'tgan: {date}"),
        "use_buttons": "👆 Iltimos, yuqoridagi tugmalardan birini tanlang.",
        "lang_changed": "✅ Til o'zgartirildi: O'zbekcha",
    },
    "ru": {
        "pick_lang": "🌐 Tilni tanlang / Выберите язык",
        "welcome": ("👋 <b>Здравствуйте! Добро пожаловать в мир аренды!</b>\n\n"
                    "Здесь вы можете <b>быстро и надёжно</b> арендовать или сдать жильё, "
                    "авто и оборудование.\n\nДавайте познакомимся за 1 минуту 🚀"),
        "ask_role": "<b>Кто вы?</b>",
        "tenant": "🔑 Хочу арендовать", "landlord": "🏠 Хочу сдавать", "both": "🔄 И то и другое",
        "chosen": "Ваш выбор: <b>{x}</b> ✅",
        "ask_name": "<b>Ваше имя и фамилия?</b>\nНапример: <i>Азиз Каримов</i>",
        "bad_name": "🙅 Пожалуйста, введите настоящие имя и фамилию (только буквы).",
        "ask_phone": ("Спасибо, <b>{n}</b>! 🤝\n\n<b>Ваш номер телефона?</b>\n"
                      "Отправьте кнопкой ниже или введите вручную."),
        "phone_btn": "📱 Отправить номер", "phone_ph": "или введите +998901234567",
        "not_own": "⚠️ Пожалуйста, отправьте свой собственный номер.",
        "bad_phone": "⚠️ Неверный формат. Только номера Узбекистана: <code>+998901234567</code>",
        "phone_ok": "📞 Номер сохранён!",
        "ask_region": "<b>В каком вы регионе?</b> 📍",
        "region_chosen": "Регион: <b>{x}</b> ✅",
        "ask_district": "🏘 <b>Ваш район или город?</b>\nНапример: <i>Чиланзар</i>",
        "bad_district": "🙅 Введите название района правильно.",
        "check": "<b>Проверьте ваши данные:</b>",
        "ok_btn": "✅ Подтвердить", "redo_btn": "✏️ Заново",
        "done": ("🎉 <b>Поздравляем! Регистрация прошла успешно!</b>\n\n"
                 "Теперь вам доступны все возможности аренды.\nВаш профиль: /profile"),
        "saved": "Сохранено ✅",
        "again": ("😊 С возвращением, <b>{n}</b>!\nВы уже зарегистрированы.\n\n"
                  "Обновить данные: /register\nПрофиль: /profile\nСменить язык: /til"),
        "no_reg": "Сначала зарегистрируйтесь: /start",
        "profile": ("👤 <b>Ваш профиль</b>\n\nИмя: {name}\nТелефон: {phone}\n"
                    "Цель: {role}\nРегион: {region}, {district}\nДата регистрации: {date}"),
        "use_buttons": "👆 Пожалуйста, выберите один из вариантов кнопками выше.",
        "lang_changed": "✅ Язык изменён: Русский",
    },
}


def t(lang: str, key: str, **kw) -> str:
    s = T.get(lang, T["uz"])[key]
    return s.format(**kw) if kw else s


def region_name(lang: str, uz_name: str) -> str:
    for uz, ru in REGIONS:
        if uz == uz_name:
            return ru if lang == "ru" else uz
    return uz_name
