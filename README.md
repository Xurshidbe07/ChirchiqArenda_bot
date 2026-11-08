# ChirchiqArenda_bot

Chirchiqda ijara uchun Telegram bot (aiogram 3 + PostgreSQL).

## OLX integratsiyasi

- **🛒 OLXda** tugmasi — bosilganda Chirchiqdagi uzoq muddatli ijara e'lonlari sahifasi OLX'da ochiladi.
  Tugma `/start` (ro'yxatdan o'tgan foydalanuvchi), ro'yxatdan o'tish yakuni va `/olx` javobida chiqadi.
- **📢 OLX e'lonlari** menyu tugmasi yoki `/olx` — OLX'dan so'nggi 5 ta e'lonni olib ko'rsatadi.
  Agar OLX javob bermasa yoki so'rovni rad etsa, bot to'g'ridan-to'g'ri OLX havolasini beradi.

Scraper (`olx.py`) proksilarni `proxies.txt` dan o'qiydi (`ip:port:login:parol`),
so'rovlarni ular orasida navbat bilan taqsimlaydi va natijani `OLX_CACHE_TTL` soniya keshda saqlaydi.

## Ishga tushirish

```bash
pip install -r requirements.txt
cp .env.example .env        # BOT_TOKEN va DATABASE_URL ni to'ldiring
# proxies.txt faylini yarating (gitga qo'shilmaydi)
python bot.py
```

`.env` va `proxies.txt` maxfiy — ular `.gitignore` da.
