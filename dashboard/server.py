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


def max_stack_size(item_id):
    if not item_id:
        return 64
    stack_16 = {
        "minecraft:egg",
        "minecraft:ender_pearl",
        "minecraft:snowball",
        "minecraft:honey_bottle",
        "minecraft:armor_stand",
        "minecraft:sign",
        "minecraft:oak_sign",
        "minecraft:spruce_sign",
        "minecraft:birch_sign",
        "minecraft:jungle_sign",
        "minecraft:acacia_sign",
        "minecraft:dark_oak_sign",
        "minecraft:mangrove_sign",
        "minecraft:cherry_sign",
        "minecraft:bamboo_sign",
        "minecraft:crimson_sign",
        "minecraft:warped_sign",
    }
    stack_1_suffixes = (
        "_helmet",
        "_chestplate",
        "_leggings",
        "_boots",
        "_sword",
        "_pickaxe",
        "_axe",
        "_shovel",
        "_hoe",
    )
    stack_1 = {
        "minecraft:bow",
        "minecraft:crossbow",
        "minecraft:trident",
        "minecraft:shield",
        "minecraft:elytra",
        "minecraft:fishing_rod",
        "minecraft:shears",
        "minecraft:flint_and_steel",
        "minecraft:brush",
        "minecraft:cake",
        "minecraft:mushroom_stew",
        "minecraft:rabbit_stew",
        "minecraft:beetroot_soup",
        "minecraft:suspicious_stew",
        "minecraft:carrot_on_a_stick",
        "minecraft:warped_fungus_on_a_stick",
        "minecraft:bucket",
        "minecraft:water_bucket",
        "minecraft:lava_bucket",
        "minecraft:milk_bucket",
        "minecraft:powder_snow_bucket",
        "minecraft:minecart",
        "minecraft:chest_minecart",
        "minecraft:furnace_minecart",
        "minecraft:hopper_minecart",
        "minecraft:tnt_minecart",
        "minecraft:boat",
        "minecraft:oak_boat",
        "minecraft:spruce_boat",
        "minecraft:birch_boat",
        "minecraft:jungle_boat",
        "minecraft:acacia_boat",
        "minecraft:dark_oak_boat",
        "minecraft:mangrove_boat",
        "minecraft:cherry_boat",
        "minecraft:bamboo_raft",
        "minecraft:potion",
        "minecraft:splash_potion",
        "minecraft:lingering_potion",
    }
    if item_id in stack_16:
        return 16
    if item_id in stack_1 or item_id.endswith(stack_1_suffixes):
        return 1
    return 64


