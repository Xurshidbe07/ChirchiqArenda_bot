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

### Market Mini App (klientlar uchun, `/start` → «🏠 Uylar bozorini ochish»)
OLX/Joymee uslubidagi ijara uylar bozori. Chat pastidagi «🏠 Uylar» menyu tugmasi ham shuni ochadi.

- **Ro'yxatdan o'tish** (birinchi ochishda): ism, telefon (Telegram orqali ulashish yoki qo'lda), rol
  (ijarachi / uy egasi). Ro'yxatdan o'tmagan klient e'lonlarni ko'rmaydi.
- **Lenta**: 2 ustunli kartalar (rasm, narx, xona, mavze, manba belgisi), qidiruv, xona bo'yicha chiplar,
  filtr (narx so'mda, mavze, manba), saralash (yangi / arzon / qimmat / ommabop), sahifalash.
- **Tafsilot**: rasm galereyasi (surish), narx (y.e bo'lsa so'mga taxminiy kurs), parametrlar
  (xona, maydon, qavat), tavsif, sotuvchi, «📞 Qo'ng'iroq», «Joymee'da ochish».
- **Sevimlilar** va **Profil** (ma'lumotlarni o'zgartirish).

Fayllar: `bot/webapp/static/market.html` (interfeys), `bot/webapp/server.py` (`/api/market/*`).

### E'lonlar manbasi: Joymee scraper
E'lonlar **Joymee.uz** dan avtomatik tortiladi (`bot/scrapers/joymee.py`) — saytning ochiq JSON API'si
orqali (`api.joymee.uz/api/v1/announcement/?deal_type=2&district=166`), robots.txt ruxsat bergan.

- Bot ishga tushganda va keyin har `SYNC_INTERVAL_MIN` daqiqada (`bot/sync.py`); admin paneldagi
  «🔄 Joymee'dan yangilash» tugmasi bilan qo'lda ham.
- Yangi e'lon → qo'shiladi; narxi/nomi o'zgargan → yangilanadi; Joymee'dan yo'qolgan → yashiriladi.
- Admin yashirgan tashqi e'lon (`admin_hidden`) sinxda qayta ochilmaydi. Tashqi e'lonni o'chirish = yashirish.
- `JOYMEE_DISTRICTS` — tumanlar (166 Chirchiq shahar; 150/156/147 — Yuqori/O'rta/Quyichirchiq),
  `JOYMEE_CATEGORIES` — turkumlar (4 Kvartira, 5 Uy/dacha, 6 Tijorat, 7 Yer), `USD_RATE` — y.e kursi.

> **OLX haqida.** OLX.uz barcha dastur so'rovlarini (hatto `robots.txt` ni ham) CloudFront bot-himoyasi
> bilan bloklaydi, faqat brauzerdan ochiladi. Bot-himoyani aylanib o'tish qilinmaydi, shuning uchun OLX
> e'lonlari avtomatik tortilmaydi. Variantlar: OLX'ning rasmiy hamkorlik API'si yoki admin panel orqali qo'lda qo'shish.

### Matnli zaxira
Mini App ishlamasa (`WEBAPP_URL` yo'q), «🏠 Uylar» tugmasi e'lonlarni chatda varaqlab beradi.

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

## Serverga joylash (Render.com)

Repo'da tayyor [render.yaml](render.yaml) bor: Web Service (bot + Mini App) va Postgres.

1. Render dashboard → **New → Blueprint** → GitHub'dan `ChirchiqArenda_bot` repo'ni tanlang.
2. So'ralganda `BOT_TOKEN` va `ADMIN_IDS` ni kiriting. `DATABASE_URL` bazadan, `WEBAPP_URL` esa
   Render'ning `RENDER_EXTERNAL_URL` muhit o'zgaruvchisidan avtomatik olinadi (cloudflared kerak emas).
3. Deploy tugagach Telegramda `/start` → Mini App Render manzilida ochiladi.

**Bepul tarif eslatmalari**
- Bepul Web Service 15 daqiqa so'rovsiz qolsa uxlaydi. Bot o'zi har `KEEPALIVE_MIN` (10) daqiqada
  `/health` ga so'rov yuborib uyg'oq turadi (`bot/keepalive.py`). Qo'shimcha kafolat uchun
  [UptimeRobot](https://uptimerobot.com) da `https://<nomi>.onrender.com/health` ni 5 daqiqalik monitor qiling.
- Bepul Render Postgres 30 kundan keyin o'chadi. Uzoq muddat uchun [Neon](https://neon.tech) yoki
  [Supabase](https://supabase.com) bepul bazasini olib, `DATABASE_URL` ni shunga almashtiring.

Boshqa hostinglar (Railway, Fly.io, VPS) uchun: `PORT` berilsa bot `0.0.0.0:$PORT` da tinglaydi,
`WEBAPP_URL` ga ochiq HTTPS manzilni yozing.

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
│   ├── sync.py          # davriy sinxronlash (fon vazifasi)
│   ├── keepalive.py     # bepul hostingda uxlamaslik uchun o'ziga ping
│   ├── scrapers/
│   │   └── joymee.py    # Joymee.uz API dan e'lonlarni tortish
│   ├── webapp/
│   │   ├── server.py    # Mini App API (aiohttp): admin + market
│   │   └── static/
│   │       ├── index.html   # admin Mini App
│   │       └── market.html  # klient Mini App (uylar bozori)
│   └── handlers/
│       ├── admin.py     # /admin (Mini App), /menu (tugmali), admin handlerlar
│       └── user.py      # klient qismi
├── sql/schema.sql       # jadvallar
├── requirements.txt
├── .env.example
└── README.md
```

## Ma'lumotlar bazasi

- `users` — klientlar: `telegram_id`, `full_name`, `username`, `phone`, `role`, `registered_at`, `is_blocked`, `block_reason`
- `houses` — e'lonlar: `title`, `address`, `district`, `rooms`, `area`, `floor`, `price`, `currency`, `price_uzs`,
  `description`, `photo_urls` (tashqi URL yoki `tg:FILE_ID`), `contact_phone`, `source` (admin/joymee),
  `source_id`, `source_url`, `seller_*`, `views`, `is_active`, `admin_hidden`, `last_seen_at`
- `favorites` — klient sevimlilari
- `sync_log` — sinxronlash jurnali

## Jamoa uchun

- Admin funksiyalari: `bot/handlers/admin.py`
- Klient funksiyalari: `bot/handlers/user.py`
- Yangi jadval/ustun kerak bo'lsa: `sql/schema.sql` ga `CREATE TABLE IF NOT EXISTS` / `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` qo'shing va `bot/db.py` ga funksiya yozing.
