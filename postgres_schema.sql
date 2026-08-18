CREATE TABLE IF NOT EXISTS auction_sales (
    sale_key TEXT PRIMARY KEY,
    sale_fingerprint TEXT,
    sold_at TEXT NOT NULL,
    sold_at_ms BIGINT,
    collected_first_at TEXT,
    collected_last_at TEXT,
    observation_count INTEGER NOT NULL DEFAULT 1,
    base_item_key TEXT,
    item_key TEXT NOT NULL,
    item_hash TEXT,
    item_id TEXT,
    display_name TEXT,
    quantity INTEGER,
    total_price DOUBLE PRECISION,
    price_each DOUBLE PRECISION,
    seller_name TEXT,
    seller_uuid TEXT,
    enchants_json TEXT,
    lore_json TEXT,
    contents_json TEXT,
    raw_json TEXT NOT NULL,
    inserted_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_sales_item_sold_at
    ON auction_sales(item_key, sold_at);

CREATE INDEX IF NOT EXISTS idx_sales_sold_at
    ON auction_sales(sold_at);

CREATE INDEX IF NOT EXISTS idx_sales_sold_at_ms
    ON auction_sales(sold_at_ms);

CREATE INDEX IF NOT EXISTS idx_sales_item_sold_at_ms
    ON auction_sales(item_key, sold_at_ms);

CREATE INDEX IF NOT EXISTS idx_sales_base_item_sold_at
    ON auction_sales(base_item_key, sold_at_ms);

CREATE TABLE IF NOT EXISTS auction_listing_snapshots (
    listing_key TEXT PRIMARY KEY,
    snapshot_at TEXT NOT NULL,
    page INTEGER NOT NULL,
    row_index INTEGER NOT NULL,
    base_item_key TEXT,
    item_key TEXT NOT NULL,
    item_hash TEXT,
    item_id TEXT,
    display_name TEXT,
    quantity INTEGER,
    total_price DOUBLE PRECISION,
    price_each DOUBLE PRECISION,
    seller_name TEXT,
    seller_uuid TEXT,
    time_left TEXT,
    enchants_json TEXT,
    lore_json TEXT,
    contents_json TEXT,
    raw_json TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_listing_snapshot_item
    ON auction_listing_snapshots(snapshot_at, item_key);

CREATE INDEX IF NOT EXISTS idx_listing_page_snapshot
    ON auction_listing_snapshots(page, snapshot_at);

CREATE INDEX IF NOT EXISTS idx_listing_snapshot_at
    ON auction_listing_snapshots(snapshot_at);

CREATE TABLE IF NOT EXISTS market_stats (
    item_key TEXT PRIMARY KEY,
    calculated_at TEXT NOT NULL,
    base_item_key TEXT,
    item_id TEXT,
    display_name TEXT,
    sold_median_1h DOUBLE PRECISION,
    sold_median_24h DOUBLE PRECISION,
    sold_median_7d DOUBLE PRECISION,
    units_sold_24h BIGINT,
    sales_count_24h BIGINT,
    volume_24h DOUBLE PRECISION,
    lowest_listing DOUBLE PRECISION,
    median_listing DOUBLE PRECISION,
    listing_count BIGINT,
    listed_quantity BIGINT,
    market_value DOUBLE PRECISION,
    liquidity_score DOUBLE PRECISION
);

CREATE TABLE IF NOT EXISTS item_candles_1m (
    item_key TEXT NOT NULL,
    minute_ms BIGINT NOT NULL,
    base_item_key TEXT,
    item_id TEXT,
    display_name TEXT,
    open DOUBLE PRECISION,
    high DOUBLE PRECISION,
    low DOUBLE PRECISION,
    close DOUBLE PRECISION,
    median DOUBLE PRECISION,
    vwap DOUBLE PRECISION,
    units BIGINT,
    transactions BIGINT,
    volume DOUBLE PRECISION,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (item_key, minute_ms)
);

CREATE INDEX IF NOT EXISTS idx_candles_1m_base_time
    ON item_candles_1m(base_item_key, minute_ms);

CREATE TABLE IF NOT EXISTS collector_state (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS users (
    id BIGSERIAL PRIMARY KEY,
    account_name TEXT,
    minecraft_name TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS user_identities (
    provider TEXT NOT NULL,
    provider_user_id TEXT NOT NULL,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    email TEXT,
    display_name TEXT,
    avatar_url TEXT,
    raw_json TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (provider, provider_user_id)
);

CREATE INDEX IF NOT EXISTS idx_user_identities_user
    ON user_identities(user_id);

CREATE TABLE IF NOT EXISTS user_sessions (
    session_id TEXT PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at BIGINT NOT NULL,
    expires_at BIGINT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_user_sessions_user
    ON user_sessions(user_id);

CREATE TABLE IF NOT EXISTS oauth_states (
    state TEXT PRIMARY KEY,
    provider TEXT NOT NULL,
    created_at BIGINT NOT NULL,
    expires_at BIGINT NOT NULL,
    next_path TEXT
);
