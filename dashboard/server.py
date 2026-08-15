#!/usr/bin/env python3
import argparse
import json
import sqlite3
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse


ROOT = Path(__file__).resolve().parent
STATIC_ROOT = ROOT / "static"
CACHE = {}


def cached(key, ttl_seconds, factory):
    now = time.monotonic()
    hit = CACHE.get(key)
    if hit and hit["expires_at"] > now:
        return hit["payload"]
    payload = factory()
    CACHE[key] = {
        "expires_at": now + ttl_seconds,
        "payload": payload,
    }
    return payload


def connect(db_path):
    uri = f"file:{db_path}?mode=ro"
    conn = sqlite3.connect(uri, uri=True, timeout=5)
    conn.row_factory = sqlite3.Row
    return conn


def rows(conn, sql, params=()):
    return [dict(row) for row in conn.execute(sql, params).fetchall()]


def one(conn, sql, params=()):
    row = conn.execute(sql, params).fetchone()
    return dict(row) if row else None


def clamp_limit(value, default=25, maximum=100):
    try:
        return max(1, min(maximum, int(value)))
    except (TypeError, ValueError):
        return default


def movement_expr():
    return """
        CASE
            WHEN sold_median_7d IS NOT NULL AND sold_median_7d > 0 AND sold_median_24h IS NOT NULL
            THEN ROUND((sold_median_24h - sold_median_7d) * 100.0 / sold_median_7d, 2)
            ELSE NULL
        END
    """


def variant_note(item_id):
    heterogeneous = {
        "minecraft:enchanted_book": "Many enchantment variants",
        "minecraft:filled_map": "Map variants are mixed",
        "minecraft:potion": "Potion variants are mixed",
        "minecraft:splash_potion": "Potion variants are mixed",
        "minecraft:lingering_potion": "Potion variants are mixed",
        "minecraft:tipped_arrow": "Arrow variants are mixed",
        "minecraft:player_head": "Custom heads are mixed",
        "minecraft:written_book": "Book variants are mixed",
    }
    if item_id and item_id.endswith("shulker_box"):
        return "Contents may vary"
    return heterogeneous.get(item_id)


def decorate_items(items):
    for item in items:
        item["variant_note"] = variant_note(item.get("item_id"))
    return items


def summary(conn):
    now_ms = int(time.time() * 1000)
    day_ms = 24 * 60 * 60 * 1000
    last_24h = one(
        conn,
        """
        SELECT
            COUNT(*) AS transactions,
            COALESCE(SUM(quantity), 0) AS units,
            COALESCE(SUM(total_price), 0) AS volume
        FROM auction_sales
        WHERE sold_at_ms >= ?
        """,
        (now_ms - day_ms,),
    )
    previous_24h = one(
        conn,
        """
        SELECT
            COUNT(*) AS transactions,
            COALESCE(SUM(quantity), 0) AS units,
            COALESCE(SUM(total_price), 0) AS volume
        FROM auction_sales
        WHERE sold_at_ms >= ?
          AND sold_at_ms < ?
        """,
        (now_ms - 2 * day_ms, now_ms - day_ms),
    )
    prev_volume = previous_24h["volume"] or 0
    volume_change = None
    if prev_volume > 0:
        volume_change = round((last_24h["volume"] - prev_volume) * 100.0 / prev_volume, 2)

    tx_per_minute = round((last_24h["transactions"] or 0) / (24 * 60), 2)
    if tx_per_minute >= 100:
        activity = "Extreme"
    elif tx_per_minute >= 25:
        activity = "High"
    elif tx_per_minute >= 5:
        activity = "Active"
    else:
        activity = "Quiet"

    return {
        "last_24h": {
            "transactions": last_24h["transactions"],
            "units": last_24h["units"],
            "volume": last_24h["volume"],
            "volume_change_pct": volume_change,
            "tx_per_minute": tx_per_minute,
            "activity": activity,
        },
        "sales": one(conn, "SELECT COUNT(*) AS value FROM auction_sales")["value"],
        "listings": one(conn, "SELECT COUNT(*) AS value FROM auction_listing_snapshots")["value"],
        "items": one(conn, "SELECT COUNT(*) AS value FROM market_stats")["value"],
        "candles": one(conn, "SELECT COUNT(*) AS value FROM item_candles_1m")["value"],
        "latest_sale": one(conn, "SELECT MAX(sold_at_ms) AS value FROM auction_sales")["value"],
        "latest_listing_page": one(conn, "SELECT value FROM collector_state WHERE key = 'next_listing_page'"),
    }


