"""Muhit o'zgaruvchilaridan (.env) konfiguratsiyani o'qish."""
import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Config:
    bot_token: str
    database_url: str
    admin_ids: frozenset[int] = field(default_factory=frozenset)
    # Mini App (Telegram Web App) sozlamalari
    webapp_url: str = ""          # tashqi HTTPS manzil; bo'sh bo'lsa cloudflared tunnel ochiladi
    webapp_host: str = "127.0.0.1"
    webapp_port: int = 8080
    # Market: tashqi manbalardan sinxronlash
    sync_interval_min: int = 30                 # 0 = avtomatik sinxronlash o'chiq
    # Hududlar: Toshkent shahri (butun) + atrofidagi tumanlar. Har manbadan hudud bo'yicha eng yangilari olinadi.
    joymee_regions: tuple[int, ...] = (59,)     # 59 = Toshkent shahri (barcha tumanlari)
    joymee_districts: tuple[int, ...] = (166, 145, 151, 148, 161, 157, 160, 159, 150, 156, 147, 154)
    #   166 Chirchiq, 145 Bo'stonliq, 151 Qibray, 148 Zangiota, 161 Toshkent t., 157 Nurafshon,
    #   160/159 Yangiyo'l sh./t., 150 Yuqorichirchiq, 156 O'rtachirchiq, 147 Quyichirchiq, 154 Parkent
    joymee_max_pages: int = 20                  # har hudud/ijara turi bo'yicha 20 x 50 = 1000 ta eng yangi
    joymee_max_new: int = 300                   # bir sinxronda ko'pi bilan nechta yangi tafsilot (sekin API)
    joymee_categories: tuple[int, ...] = (4, 5) # 4 = Kvartira, 5 = Uy/dacha
    joymee_deal_types: tuple[int, ...] = (2, 1) # 2 = oylik ijara, 1 = kunlik ijara
    usd_rate: int = 12500                       # 1 y.e necha so'm (filtr uchun)
    # Keep-alive: bepul hostingda (Render) server uxlab qolmasligi uchun o'ziga so'rov yuboradi
    keepalive_min: int = 10                     # 0 = o'chiq; Render 15 daqiqada uxlatadi, 10 yetarli
    # Klient e'lonlari moderatsiyasi: False = darhol bozorga chiqadi, True = admin tasdiqlashi kerak
    moderation: bool = False
    # Admin panel JWT: maxfiy kalit (bo'sh = bot tokenidan hosil qilinadi) va amal qilish muddati
    admin_jwt_secret: str = ""
    admin_token_hours: int = 12
    # Uybor (uybor.uz): region 13 = Toshkent shahri, 12 = Toshkent viloyati; bo'sh ikkalasi = o'chiq
    uybor_regions: tuple[int, ...] = (13, 12)
    uybor_cities: tuple[int, ...] = ()                      # ixtiyoriy aniq shaharlar (150 = Chirchiq)
    uybor_max_pages: int = 20                               # 20 x 50 = 1000 ta eng yangi (har region)
    uybor_categories: tuple[int, ...] = (7, 8, 9, 26, 27, 28)  # kvartira, uy, kottej, xona, dacha, xususiy uy
    # Qayoda (qayoda.uz, agregator): katalog yo'llari; bo'sh = o'chiq. Sekin (Crawl-delay 10s) — alohida jadval
    qayoda_cities: tuple[str, ...] = (
        "toshkent",
        *(f"toshkent-viloyati/{d}" for d in (
            "chirchiq", "qibray", "bostonliq", "zangiota", "toshkent", "nurafshon", "yangiyol",
            "yangiyol-tumani", "yuqorichirchiq", "ortachirchiq", "quyichirchiq", "parkent")),
    )
    qayoda_max_pages: int = 10                    # har yo'l/bo'lim bo'yicha (10 x 24 = 240 ta eng yangi)
    qayoda_interval_min: int = 60