def item_uses(item_id):
    uses = {
        "minecraft:egg": {
            "summary": "Ingredient for food crafts and throwable item.",
            "crafting": [
                {
                    "result": {"item_id": "minecraft:cake", "name": "Cake", "quantity": 1},
                    "ingredients": [
                        {"item_id": "minecraft:milk_bucket", "name": "Milk Bucket", "quantity": 3},
                        {"item_id": "minecraft:sugar", "name": "Sugar", "quantity": 2},
                        {"item_id": "minecraft:egg", "name": "Egg", "quantity": 1},
                        {"item_id": "minecraft:wheat", "name": "Wheat", "quantity": 3},
                    ],
                },
                {
                    "result": {"item_id": "minecraft:pumpkin_pie", "name": "Pumpkin Pie", "quantity": 1},
                    "ingredients": [
                        {"item_id": "minecraft:pumpkin", "name": "Pumpkin", "quantity": 1},
                        {"item_id": "minecraft:sugar", "name": "Sugar", "quantity": 1},
                        {"item_id": "minecraft:egg", "name": "Egg", "quantity": 1},
                    ],
                },
            ],
        },
        "minecraft:sugar": {
            "summary": "Common cooking and potion ingredient.",
            "crafting": [
                {
                    "result": {"item_id": "minecraft:cake", "name": "Cake", "quantity": 1},
                    "ingredients": [
                        {"item_id": "minecraft:milk_bucket", "name": "Milk Bucket", "quantity": 3},
                        {"item_id": "minecraft:sugar", "name": "Sugar", "quantity": 2},
                        {"item_id": "minecraft:egg", "name": "Egg", "quantity": 1},
                        {"item_id": "minecraft:wheat", "name": "Wheat", "quantity": 3},
                    ],
                },
                {
                    "result": {"item_id": "minecraft:pumpkin_pie", "name": "Pumpkin Pie", "quantity": 1},
                    "ingredients": [
                        {"item_id": "minecraft:pumpkin", "name": "Pumpkin", "quantity": 1},
                        {"item_id": "minecraft:sugar", "name": "Sugar", "quantity": 1},
                        {"item_id": "minecraft:egg", "name": "Egg", "quantity": 1},
                    ],
                },
            ],
        },
        "minecraft:wheat": {
            "summary": "Core farming commodity used in food and animal breeding.",
            "crafting": [
                {
                    "result": {"item_id": "minecraft:bread", "name": "Bread", "quantity": 1},
                    "ingredients": [
                        {"item_id": "minecraft:wheat", "name": "Wheat", "quantity": 3},
                    ],
                },
                {
                    "result": {"item_id": "minecraft:cake", "name": "Cake", "quantity": 1},
                    "ingredients": [
                        {"item_id": "minecraft:milk_bucket", "name": "Milk Bucket", "quantity": 3},
                        {"item_id": "minecraft:sugar", "name": "Sugar", "quantity": 2},
                        {"item_id": "minecraft:egg", "name": "Egg", "quantity": 1},
                        {"item_id": "minecraft:wheat", "name": "Wheat", "quantity": 3},
                    ],
                },
            ],
        },
        "minecraft:pumpkin": {
            "summary": "Ingredient and utility block.",
            "crafting": [
                {
                    "result": {"item_id": "minecraft:pumpkin_pie", "name": "Pumpkin Pie", "quantity": 1},
                    "ingredients": [
                        {"item_id": "minecraft:pumpkin", "name": "Pumpkin", "quantity": 1},
                        {"item_id": "minecraft:sugar", "name": "Sugar", "quantity": 1},
                        {"item_id": "minecraft:egg", "name": "Egg", "quantity": 1},
                    ],
                },
                {
                    "result": {"item_id": "minecraft:jack_o_lantern", "name": "Jack o'Lantern", "quantity": 1},
                    "ingredients": [
                        {"item_id": "minecraft:carved_pumpkin", "name": "Carved Pumpkin", "quantity": 1},
                        {"item_id": "minecraft:torch", "name": "Torch", "quantity": 1},
                    ],
                },
            ],
        },
        "minecraft:milk_bucket": {
            "summary": "Consumable utility item and cake ingredient.",
            "crafting": [
                {
                    "result": {"item_id": "minecraft:cake", "name": "Cake", "quantity": 1},
                    "ingredients": [
                        {"item_id": "minecraft:milk_bucket", "name": "Milk Bucket", "quantity": 3},
                        {"item_id": "minecraft:sugar", "name": "Sugar", "quantity": 2},
                        {"item_id": "minecraft:egg", "name": "Egg", "quantity": 1},
                        {"item_id": "minecraft:wheat", "name": "Wheat", "quantity": 3},
                    ],
                },
            ],
        },
    }
    return uses.get(item_id, {"summary": "", "crafting": []})


def decorate_items(items):
    for item in items:
        item["variant_note"] = variant_note(item.get("item_id"))
    return items


def market_prices(conn, item_ids):
    if not item_ids:
        return {}
    placeholders = ",".join("?" for _ in item_ids)
    candidates = rows(
        conn,
        f"""
        SELECT
            item_id,
            item_key,
            display_name,
            sold_median_24h,
            market_value,
            lowest_listing,
            sales_count_24h,
            volume_24h
        FROM market_stats
        WHERE item_id IN ({placeholders})
        ORDER BY item_id, sales_count_24h DESC, volume_24h DESC
        """,
        tuple(item_ids),
    )
    prices = {}
    for row in candidates:
        item_id = row["item_id"]
        if item_id in prices:
            continue
        price_each = row.get("market_value") or row.get("sold_median_24h") or row.get("lowest_listing")
        prices[item_id] = {
            "item_key": row.get("item_key"),
            "display_name": row.get("display_name"),
            "price_each": price_each,
            "market_value": row.get("market_value"),
            "sold_median_24h": row.get("sold_median_24h"),
            "lowest_listing": row.get("lowest_listing"),
            "sales_count_24h": row.get("sales_count_24h"),
            "volume_24h": row.get("volume_24h"),
            "max_stack": max_stack_size(item_id),
        }
    return prices


