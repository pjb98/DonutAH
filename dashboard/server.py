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


def summary(conn):
    return {
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
    }
    order_by = order_map.get(sort, order_map["sales"])
    return rows(
        conn,
        f"""
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
            liquidity_score
        FROM market_stats
        WHERE sales_count_24h > 0
        ORDER BY {order_by}
        LIMIT ?
        """,
        (limit,),
    )


def movers(conn, params):
    limit = clamp_limit(params.get("limit", ["20"])[0])
    direction = params.get("direction", ["gainers"])[0]
    order = "change_pct DESC" if direction == "gainers" else "change_pct ASC"
    return rows(
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


def opportunities(conn, params):
    limit = clamp_limit(params.get("limit", ["25"])[0])
    min_sales = clamp_limit(params.get("min_sales", ["5"])[0], default=5, maximum=1000)
    return rows(
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
        SELECT *
        FROM market_stats
        WHERE item_key = ?
        """,
        (item_key,),
    )
    if not stats:
        return None
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

    def handle_api(self, parsed):
        params = parse_qs(parsed.query)
        try:
            with connect(self.db_path) as conn:
                if parsed.path == "/api/summary":
                    payload = summary(conn)
                elif parsed.path == "/api/markets":
                    payload = top_markets(conn, params)
                elif parsed.path == "/api/movers":
                    payload = movers(conn, params)
                elif parsed.path == "/api/opportunities":
                    payload = opportunities(conn, params)
                elif parsed.path == "/api/candles":
                    payload = candles(conn, params)
                elif parsed.path == "/api/item":
                    payload = item_detail(conn, params)
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