def top_markets(conn, params):
    limit = clamp_limit(params.get("limit", ["25"])[0])
    sort = params.get("sort", ["sales"])[0]
    order_map = {
        "sales": "sales_count_24h DESC, units_sold_24h DESC",
        "units": "units_sold_24h DESC, sales_count_24h DESC",
        "volume": "volume_24h DESC, sales_count_24h DESC",
        "liquidity": "liquidity_score DESC, sales_count_24h DESC",
        "gainers": "change_pct DESC, sales_count_24h DESC",
        "losers": "change_pct ASC, sales_count_24h DESC",
    }
    order_by = order_map.get(sort, order_map["sales"])
    result = rows(
        conn,
        f"""
        SELECT *
        FROM (
        SELECT
            item_key,
            COALESCE(base_item_key, item_id) AS base_item_key,
            item_id,
            display_name,
            sold_median_1h,
            sold_median_24h,
            sold_median_7d,
            units_sold_24h,
            sales_count_24h,
            volume_24h,
            lowest_listing,
            median_listing,
            listing_count,
            listed_quantity,
            market_value,
            liquidity_score,
            {movement_expr()} AS change_pct
        FROM market_stats
        WHERE sales_count_24h > 0
        )
        ORDER BY {order_by}
        LIMIT ?
        """,
        (limit,),
    )
    return decorate_items(result)


def movers(conn, params):
    limit = clamp_limit(params.get("limit", ["20"])[0])
    direction = params.get("direction", ["gainers"])[0]
    order = "change_pct DESC" if direction == "gainers" else "change_pct ASC"
    result = rows(
        conn,
        f"""
        SELECT *
        FROM (
            SELECT
                item_key,
                COALESCE(base_item_key, item_id) AS base_item_key,
                item_id,
                display_name,
                sold_median_24h,
                sold_median_7d,
                sales_count_24h,
                volume_24h,
                ROUND((sold_median_24h - sold_median_7d) * 100.0 / sold_median_7d, 2) AS change_pct
            FROM market_stats
            WHERE sold_median_24h IS NOT NULL
              AND sold_median_7d IS NOT NULL
              AND sold_median_7d > 0
              AND sales_count_24h >= 5
        )
        ORDER BY {order}
        LIMIT ?
        """,
        (limit,),
    )
    return decorate_items(result)


def opportunities(conn, params):
    limit = clamp_limit(params.get("limit", ["25"])[0])
    min_sales = clamp_limit(params.get("min_sales", ["5"])[0], default=5, maximum=1000)
    result = rows(
        conn,
        """
        SELECT *
        FROM (
            SELECT
                item_key,
                COALESCE(base_item_key, item_id) AS base_item_key,
                item_id,
                display_name,
                market_value,
                lowest_listing,
                median_listing,
                listing_count,
                listed_quantity,
                sales_count_24h,
                units_sold_24h,
                volume_24h,
                liquidity_score,
                ROUND((market_value - lowest_listing) * 100.0 / market_value, 2) AS discount_pct
            FROM market_stats
            WHERE market_value IS NOT NULL
              AND lowest_listing IS NOT NULL
              AND market_value > 0
              AND lowest_listing < market_value
              AND sales_count_24h >= ?
        )
        ORDER BY discount_pct DESC, liquidity_score DESC
        LIMIT ?
        """,
        (min_sales, limit),
    )
    return decorate_items(result)


def search(conn, params):
    q = params.get("q", [""])[0].strip()
    limit = clamp_limit(params.get("limit", ["12"])[0], default=12, maximum=30)
    if not q:
        return []
    pattern = f"%{q.lower()}%"
    result = rows(
        conn,
        f"""
        SELECT
            item_key,
            COALESCE(base_item_key, item_id) AS base_item_key,
            item_id,
            display_name,
            sold_median_24h,
            sold_median_7d,
            lowest_listing,
            sales_count_24h,
            volume_24h,
            {movement_expr()} AS change_pct
        FROM market_stats
        WHERE lower(COALESCE(display_name, '')) LIKE ?
           OR lower(item_id) LIKE ?
        ORDER BY sales_count_24h DESC, volume_24h DESC
        LIMIT ?
        """,
        (pattern, pattern, limit),
    )
    return decorate_items(result)