def enrich_recipe_economics(conn, uses):
    recipes = uses.get("crafting", [])
    item_ids = set()
    for recipe in recipes:
        result = recipe.get("result", {})
        if result.get("item_id"):
            item_ids.add(result["item_id"])
        for ingredient in recipe.get("ingredients", []):
            if ingredient.get("item_id"):
                item_ids.add(ingredient["item_id"])

    prices = market_prices(conn, sorted(item_ids))
    enriched = []
    for recipe in recipes:
        result = dict(recipe.get("result", {}))
        result_price = prices.get(result.get("item_id"), {})
        result_quantity = result.get("quantity") or 1
        result["price_each"] = result_price.get("price_each")
        result["total_value"] = (
            result["price_each"] * result_quantity if result["price_each"] is not None else None
        )
        result["item_key"] = result_price.get("item_key")
        result["max_stack"] = result_price.get("max_stack", max_stack_size(result.get("item_id")))

        ingredients = []
        known_cost = 0
        missing_prices = []
        for ingredient in recipe.get("ingredients", []):
            enriched_ingredient = dict(ingredient)
            price = prices.get(ingredient.get("item_id"), {})
            quantity = ingredient.get("quantity") or 1
            enriched_ingredient["price_each"] = price.get("price_each")
            enriched_ingredient["total_cost"] = (
                enriched_ingredient["price_each"] * quantity
                if enriched_ingredient["price_each"] is not None
                else None
            )
            enriched_ingredient["item_key"] = price.get("item_key")
            enriched_ingredient["max_stack"] = price.get("max_stack", max_stack_size(ingredient.get("item_id")))
            if enriched_ingredient["total_cost"] is None:
                missing_prices.append(enriched_ingredient.get("name") or enriched_ingredient.get("item_id"))
            else:
                known_cost += enriched_ingredient["total_cost"]
            ingredients.append(enriched_ingredient)

        profit = None
        profit_pct = None
        if result["total_value"] is not None and not missing_prices:
            profit = result["total_value"] - known_cost
            if known_cost > 0:
                profit_pct = round(profit * 100.0 / known_cost, 2)

        enriched.append(
            {
                "result": result,
                "ingredients": ingredients,
                "ingredient_cost": known_cost if not missing_prices else None,
                "result_value": result["total_value"],
                "profit": profit,
                "profit_pct": profit_pct,
                "profitable": profit is not None and profit > 0,
                "missing_prices": missing_prices,
            }
        )

    uses["crafting"] = enriched
    return uses


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
    normalized = q.lower()
    pattern = f"%{normalized}%"
    prefix = f"{normalized}%"
    word_pattern = f"% {normalized}%"
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
        ORDER BY
            CASE
                WHEN lower(COALESCE(display_name, '')) = ? THEN 0
                WHEN lower(replace(item_id, 'minecraft:', '')) = ? THEN 1
                WHEN lower(COALESCE(display_name, '')) LIKE ? THEN 2
                WHEN lower(replace(item_id, 'minecraft:', '')) LIKE ? THEN 3
                WHEN lower(COALESCE(display_name, '')) LIKE ? THEN 4
                ELSE 5
            END,
            sales_count_24h DESC,
            volume_24h DESC
        LIMIT ?
        """,
        (pattern, pattern, normalized, normalized, prefix, prefix, word_pattern, limit),
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
    stats["max_stack"] = max_stack_size(stats.get("item_id"))
    price_each = stats.get("market_value") or stats.get("sold_median_24h") or stats.get("lowest_listing")
    stats["price_each"] = price_each
    stats["price_stack"] = price_each * stats["max_stack"] if price_each is not None else None
    stats["uses"] = enrich_recipe_economics(conn, item_uses(stats.get("item_id")))
    stats["candles"] = candles(conn, {"item_key": [item_key], "limit": [params.get("limit", ["240"])[0]]})
    return stats


class DashboardHandler(SimpleHTTPRequestHandler):
    db_path = None

    def translate_path(self, path):
        parsed = urlparse(path)
        if parsed.path == "/" or parsed.path.startswith("/item/"):
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
