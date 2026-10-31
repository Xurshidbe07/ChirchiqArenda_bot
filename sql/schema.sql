-- ChirchiqArendabot ma'lumotlar bazasi sxemasi
-- Bot ishga tushganda avtomatik bajariladi (bot/db.py -> init_db)

CREATE TABLE IF NOT EXISTS users (
    id           BIGSERIAL PRIMARY KEY,
    telegram_id  BIGINT      NOT NULL UNIQUE,
    full_name    TEXT        NOT NULL DEFAULT '',
    username     TEXT,
    phone        TEXT,
    is_blocked   BOOLEAN     NOT NULL DEFAULT FALSE,
    block_reason TEXT,
    blocked_at   TIMESTAMPTZ,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS houses (
    id            SERIAL PRIMARY KEY,
    title         TEXT          NOT NULL,
    address       TEXT          NOT NULL,
    rooms         SMALLINT      NOT NULL CHECK (rooms > 0),
    price         NUMERIC(14,2) NOT NULL CHECK (price >= 0),
    description   TEXT          NOT NULL DEFAULT '',
    photo_file_id TEXT,
    contact_phone TEXT,
    is_active     BOOLEAN       NOT NULL DEFAULT TRUE,
    created_by    BIGINT,
    created_at    TIMESTAMPTZ   NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_houses_active ON houses(is_active, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_users_blocked ON users(is_blocked);

-- ===================== Market: tashqi manbalar (Joymee) + klient qismi =====================

-- Klient ro'yxatdan o'tishi
ALTER TABLE users ADD COLUMN IF NOT EXISTS role          TEXT;          -- 'tenant' | 'landlord'
ALTER TABLE users ADD COLUMN IF NOT EXISTS registered_at TIMESTAMPTZ;   -- NULL = hali ro'yxatdan o'tmagan

-- E'lon manbasi va qo'shimcha maydonlar
ALTER TABLE houses ALTER COLUMN rooms DROP NOT NULL;                   -- tashqi e'londa xona soni bo'lmasligi mumkin
ALTER TABLE houses ADD COLUMN IF NOT EXISTS source        TEXT NOT NULL DEFAULT 'admin';  -- admin | joymee
ALTER TABLE houses ADD COLUMN IF NOT EXISTS source_id     TEXT;
ALTER TABLE houses ADD COLUMN IF NOT EXISTS source_url    TEXT;
ALTER TABLE houses ADD COLUMN IF NOT EXISTS currency      TEXT NOT NULL DEFAULT 'UZS';    -- UZS | USD
ALTER TABLE houses ADD COLUMN IF NOT EXISTS price_uzs     NUMERIC(16,2);                  -- filtr/saralash uchun so'mda
ALTER TABLE houses ADD COLUMN IF NOT EXISTS district      TEXT;
ALTER TABLE houses ADD COLUMN IF NOT EXISTS area          NUMERIC(8,1);
ALTER TABLE houses ADD COLUMN IF NOT EXISTS floor         SMALLINT;
ALTER TABLE houses ADD COLUMN IF NOT EXISTS floors        SMALLINT;
ALTER TABLE houses ADD COLUMN IF NOT EXISTS photo_urls    TEXT[] NOT NULL DEFAULT '{}';   -- tashqi rasm manzillari
ALTER TABLE houses ADD COLUMN IF NOT EXISTS seller_name   TEXT;
ALTER TABLE houses ADD COLUMN IF NOT EXISTS seller_username TEXT;
ALTER TABLE houses ADD COLUMN IF NOT EXISTS lat           DOUBLE PRECISION;
ALTER TABLE houses ADD COLUMN IF NOT EXISTS lon           DOUBLE PRECISION;
ALTER TABLE houses ADD COLUMN IF NOT EXISTS external_created_at TIMESTAMPTZ;
ALTER TABLE houses ADD COLUMN IF NOT EXISTS last_seen_at  TIMESTAMPTZ;
ALTER TABLE houses ADD COLUMN IF NOT EXISTS admin_hidden  BOOLEAN NOT NULL DEFAULT FALSE; -- admin yashirgan: sinx qayta yoqmaydi
ALTER TABLE houses ADD COLUMN IF NOT EXISTS views         INTEGER NOT NULL DEFAULT 0;
ALTER TABLE houses ADD COLUMN IF NOT EXISTS updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW();

UPDATE houses SET price_uzs = price WHERE price_uzs IS NULL AND currency = 'UZS';

CREATE UNIQUE INDEX IF NOT EXISTS ux_houses_source ON houses(source, source_id) WHERE source_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_houses_market ON houses(is_active, price_uzs, created_at DESC);

-- Sevimlilar
CREATE TABLE IF NOT EXISTS favorites (
    user_id    BIGINT  NOT NULL,
    house_id   INTEGER NOT NULL REFERENCES houses(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (user_id, house_id)
);

-- ===================== Tillar, klient e'lonlari (moderatsiya), adminlar =====================

ALTER TABLE users ADD COLUMN IF NOT EXISTS lang TEXT;                -- uz | ru | en (NULL = hali tanlamagan)

ALTER TABLE houses ADD COLUMN IF NOT EXISTS status        TEXT NOT NULL DEFAULT 'approved'; -- pending|approved|rejected
ALTER TABLE houses ADD COLUMN IF NOT EXISTS owner_id      BIGINT;    -- e'lonni bergan klient (admin/tashqi bo'lsa NULL)
ALTER TABLE houses ADD COLUMN IF NOT EXISTS reject_reason TEXT;
ALTER TABLE houses ADD COLUMN IF NOT EXISTS moderated_by  BIGINT;
ALTER TABLE houses ADD COLUMN IF NOT EXISTS moderated_at  TIMESTAMPTZ;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'houses_status_check') THEN
        ALTER TABLE houses ADD CONSTRAINT houses_status_check
            CHECK (status IN ('pending', 'approved', 'rejected'));
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_houses_status ON houses(status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_houses_owner  ON houses(owner_id);

-- Adminlar (superadminlar ADMIN_IDS da; bu jadvalni superadmin paneldan boshqaradi)
CREATE TABLE IF NOT EXISTS admins (
    telegram_id BIGINT PRIMARY KEY,
    added_by    BIGINT,
    note        TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Sinxronlash jurnali
CREATE TABLE IF NOT EXISTS sync_log (
    id          SERIAL PRIMARY KEY,
    source      TEXT NOT NULL,
    started_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at TIMESTAMPTZ,
    added       INTEGER NOT NULL DEFAULT 0,
    updated     INTEGER NOT NULL DEFAULT 0,
    deactivated INTEGER NOT NULL DEFAULT 0,
    seen        INTEGER NOT NULL DEFAULT 0,
    error       TEXT
);