def candles(conn, params):
    item_key = params.get("item_key", [""])[0]
    limit = clamp_limit(params.get("limit", ["240"])[0], default=240, maximum=2000)
    if not item_key:
        return []
    return rows(
        conn,
        """
        SELECT
            minute_ms,
            open,
            high,
            low,
            close,
            median,
            vwap,
            units,
            transactions,
            volume
        FROM item_candles_1m
        WHERE item_key = ?
        ORDER BY minute_ms DESC
        LIMIT ?
        """,
        (item_key, limit),
    )[::-1]


def item_detail(conn, params):
    item_key = params.get("item_key", [""])[0]
    if not item_key:
        return None
    stats = one(
        conn,
        """
        SELECT
            *,
            CASE
                WHEN sold_median_7d IS NOT NULL AND sold_median_7d > 0 AND sold_median_24h IS NOT NULL
                THEN ROUND((sold_median_24h - sold_median_7d) * 100.0 / sold_median_7d, 2)
                ELSE NULL
            END AS change_pct
        FROM market_stats
        WHERE item_key = ?
        """,
        (item_key,),
    )
    if not stats:
        return None
    stats["variant_note"] = variant_note(stats.get("item_id"))
    stats["candles"] = candles(conn, {"item_key": [item_key], "limit": [params.get("limit", ["240"])[0]]})
    return stats


class DashboardHandler(SimpleHTTPRequestHandler):
    db_path = None

    def translate_path(self, path):
        parsed = urlparse(path)
        if parsed.path == "/":
            return str(STATIC_ROOT / "index.html")
        return str(STATIC_ROOT / parsed.path.lstrip("/"))

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path.startswith("/api/"):
            self.handle_api(parsed)
            return
        super().do_GET()

    def end_headers(self):
        if not urlparse(self.path).path.startswith("/api/"):
            self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def handle_api(self, parsed):
        params = parse_qs(parsed.query)
        try:
            with connect(self.db_path) as conn:
                if parsed.path == "/api/summary":
                    payload = cached("summary", 10, lambda: summary(conn))
                elif parsed.path == "/api/markets":
                    key = f"markets:{parsed.query}"
                    payload = cached(key, 15, lambda: top_markets(conn, params))
                elif parsed.path == "/api/movers":
                    key = f"movers:{parsed.query}"
                    payload = cached(key, 15, lambda: movers(conn, params))
                elif parsed.path == "/api/opportunities":
                    key = f"opportunities:{parsed.query}"
                    payload = cached(key, 30, lambda: opportunities(conn, params))
                elif parsed.path == "/api/search":
                    key = f"search:{parsed.query}"
                    payload = cached(key, 10, lambda: search(conn, params))
                elif parsed.path == "/api/candles":
                    key = f"candles:{parsed.query}"
                    payload = cached(key, 30, lambda: candles(conn, params))
                elif parsed.path == "/api/item":
                    key = f"item:{parsed.query}"
                    payload = cached(key, 15, lambda: item_detail(conn, params))
                else:
                    self.send_json({"error": "not found"}, status=404)
                    return
            self.send_json(payload)
        except Exception as error:
            self.send_json({"error": str(error)}, status=500)

    def send_json(self, payload, status=200):
        data = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, fmt, *args):
        print(f"{time.strftime('%Y-%m-%dT%H:%M:%S')} {self.address_string()} {fmt % args}")


def main():
    parser = argparse.ArgumentParser(description="Donut Market public dashboard")
    parser.add_argument("--db", default="/root/donut-market/donut_market.sqlite")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8095)
    args = parser.parse_args()

    DashboardHandler.db_path = args.db
    server = ThreadingHTTPServer((args.host, args.port), DashboardHandler)
    print(f"dashboard listening on http://{args.host}:{args.port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
