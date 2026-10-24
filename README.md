# ChirchiqArendabot 🏠

Chirchiq shahrida ijaraga uylar bo'yicha Telegram bot.
**Python 3.11+ · aiogram 3 · PostgreSQL (asyncpg)**

## Imkoniyatlar

### Admin Mini App (`/admin`)
`/admin` yuborilganda **«🛠 Admin panelni ochish»** tugmasi keladi — Telegram ichida interfeysli
Mini App ochiladi (chat pastidagi «Admin» menyu tugmasi ham shuni ochadi):

- 🏠 **Uylar** — ro'yxat (rasm, narx, holat), yashirish/ko'rsatish, o'chirish, «+ Uy qo'shish» formasi (rasm bilan)
- 👥 **Klientlar** — qidiruv (ism / @username / ID), filtr, bloklash (sabab bilan) / blokdan chiqarish
- 📊 **Statistika**

Texnik: `bot/webapp/server.py` (aiohttp API) + `bot/webapp/static/index.html`.
Har bir so'rov Telegram `initData` imzosi bilan tekshiriladi, faqat `ADMIN_IDS` kiradi.

Mini App uchun HTTPS manzil kerak:
- **Dev:** `WEBAPP_URL` bo'sh qoldiring va [cloudflared](https://github.com/cloudflare/cloudflared/releases)
  o'rnating (`winget install Cloudflare.cloudflared`). Bot ishga tushganda o'zi vaqtinchalik tunnel ochadi.
- **Server:** `WEBAPP_URL=https://sizning-domen.uz` yozing va 8080-portni nginx/caddy orqali HTTPS bilan oching.

### Tugmali admin menyu (`/menu`)
Mini App ishlamasa zaxira variant — oddiy reply-klaviatura:

| Tugma | Vazifasi |
|---|---|
| ➕ Uy qo'shish | Bosqichma-bosqich (FSM) yangi e'lon: nomi, manzil, xonalar, narx, tavsif, telefon, rasm → tasdiqlash |
| 🗑 Uy o'chirish | Ro'yxatdan tanlab, tasdiqlab o'chirish (sahifalash bilan) |
| 🏠 Uylar ro'yxati | Barcha e'lonlar (faol/nofaol) |
| 👥 Klientlar | Barcha klientlar; bosib bloklash / blokdan chiqarish |
| 🚫 Klient bloklash | Telegram ID yoki forward xabar orqali, sabab bilan |
| ✅ Blokdan chiqarish | Bloklanganlar ro'yxati |
| 📊 Statistika | Klientlar va uylar soni |

Bloklangan klientga bot javob bermaydi (middleware darajasida to'xtatiladi).

### Klient qismi
`/start` → ro'yxatdan o'tadi, «🏠 Uylar» tugmasi orqali e'lonlarni varaqlaydi.
Bu qism minimal — jamoa a'zolari `bot/handlers/user.py` da kengaytiradi.

## O'rnatish

```bash
git clone <repo-url>
cd ChirchiqArendabot
python -m venv .venv
# Windows:
.venv\Scripts\activate
# Linux/Mac:
# source .venv/bin/activate
pip install -r requirements.txt
```

### PostgreSQL

```sql
CREATE DATABASE chirchiq_arenda;
```

Jadvallar bot birinchi ishga tushganda `sql/schema.sql` dan avtomatik yaratiladi.

### Sozlash

```bash
copy .env.example .env     # Linux/Mac: cp .env.example .env
```

`.env` ichida:

```
BOT_TOKEN=<BotFather bergan token>
ADMIN_IDS=<sizning telegram id>,<boshqa admin id>
DATABASE_URL=postgresql://postgres:parol@localhost:5432/chirchiq_arenda
```

> ⚠️ `.env` fayli `.gitignore` da — tokenni hech qachon GitHub'ga yubormang.
> O'z Telegram ID ingizni [@userinfobot](https://t.me/userinfobot) orqali bilib oling.

### Ishga tushirish

```bash
python -m bot.main
```

## Loyiha tuzilishi

```
ChirchiqArendabot/
├── bot/
│   ├── main.py          # kirish nuqtasi, dispatcher
│   ├── config.py        # .env dan sozlamalar
│   ├── db.py            # PostgreSQL so'rovlari (asyncpg)
│   ├── middlewares.py   # foydalanuvchini ro'yxatga olish + blok tekshiruvi
│   ├── filters.py       # IsAdmin filtri
│   ├── keyboards.py     # reply/inline klaviaturalar
│   ├── states.py        # FSM holatlari
│   ├── tunnel.py        # dev uchun cloudflared HTTPS tunnel
│   ├── webapp/
│   │   ├── server.py    # Mini App API (aiohttp)
│   │   └── static/index.html  # Mini App interfeysi
│   └── handlers/
│       ├── admin.py     # /admin (Mini App), /menu (tugmali), admin handlerlar
│       └── user.py      # klient qismi
├── sql/schema.sql       # jadvallar
├── requirements.txt
├── .env.example
└── README.md
```

## Ma'lumotlar bazasi

- `users` — klientlar: `telegram_id`, `full_name`, `username`, `phone`, `is_blocked`, `block_reason`
- `houses` — e'lonlar: `title`, `address`, `rooms`, `price`, `description`, `photo_file_id`, `contact_phone`, `is_active`

## Jamoa uchun

- Admin funksiyalari: `bot/handlers/admin.py`
- Klient funksiyalari: `bot/handlers/user.py`
- Yangi jadval/ustun kerak bo'lsa: `sql/schema.sql` ga `CREATE TABLE IF NOT EXISTS` / `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` qo'shing va `bot/db.py` ga funksiya yozing.