def _parse_admin_ids(raw: str) -> frozenset[int]:
    ids: set[int] = set()
    for part in raw.split(","):
        part = part.strip()
        if part:
            ids.add(int(part))
    return frozenset(ids)


def _parse_int_list(raw: str, default: tuple[int, ...]) -> tuple[int, ...]:
    vals = tuple(int(p) for p in raw.split(",") if p.strip())
    return vals or default


def _opt_list(name: str, default: tuple[int, ...]) -> tuple[int, ...]:
    """O'zgaruvchi yo'q -> default; bo'sh qiymat (NAME=) -> () ya'ni o'chiq; aks holda ro'yxat."""
    raw = os.getenv(name)
    if raw is None:
        return default
    return tuple(int(p) for p in raw.split(",") if p.strip())


def load_config() -> Config:
    token = os.getenv("BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("BOT_TOKEN topilmadi. .env faylini .env.example asosida yarating.")

    db_url = os.getenv("DATABASE_URL", "").strip()
    if not db_url:
        raise RuntimeError("DATABASE_URL topilmadi. .env faylini tekshiring.")

    # Render kabi hostinglar PORT va RENDER_EXTERNAL_URL beradi — ularni avtomatik olamiz
    hosted_port = os.getenv("PORT", "").strip()
    default_host = "0.0.0.0" if hosted_port else "127.0.0.1"
    webapp_url = os.getenv("WEBAPP_URL", "").strip() or os.getenv("RENDER_EXTERNAL_URL", "").strip()

    return Config(
        bot_token=token,
        database_url=db_url,
        admin_ids=_parse_admin_ids(os.getenv("ADMIN_IDS", "")),
        webapp_url=webapp_url.rstrip("/"),
        webapp_host=os.getenv("WEBAPP_HOST", "").strip() or default_host,
        webapp_port=int(os.getenv("WEBAPP_PORT", "").strip() or hosted_port or 8080),
        keepalive_min=int(os.getenv("KEEPALIVE_MIN", "10") or 0),
        moderation=os.getenv("MODERATION", "0").strip().lower() in ("1", "true", "yes", "on"),
        admin_jwt_secret=os.getenv("ADMIN_JWT_SECRET", "").strip(),
        admin_token_hours=int(os.getenv("ADMIN_TOKEN_HOURS", "12") or 12),
        uybor_regions=_opt_list("UYBOR_REGIONS", (13, 12)),
        uybor_cities=_opt_list("UYBOR_CITIES", ()),
        uybor_max_pages=int(os.getenv("UYBOR_MAX_PAGES", "20") or 20),
        uybor_categories=_parse_int_list(os.getenv("UYBOR_CATEGORIES", ""), (7, 8, 9, 26, 27, 28)),
        qayoda_cities=(tuple(p.strip().strip("/") for p in os.environ["QAYODA_CITIES"].split(",") if p.strip())
                       if "QAYODA_CITIES" in os.environ else Config.qayoda_cities),
        qayoda_max_pages=int(os.getenv("QAYODA_MAX_PAGES", "10") or 10),
        qayoda_interval_min=int(os.getenv("QAYODA_INTERVAL_MIN", "60") or 0),
        sync_interval_min=int(os.getenv("SYNC_INTERVAL_MIN", "30") or 0),
        joymee_regions=_opt_list("JOYMEE_REGIONS", (59,)),
        joymee_districts=_opt_list("JOYMEE_DISTRICTS", (166, 145, 151, 148, 161, 157, 160, 159, 150, 156, 147, 154)),
        joymee_max_pages=int(os.getenv("JOYMEE_MAX_PAGES", "20") or 20),
        joymee_max_new=int(os.getenv("JOYMEE_MAX_NEW", "300") or 300),
        joymee_categories=_parse_int_list(os.getenv("JOYMEE_CATEGORIES", ""), (4, 5)),
        joymee_deal_types=_parse_int_list(os.getenv("JOYMEE_DEAL_TYPES", ""), (2, 1)),
        usd_rate=int(os.getenv("USD_RATE", "12500") or 12500),
    )


config = load_config()
