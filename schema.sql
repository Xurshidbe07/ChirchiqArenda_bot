CREATE TABLE IF NOT EXISTS users (
    id            BIGSERIAL PRIMARY KEY,
    telegram_id   BIGINT UNIQUE NOT NULL,
    username      TEXT,
    full_name     TEXT NOT NULL,
    phone         TEXT NOT NULL,
    role          TEXT NOT NULL CHECK (role IN ('tenant', 'landlord', 'both')),
    region        TEXT NOT NULL,
    district      TEXT NOT NULL,
    lang          TEXT NOT NULL DEFAULT 'uz',
    is_active     BOOLEAN NOT NULL DEFAULT TRUE,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_users_region ON users(region);
