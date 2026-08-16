#!/usr/bin/env python3
import argparse
import hashlib
import json
import os
import sqlite3
import statistics
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone


API_BASE = "https://api.donutsmp.net"
USER_AGENT = "donut-market-collector/0.1"


def utc_now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def millis_to_iso(value):
    if value is None:
        return None
    return datetime.fromtimestamp(int(value) / 1000, tz=timezone.utc).isoformat(timespec="seconds")


def item_key(item):
    if not item:
        return "unknown"
    item_id = item.get("id") or "unknown"
    display_name = item.get("display_name") or ""
    enchants = item.get("enchants") or {}
    lore = item.get("lore") or []
    contents = item.get("contents") or []
    payload = json.dumps(
        {
            "id": item_id,
            "display_name": display_name,
            "enchants": enchants,
            "lore": lore,
            "contents": contents,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    digest = hashlib.sha1(payload.encode("utf-8")).hexdigest()[:12]
    return f"{item_id}:{digest}"


def base_item_key(item):
    if not item:
        return "unknown"
    return item.get("id") or "unknown"


def readable_item_name(item):
    display_name = (item.get("display_name") or "").strip()
    if display_name:
        return display_name
    item_id = item.get("id") or "unknown"
    name = item_id.split(":", 1)[-1]
    return name.replace("_", " ").title()


def readable_name_from_id(item_id):
    if not item_id:
        return "Unknown"
    return item_id.split(":", 1)[-1].replace("_", " ").title()


def item_hash(item):
    payload = json.dumps(item or {}, sort_keys=True, separators=(",", ":"))
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()


def sale_fingerprint(sale):
    item = sale.get("item") or {}
    seller = sale.get("seller") or {}
    payload = json.dumps(
        {
            "sold": sale.get("unixMillisDateSold"),
            "price": sale.get("price"),
            "seller_uuid": seller.get("uuid"),
            "seller_name": seller.get("name"),
            "item": item,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()


def listing_key(snapshot_at, page, index, listing):
    item = listing.get("item") or {}
    seller = listing.get("seller") or {}
    payload = json.dumps(
        {
            "snapshot_at": snapshot_at,
            "page": page,
            "index": index,
            "price": listing.get("price"),
            "seller_uuid": seller.get("uuid"),
            "seller_name": seller.get("name"),
            "time_left": listing.get("time_left"),
            "item": item,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()


def price_each(price, count):
    if price is None:
        return None
    count = int(count or 1)
    if count <= 0:
        count = 1
    return float(price) / count


def fetch_json(path, api_key, timeout=20):
    req = urllib.request.Request(
        f"{API_BASE}{path}",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {error.code} for {path}: {body}") from error


def connect(db_path):
    conn = sqlite3.connect(db_path, timeout=60)
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 60000")
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.execute("PRAGMA wal_autocheckpoint = 1000")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS auction_sales (
            sale_key TEXT PRIMARY KEY,
            sale_fingerprint TEXT,
            sold_at TEXT NOT NULL,
            sold_at_ms INTEGER,
            collected_first_at TEXT,
            collected_last_at TEXT,
            observation_count INTEGER NOT NULL DEFAULT 1,
            base_item_key TEXT,
            item_key TEXT NOT NULL,
            item_hash TEXT,
            item_id TEXT,
            display_name TEXT,
            quantity INTEGER,
            total_price REAL,
            price_each REAL,
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

        CREATE INDEX IF NOT EXISTS idx_sales_item_sold_at_ms
            ON auction_sales(item_key, sold_at_ms);

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
            total_price REAL,
            price_each REAL,
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

        CREATE TABLE IF NOT EXISTS market_stats (
            item_key TEXT PRIMARY KEY,
            calculated_at TEXT NOT NULL,
            base_item_key TEXT,
            item_id TEXT,
            display_name TEXT,
            sold_median_1h REAL,
            sold_median_24h REAL,
            sold_median_7d REAL,
            units_sold_24h INTEGER,
            sales_count_24h INTEGER,
            volume_24h REAL,
            lowest_listing REAL,
            median_listing REAL,
            listing_count INTEGER,
            listed_quantity INTEGER,
            market_value REAL,
            liquidity_score REAL
        );

        CREATE TABLE IF NOT EXISTS item_candles_1m (
            item_key TEXT NOT NULL,
            minute_ms INTEGER NOT NULL,
            base_item_key TEXT,
            item_id TEXT,
            display_name TEXT,
            open REAL,
            high REAL,
            low REAL,
            close REAL,
            median REAL,
            vwap REAL,
            units INTEGER,
            transactions INTEGER,
            volume REAL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (item_key, minute_ms)
        );

        CREATE INDEX IF NOT EXISTS idx_candles_1m_base_time
            ON item_candles_1m(base_item_key, minute_ms);

        CREATE TABLE IF NOT EXISTS collector_state (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        """
    )
    ensure_columns(conn)
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_sales_base_item_sold_at
            ON auction_sales(base_item_key, sold_at_ms)
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_candles_1m_base_time
            ON item_candles_1m(base_item_key, minute_ms)
        """
    )
    conn.commit()
    return conn


def ensure_columns(conn):
    desired = {
        "auction_sales": {
            "sale_fingerprint": "TEXT",
            "collected_first_at": "TEXT",
            "collected_last_at": "TEXT",
            "observation_count": "INTEGER NOT NULL DEFAULT 1",
            "base_item_key": "TEXT",
            "item_hash": "TEXT",
        },
        "auction_listing_snapshots": {
            "base_item_key": "TEXT",
            "item_hash": "TEXT",
        },
        "market_stats": {
            "base_item_key": "TEXT",
        },
    }
    for table, columns in desired.items():
        existing = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
        for column, definition in columns.items():
            if column not in existing:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
    conn.commit()


def normalize_sale(sale):
    item = sale.get("item") or {}
    seller = sale.get("seller") or {}
    quantity = int(item.get("count") or 1)
    total_price = sale.get("price")
    fingerprint = sale_fingerprint(sale)
    collected_at = utc_now_iso()
    return {
        "sale_key": fingerprint,
        "sale_fingerprint": fingerprint,
        "sold_at": millis_to_iso(sale.get("unixMillisDateSold")) or utc_now_iso(),
        "sold_at_ms": sale.get("unixMillisDateSold"),
        "collected_first_at": collected_at,
        "collected_last_at": collected_at,
        "observation_count": 1,
        "base_item_key": base_item_key(item),
        "item_key": item_key(item),
        "item_hash": item_hash(item),
        "item_id": item.get("id"),
        "display_name": readable_item_name(item),
        "quantity": quantity,
        "total_price": total_price,
        "price_each": price_each(total_price, quantity),
        "seller_name": seller.get("name"),
        "seller_uuid": seller.get("uuid"),
        "enchants_json": json.dumps(item.get("enchants"), sort_keys=True),
        "lore_json": json.dumps(item.get("lore"), sort_keys=True),
        "contents_json": json.dumps(item.get("contents"), sort_keys=True),
        "raw_json": json.dumps(sale, sort_keys=True),
        "inserted_at": utc_now_iso(),
    }


def normalize_listing(snapshot_at, page, index, listing):
    item = listing.get("item") or {}
    seller = listing.get("seller") or {}
    quantity = int(item.get("count") or 1)
    total_price = listing.get("price")
    return {
        "listing_key": listing_key(snapshot_at, page, index, listing),
        "snapshot_at": snapshot_at,
        "page": page,
        "row_index": index,
        "base_item_key": base_item_key(item),
        "item_key": item_key(item),
        "item_hash": item_hash(item),
        "item_id": item.get("id"),
        "display_name": readable_item_name(item),
        "quantity": quantity,
        "total_price": total_price,
        "price_each": price_each(total_price, quantity),
        "seller_name": seller.get("name"),
        "seller_uuid": seller.get("uuid"),
        "time_left": listing.get("time_left"),
        "enchants_json": json.dumps(item.get("enchants"), sort_keys=True),
        "lore_json": json.dumps(item.get("lore"), sort_keys=True),
        "contents_json": json.dumps(item.get("contents"), sort_keys=True),
        "raw_json": json.dumps(listing, sort_keys=True),
    }


def insert_rows(conn, table, rows):
    if not rows:
        return 0
    columns = list(rows[0].keys())
    placeholders = ",".join("?" for _ in columns)
    sql = f"INSERT OR IGNORE INTO {table} ({','.join(columns)}) VALUES ({placeholders})"
    before = conn.total_changes
    conn.executemany(sql, [[row[column] for column in columns] for row in rows])
    conn.commit()
    return conn.total_changes - before


def upsert_sales(conn, rows):
    if not rows:
        return 0
    columns = list(rows[0].keys())
    placeholders = ",".join("?" for _ in columns)
    sql = f"""
        INSERT INTO auction_sales ({','.join(columns)})
        VALUES ({placeholders})
        ON CONFLICT(sale_key) DO UPDATE SET
            collected_last_at = excluded.collected_last_at,
            observation_count = auction_sales.observation_count + 1
    """
    before = conn.total_changes
    conn.executemany(sql, [[row[column] for column in columns] for row in rows])
    conn.commit()
    changed = conn.total_changes - before
    return sum(1 for row in rows if conn.execute("SELECT observation_count FROM auction_sales WHERE sale_key = ?", (row["sale_key"],)).fetchone()[0] == 1)


def collect_transactions(conn, api_key, pages):
    total_seen = 0
    before_count = conn.execute("SELECT COUNT(*) FROM auction_sales").fetchone()[0]
    for page in range(1, pages + 1):
        data = fetch_json(f"/v1/auction/transactions/{page}", api_key)
        result = data.get("result") or []
        total_seen += len(result)
        upsert_sales(conn, [normalize_sale(row) for row in result])
        if len(result) == 0:
            break
        time.sleep(0.05)
    after_count = conn.execute("SELECT COUNT(*) FROM auction_sales").fetchone()[0]
    return total_seen, after_count - before_count


def collect_listings(conn, api_key, pages, start_page=1):
    snapshot_at = utc_now_iso()
    total_seen = 0
    total_inserted = 0
    last_page = start_page - 1
    next_page = start_page
    for offset in range(pages):
        page = start_page + offset
        try:
            data = fetch_json(f"/v1/auction/list/{page}", api_key)
        except RuntimeError as error:
            if "HTTP 500" in str(error):
                next_page = 1
                break
            raise
        result = data.get("result") or []
        total_seen += len(result)
        last_page = page
        rows = [normalize_listing(snapshot_at, page, index, row) for index, row in enumerate(result)]
        total_inserted += insert_rows(conn, "auction_listing_snapshots", rows)
        if len(result) == 0:
            next_page = 1
            break
        next_page = page + 1
        time.sleep(0.05)
    return total_seen, total_inserted, last_page, next_page


def get_state(conn, key, default):
    row = conn.execute("SELECT value FROM collector_state WHERE key = ?", (key,)).fetchone()
    return row[0] if row else default


def set_state(conn, key, value):
    conn.execute(
        """
        INSERT INTO collector_state(key, value)
        VALUES(?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """,
        (key, str(value)),
    )
    conn.commit()


def refresh_recent_candles(conn, lookback_minutes=180):
    cutoff_ms = int(time.time() * 1000) - lookback_minutes * 60 * 1000
    rows = conn.execute(
        """
        SELECT
            item_key,
            (sold_at_ms / 60000) * 60000 AS minute_ms,
            base_item_key,
            item_id,
            display_name,
            price_each,
            quantity,
            total_price,
            sold_at_ms
        FROM auction_sales
        WHERE sold_at_ms >= ?
          AND price_each IS NOT NULL
        ORDER BY item_key, minute_ms, sold_at_ms
        """,
        (cutoff_ms,),
    ).fetchall()

    grouped = {}
    for row in rows:
        key = (row[0], row[1])
        grouped.setdefault(key, []).append(row)

    now = utc_now_iso()
    for (variant_key, minute_ms), candle_rows in grouped.items():
        prices = [row[5] for row in candle_rows]
        units = sum(int(row[6] or 0) for row in candle_rows)
        volume = sum(float(row[7] or 0) for row in candle_rows)
        vwap = volume / units if units else None
        first = candle_rows[0]
        last = candle_rows[-1]
        conn.execute(
            """
            INSERT INTO item_candles_1m (
                item_key, minute_ms, base_item_key, item_id, display_name,
                open, high, low, close, median, vwap, units, transactions, volume, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(item_key, minute_ms) DO UPDATE SET
                open = excluded.open,
                high = excluded.high,
                low = excluded.low,
                close = excluded.close,
                median = excluded.median,
                vwap = excluded.vwap,
                units = excluded.units,
                transactions = excluded.transactions,
                volume = excluded.volume,
                updated_at = excluded.updated_at
            """,
            (
                variant_key,
                minute_ms,
                first[2],
                first[3],
                first[4],
                first[5],
                max(prices),
                min(prices),
                last[5],
                median_or_none(prices),
                vwap,
                units,
                len(candle_rows),
                volume,
                now,
            ),
        )
    conn.commit()


def median_or_none(values):
    values = [value for value in values if value is not None]
    if not values:
        return None
    return float(statistics.median(values))


def recalc_market_stats(conn):
    now = utc_now_iso()
    now_ms = int(time.time() * 1000)
    one_hour_ms = now_ms - 60 * 60 * 1000
    one_day_ms = now_ms - 24 * 60 * 60 * 1000
    seven_days_ms = now_ms - 7 * 24 * 60 * 60 * 1000

    def price_medians(cutoff_ms):
        grouped = {}
        for item_key, price_each in conn.execute(
            """
            SELECT item_key, price_each
            FROM auction_sales
            WHERE sold_at_ms >= ?
              AND price_each IS NOT NULL
            ORDER BY item_key
            """,
            (cutoff_ms,),
        ):
            grouped.setdefault(item_key, []).append(price_each)
        return {item_key: median_or_none(prices) for item_key, prices in grouped.items()}

    conn.execute("DELETE FROM market_stats")
    item_keys = {
        row[0]
        for row in conn.execute(
            """
            SELECT item_key FROM auction_sales
            UNION
            SELECT item_key FROM auction_listing_snapshots
            """
        )
    }

    metadata_by_item = {}
    for row in conn.execute(
        """
        SELECT item_key, base_item_key, item_id, display_name, MAX(sold_at_ms) AS last_seen
        FROM auction_sales
        GROUP BY item_key
        """
    ):
        metadata_by_item[row[0]] = {
            "base_item_key": row[1],
            "item_id": row[2],
            "display_name": row[3],
            "last_seen": row[4] or 0,
        }
    for row in conn.execute(
        """
        SELECT item_key, base_item_key, item_id, display_name, MAX(snapshot_at) AS last_seen
        FROM auction_listing_snapshots
        GROUP BY item_key
        """
    ):
        existing = metadata_by_item.get(row[0])
        if not existing or (row[4] or "") > str(existing.get("last_seen") or ""):
            metadata_by_item[row[0]] = {
                "base_item_key": row[1],
                "item_id": row[2],
                "display_name": row[3],
                "last_seen": row[4],
            }

    sold_median_1h = price_medians(one_hour_ms)
    sold_median_24h = price_medians(one_day_ms)
    sold_median_7d = price_medians(seven_days_ms)
    sales_24h_by_item = {
        row[0]: (row[1] or 0, row[2] or 0, row[3] or 0)
        for row in conn.execute(
            """
            SELECT
                item_key,
                COALESCE(SUM(quantity), 0) AS units,
                COUNT(*) AS sales,
                COALESCE(SUM(total_price), 0) AS volume
            FROM auction_sales
            WHERE sold_at_ms >= ?
            GROUP BY item_key
            """,
            (one_day_ms,),
        )
    }

    listing_rows_by_item = {}
    for row in conn.execute(
        """
        WITH latest_page_scans AS (
            SELECT page, MAX(snapshot_at) AS snapshot_at
            FROM auction_listing_snapshots
            GROUP BY page
        )
        SELECT listings.item_key, listings.price_each, listings.quantity
        FROM auction_listing_snapshots listings
        JOIN latest_page_scans latest
          ON latest.page = listings.page
         AND latest.snapshot_at = listings.snapshot_at
        """
    ):
        listing_rows_by_item.setdefault(row[0], []).append((row[1], row[2]))

    for key in item_keys:
        item_meta = metadata_by_item.get(key, {})
        base_key = item_meta.get("base_item_key")
        item_id = item_meta.get("item_id")
        display_name = item_meta.get("display_name")
        if not display_name:
            display_name = readable_name_from_id(item_id)

        listing_rows = listing_rows_by_item.get(key, [])
        listing_prices = [row[0] for row in listing_rows]
        listed_quantity = sum(int(row[1] or 0) for row in listing_rows)

        median_1h = sold_median_1h.get(key)
        median_24h = sold_median_24h.get(key)
        median_7d = sold_median_7d.get(key)
        sales_24h = sales_24h_by_item.get(key, (0, 0, 0))
        median_listing = median_or_none(listing_prices)
        lowest_listing = min(listing_prices) if listing_prices else None
        market_value = next(
            value for value in [median_24h, median_7d, median_listing, lowest_listing] if value is not None
        ) if any(value is not None for value in [median_24h, median_7d, median_listing, lowest_listing]) else None
        liquidity_score = min(100.0, float(sales_24h[1]) * 2.0)

        conn.execute(
            """
            INSERT INTO market_stats (
                item_key, calculated_at, base_item_key, item_id, display_name,
                sold_median_1h, sold_median_24h, sold_median_7d,
                units_sold_24h, sales_count_24h, volume_24h,
                lowest_listing, median_listing, listing_count, listed_quantity,
                market_value, liquidity_score
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                key,
                now,
                base_key,
                item_id,
                display_name,
                median_1h,
                median_24h,
                median_7d,
                int(sales_24h[0]),
                int(sales_24h[1]),
                float(sales_24h[2]),
                lowest_listing,
                median_listing,
                len(listing_rows),
                listed_quantity,
                market_value,
                liquidity_score,
            ),
        )
    conn.commit()


def print_opportunities(conn, limit, min_sales_24h):
    rows = conn.execute(
        """
        SELECT
            display_name,
            item_id,
            market_value,
            lowest_listing,
            ROUND((market_value - lowest_listing) * 100.0 / market_value, 2) AS discount_pct,
            sales_count_24h,
            units_sold_24h,
            listing_count,
            liquidity_score
        FROM market_stats
        WHERE market_value IS NOT NULL
          AND lowest_listing IS NOT NULL
          AND market_value > 0
          AND lowest_listing < market_value
          AND sales_count_24h >= ?
        ORDER BY discount_pct DESC, liquidity_score DESC
        LIMIT ?
        """,
        (min_sales_24h, limit),
    ).fetchall()
    print("display_name | item_id | market | lowest | discount% | sales24h | units24h | listings | liq")
    for row in rows:
        print(" | ".join("" if value is None else str(value) for value in row))


def run_once(args):
    api_key = os.environ.get("DONUT_API_KEY")
    if not api_key:
        raise SystemExit("Set DONUT_API_KEY in your environment.")
    conn = connect(args.db)
    tx_seen, tx_inserted = collect_transactions(conn, api_key, args.transaction_pages)
    listing_seen, listing_inserted, _, _ = collect_listings(conn, api_key, args.listing_pages)
    recalc_market_stats(conn)
    print(
        f"{utc_now_iso()} transactions seen={tx_seen} new={tx_inserted} "
        f"listings seen={listing_seen} new_snapshot_rows={listing_inserted}"
    )
    if args.show_opportunities:
        print_opportunities(conn, args.show_opportunities, args.min_sales_24h)


def run_service(args):
    api_key = os.environ.get("DONUT_API_KEY")
    if not api_key:
        raise SystemExit("Set DONUT_API_KEY in your environment.")
    conn = connect(args.db)
    print(
        f"{utc_now_iso()} service starting "
        f"tx_pages={args.transaction_pages} tx_interval={args.tx_interval}s "
        f"listing_pages_per_cycle={args.listing_pages_per_cycle} "
        f"aggregate_interval={args.aggregate_interval}s"
    )
    next_aggregate_at = time.monotonic() + args.aggregate_interval
    while True:
        cycle_started = time.monotonic()
        next_listing_page = int(get_state(conn, "next_listing_page", "1"))
        try:
            tx_seen, tx_new = collect_transactions(conn, api_key, args.transaction_pages)
            listing_seen, listing_new, listing_last, next_listing_page = collect_listings(
                conn,
                api_key,
                args.listing_pages_per_cycle,
                start_page=next_listing_page,
            )
            set_state(conn, "next_listing_page", next_listing_page)
            aggregate_note = ""
            if time.monotonic() >= next_aggregate_at:
                aggregate_started = time.monotonic()
                refresh_recent_candles(conn, lookback_minutes=args.candle_lookback_minutes)
                recalc_market_stats(conn)
                next_aggregate_at = time.monotonic() + args.aggregate_interval
                aggregate_note = f" aggregate_sec={time.monotonic() - aggregate_started:.2f}"
            elapsed = time.monotonic() - cycle_started
            print(
                f"{utc_now_iso()} tx_seen={tx_seen} tx_new={tx_new} "
                f"listing_seen={listing_seen} listing_new={listing_new} "
                f"listing_pages={listing_last}->{next_listing_page} "
                f"cycle_sec={elapsed:.2f}{aggregate_note}"
            )
        except Exception as error:
            print(f"{utc_now_iso()} collector_error={error}")

        elapsed = time.monotonic() - cycle_started
        time.sleep(max(0.0, args.tx_interval - elapsed))


def main():
    parser = argparse.ArgumentParser(description="Collect DonutSMP auction data into SQLite.")
    parser.add_argument("--db", default="donut_market.sqlite", help="SQLite database path")
    parser.add_argument("--transaction-pages", type=int, default=10, help="Transaction pages to fetch, max 10")
    parser.add_argument("--listing-pages", type=int, default=20, help="Current listing pages to fetch")
    parser.add_argument("--interval", type=int, default=0, help="Repeat interval in seconds; 0 means run once")
    parser.add_argument("--service", action="store_true", help="Run transaction-first long-running ingestion service")
    parser.add_argument("--tx-interval", type=float, default=5.0, help="Seconds between transaction poll cycles in service mode")
    parser.add_argument("--listing-pages-per-cycle", type=int, default=8, help="Listing pages to scan after each transaction poll in service mode")
    parser.add_argument("--aggregate-interval", type=float, default=300.0, help="Seconds between candle/stat refreshes in service mode")
    parser.add_argument("--candle-lookback-minutes", type=int, default=180, help="Recent minutes to recalculate for 1m candles")
    parser.add_argument("--show-opportunities", type=int, default=10, help="Print top discount rows after collection")
    parser.add_argument("--min-sales-24h", type=int, default=3, help="Minimum 24h sales for opportunity output")
    args = parser.parse_args()

    args.transaction_pages = max(1, min(10, args.transaction_pages))
    args.listing_pages = max(1, args.listing_pages)
    args.listing_pages_per_cycle = max(0, args.listing_pages_per_cycle)
    args.aggregate_interval = max(30.0, args.aggregate_interval)
    args.candle_lookback_minutes = max(5, args.candle_lookback_minutes)

    if args.service:
        run_service(args)
        return

    while True:
        run_once(args)
        if args.interval <= 0:
            break
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
