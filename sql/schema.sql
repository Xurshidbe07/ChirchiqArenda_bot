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
