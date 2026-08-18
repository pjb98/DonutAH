#!/usr/bin/env python3
import argparse
import base64
import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse
import urllib.error
import urllib.parse
import urllib.request

import psycopg2
from psycopg2.extras import RealDictCursor


ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = ROOT.parent
STATIC_ROOT = ROOT / "static"
CACHE = {}
POSTGRES_SCHEMA_READY = False
SESSION_COOKIE = "donutdex_session"
SESSION_TTL_SECONDS = 60 * 60 * 24 * 30
OAUTH_STATE_TTL_SECONDS = 60 * 10
EXCLUDED_ITEM_IDS = {
    "minecraft:book",
    "minecraft:enchanted_book",
    "minecraft:map",
    "minecraft:filled_map",
    "minecraft:banner",
    "minecraft:writable_book",
    "minecraft:written_book",
    "minecraft:knowledge_book",
}

OAUTH_PROVIDERS = {
    "discord": {
        "label": "Discord",
        "client_id_env": "DISCORD_CLIENT_ID",
        "client_secret_env": "DISCORD_CLIENT_SECRET",
        "authorize_url": "https://discord.com/oauth2/authorize",
        "token_url": "https://discord.com/api/oauth2/token",
        "userinfo_url": "https://discord.com/api/users/@me",
        "scope": "identify email",
    },
    "google": {
        "label": "Google",
        "client_id_env": "GOOGLE_CLIENT_ID",
        "client_secret_env": "GOOGLE_CLIENT_SECRET",
        "authorize_url": "https://accounts.google.com/o/oauth2/v2/auth",
        "token_url": "https://oauth2.googleapis.com/token",
        "userinfo_url": "https://openidconnect.googleapis.com/v1/userinfo",
        "scope": "openid email profile",
    },
    "microsoft": {
        "label": "Microsoft",
        "client_id_env": "MICROSOFT_CLIENT_ID",
        "client_secret_env": "MICROSOFT_CLIENT_SECRET",
        "authorize_url": "https://login.microsoftonline.com/common/oauth2/v2.0/authorize",
        "token_url": "https://login.microsoftonline.com/common/oauth2/v2.0/token",
        "userinfo_url": "https://graph.microsoft.com/v1.0/me",
        "scope": "openid email profile User.Read",
    },
}

VILLAGER_TRADE_ITEMS = [
    {"profession": "Any Villager", "level": "Trade Reward", "item_id": "minecraft:emerald"},
    {"profession": "Armorer", "level": "Apprentice", "item_id": "minecraft:bell"},
    {"profession": "Armorer", "level": "Journeyman", "item_id": "minecraft:chainmail_leggings"},
    {"profession": "Armorer", "level": "Journeyman", "item_id": "minecraft:chainmail_boots"},
    {"profession": "Armorer", "level": "Expert", "item_id": "minecraft:chainmail_helmet"},
    {"profession": "Armorer", "level": "Expert", "item_id": "minecraft:chainmail_chestplate"},
    {"profession": "Armorer", "level": "Expert", "item_id": "minecraft:shield"},
    {"profession": "Armorer", "level": "Master", "item_id": "minecraft:diamond_leggings"},
    {"profession": "Armorer", "level": "Master", "item_id": "minecraft:diamond_boots"},
    {"profession": "Armorer", "level": "Master", "item_id": "minecraft:diamond_helmet"},
    {"profession": "Armorer", "level": "Master", "item_id": "minecraft:diamond_chestplate"},
    {"profession": "Butcher", "level": "Apprentice", "item_id": "minecraft:rabbit_stew"},
    {"profession": "Butcher", "level": "Journeyman", "item_id": "minecraft:cooked_porkchop"},
    {"profession": "Butcher", "level": "Expert", "item_id": "minecraft:cooked_chicken"},
    {"profession": "Cartographer", "level": "Novice", "item_id": "minecraft:map"},
    {"profession": "Cartographer", "level": "Apprentice", "item_id": "minecraft:ocean_explorer_map"},
    {"profession": "Cartographer", "level": "Apprentice", "item_id": "minecraft:woodland_explorer_map"},
    {"profession": "Cartographer", "level": "Journeyman", "item_id": "minecraft:item_frame"},
    {"profession": "Cartographer", "level": "Expert", "item_id": "minecraft:banner"},
    {"profession": "Cartographer", "level": "Master", "item_id": "minecraft:globe_banner_pattern"},
    {"profession": "Cleric", "level": "Novice", "item_id": "minecraft:redstone"},
    {"profession": "Cleric", "level": "Apprentice", "item_id": "minecraft:lapis_lazuli"},
    {"profession": "Cleric", "level": "Journeyman", "item_id": "minecraft:glowstone"},
    {"profession": "Cleric", "level": "Expert", "item_id": "minecraft:ender_pearl"},
    {"profession": "Cleric", "level": "Master", "item_id": "minecraft:experience_bottle"},
    {"profession": "Farmer", "level": "Novice", "item_id": "minecraft:bread"},
    {"profession": "Farmer", "level": "Apprentice", "item_id": "minecraft:pumpkin_pie"},
    {"profession": "Farmer", "level": "Journeyman", "item_id": "minecraft:apple"},
    {"profession": "Farmer", "level": "Expert", "item_id": "minecraft:cookie"},
    {"profession": "Farmer", "level": "Master", "item_id": "minecraft:cake"},
    {"profession": "Fisherman", "level": "Novice", "item_id": "minecraft:bucket"},
    {"profession": "Fisherman", "level": "Apprentice", "item_id": "minecraft:cooked_cod"},
    {"profession": "Fisherman", "level": "Journeyman", "item_id": "minecraft:campfire"},
    {"profession": "Fisherman", "level": "Expert", "item_id": "minecraft:fishing_rod"},
    {"profession": "Fletcher", "level": "Novice", "item_id": "minecraft:arrow"},
    {"profession": "Fletcher", "level": "Apprentice", "item_id": "minecraft:bow"},
    {"profession": "Fletcher", "level": "Journeyman", "item_id": "minecraft:crossbow"},
    {"profession": "Fletcher", "level": "Master", "item_id": "minecraft:tipped_arrow"},
    {"profession": "Leatherworker", "level": "Novice", "item_id": "minecraft:leather_leggings"},
    {"profession": "Leatherworker", "level": "Apprentice", "item_id": "minecraft:leather_chestplate"},
    {"profession": "Leatherworker", "level": "Journeyman", "item_id": "minecraft:leather_helmet"},
    {"profession": "Leatherworker", "level": "Journeyman", "item_id": "minecraft:leather_boots"},
    {"profession": "Leatherworker", "level": "Expert", "item_id": "minecraft:leather_horse_armor"},
    {"profession": "Leatherworker", "level": "Master", "item_id": "minecraft:saddle"},
    {"profession": "Librarian", "level": "Apprentice", "item_id": "minecraft:lantern"},
    {"profession": "Librarian", "level": "Journeyman", "item_id": "minecraft:glass"},
    {"profession": "Librarian", "level": "Expert", "item_id": "minecraft:clock"},
    {"profession": "Librarian", "level": "Expert", "item_id": "minecraft:compass"},
    {"profession": "Librarian", "level": "Master", "item_id": "minecraft:name_tag"},
    {"profession": "Mason", "level": "Novice", "item_id": "minecraft:brick"},
    {"profession": "Mason", "level": "Apprentice", "item_id": "minecraft:chiseled_stone_bricks"},
    {"profession": "Mason", "level": "Journeyman", "item_id": "minecraft:polished_andesite"},
    {"profession": "Mason", "level": "Journeyman", "item_id": "minecraft:polished_diorite"},
    {"profession": "Mason", "level": "Journeyman", "item_id": "minecraft:polished_granite"},
    {"profession": "Mason", "level": "Expert", "item_id": "minecraft:terracotta"},
    {"profession": "Mason", "level": "Expert", "item_id": "minecraft:white_glazed_terracotta"},
    {"profession": "Mason", "level": "Expert", "item_id": "minecraft:orange_glazed_terracotta"},
    {"profession": "Mason", "level": "Expert", "item_id": "minecraft:magenta_glazed_terracotta"},
    {"profession": "Mason", "level": "Expert", "item_id": "minecraft:light_blue_glazed_terracotta"},
    {"profession": "Mason", "level": "Expert", "item_id": "minecraft:yellow_glazed_terracotta"},
    {"profession": "Mason", "level": "Expert", "item_id": "minecraft:lime_glazed_terracotta"},
    {"profession": "Mason", "level": "Expert", "item_id": "minecraft:pink_glazed_terracotta"},
    {"profession": "Mason", "level": "Expert", "item_id": "minecraft:gray_glazed_terracotta"},
    {"profession": "Mason", "level": "Expert", "item_id": "minecraft:light_gray_glazed_terracotta"},
    {"profession": "Mason", "level": "Expert", "item_id": "minecraft:cyan_glazed_terracotta"},
    {"profession": "Mason", "level": "Expert", "item_id": "minecraft:purple_glazed_terracotta"},
    {"profession": "Mason", "level": "Expert", "item_id": "minecraft:blue_glazed_terracotta"},
    {"profession": "Mason", "level": "Expert", "item_id": "minecraft:brown_glazed_terracotta"},
    {"profession": "Mason", "level": "Expert", "item_id": "minecraft:green_glazed_terracotta"},
    {"profession": "Mason", "level": "Expert", "item_id": "minecraft:red_glazed_terracotta"},
    {"profession": "Mason", "level": "Expert", "item_id": "minecraft:black_glazed_terracotta"},
    {"profession": "Mason", "level": "Master", "item_id": "minecraft:quartz_block"},
    {"profession": "Shepherd", "level": "Apprentice", "item_id": "minecraft:shears"},
    {"profession": "Shepherd", "level": "Apprentice", "item_id": "minecraft:white_wool"},
    {"profession": "Shepherd", "level": "Apprentice", "item_id": "minecraft:orange_wool"},
    {"profession": "Shepherd", "level": "Apprentice", "item_id": "minecraft:magenta_wool"},
    {"profession": "Shepherd", "level": "Apprentice", "item_id": "minecraft:light_blue_wool"},
    {"profession": "Shepherd", "level": "Apprentice", "item_id": "minecraft:yellow_wool"},
    {"profession": "Shepherd", "level": "Apprentice", "item_id": "minecraft:lime_wool"},
    {"profession": "Shepherd", "level": "Apprentice", "item_id": "minecraft:pink_wool"},
    {"profession": "Shepherd", "level": "Apprentice", "item_id": "minecraft:gray_wool"},
    {"profession": "Shepherd", "level": "Apprentice", "item_id": "minecraft:light_gray_wool"},
    {"profession": "Shepherd", "level": "Apprentice", "item_id": "minecraft:cyan_wool"},
    {"profession": "Shepherd", "level": "Apprentice", "item_id": "minecraft:purple_wool"},
    {"profession": "Shepherd", "level": "Apprentice", "item_id": "minecraft:blue_wool"},
    {"profession": "Shepherd", "level": "Apprentice", "item_id": "minecraft:brown_wool"},
    {"profession": "Shepherd", "level": "Apprentice", "item_id": "minecraft:green_wool"},
    {"profession": "Shepherd", "level": "Apprentice", "item_id": "minecraft:red_wool"},
    {"profession": "Shepherd", "level": "Apprentice", "item_id": "minecraft:black_wool"},
    {"profession": "Shepherd", "level": "Expert", "item_id": "minecraft:painting"},
    {"profession": "Shepherd", "level": "Master", "item_id": "minecraft:white_banner"},
    {"profession": "Shepherd", "level": "Master", "item_id": "minecraft:orange_banner"},
    {"profession": "Shepherd", "level": "Master", "item_id": "minecraft:magenta_banner"},
    {"profession": "Shepherd", "level": "Master", "item_id": "minecraft:light_blue_banner"},
    {"profession": "Shepherd", "level": "Master", "item_id": "minecraft:yellow_banner"},
    {"profession": "Shepherd", "level": "Master", "item_id": "minecraft:lime_banner"},
    {"profession": "Shepherd", "level": "Master", "item_id": "minecraft:pink_banner"},
    {"profession": "Shepherd", "level": "Master", "item_id": "minecraft:gray_banner"},
    {"profession": "Shepherd", "level": "Master", "item_id": "minecraft:light_gray_banner"},
    {"profession": "Shepherd", "level": "Master", "item_id": "minecraft:cyan_banner"},
    {"profession": "Shepherd", "level": "Master", "item_id": "minecraft:purple_banner"},
    {"profession": "Shepherd", "level": "Master", "item_id": "minecraft:blue_banner"},
    {"profession": "Shepherd", "level": "Master", "item_id": "minecraft:brown_banner"},
    {"profession": "Shepherd", "level": "Master", "item_id": "minecraft:green_banner"},
    {"profession": "Shepherd", "level": "Master", "item_id": "minecraft:red_banner"},
    {"profession": "Shepherd", "level": "Master", "item_id": "minecraft:black_banner"},
    {"profession": "Toolsmith", "level": "Novice", "item_id": "minecraft:stone_axe"},
    {"profession": "Toolsmith", "level": "Apprentice", "item_id": "minecraft:stone_pickaxe"},
    {"profession": "Toolsmith", "level": "Journeyman", "item_id": "minecraft:iron_axe"},
    {"profession": "Toolsmith", "level": "Journeyman", "item_id": "minecraft:iron_shovel"},
    {"profession": "Toolsmith", "level": "Expert", "item_id": "minecraft:diamond_hoe"},
    {"profession": "Toolsmith", "level": "Master", "item_id": "minecraft:diamond_axe"},
    {"profession": "Toolsmith", "level": "Master", "item_id": "minecraft:diamond_pickaxe"},
    {"profession": "Weaponsmith", "level": "Novice", "item_id": "minecraft:iron_axe"},
    {"profession": "Weaponsmith", "level": "Apprentice", "item_id": "minecraft:iron_sword"},
    {"profession": "Weaponsmith", "level": "Expert", "item_id": "minecraft:bell"},
    {"profession": "Weaponsmith", "level": "Master", "item_id": "minecraft:diamond_axe"},
    {"profession": "Weaponsmith", "level": "Master", "item_id": "minecraft:diamond_sword"},
]


def is_excluded_item(item_id):
    if item_id in EXCLUDED_ITEM_IDS:
        return True
    if not item_id:
        return False
    return (
        item_id.endswith("_banner")
        or item_id.endswith("_banner_pattern")
        or item_id.endswith("_explorer_map")
        or item_id.endswith("_shulker_box")
    )


def readable_name_from_id(item_id):
    if not item_id:
        return "Unknown"
    return item_id.split(":", 1)[-1].replace("_", " ").title()


def excluded_sql(column="item_id"):
    placeholders = ",".join(f"'{item_id}'" for item_id in sorted(EXCLUDED_ITEM_IDS))
    return (
        f"({column} IS NULL OR ("
        f"{column} NOT IN ({placeholders}) "
        f"AND {column} NOT LIKE '%_banner' "
        f"AND {column} NOT LIKE '%_banner_pattern' "
        f"AND {column} NOT LIKE '%_explorer_map' "
        f"AND {column} NOT LIKE '%_shulker_box'"
        f"))"
    )


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


def now_iso():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def load_env_file(path):
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def qmark_to_psycopg(sql):
    return sql.replace("%", "%%").replace("?", "%s")


class PostgresDashboardConn:
    is_postgres = True

    def __init__(self, database_url):
        self.conn = psycopg2.connect(database_url, cursor_factory=RealDictCursor)

    def execute(self, sql, params=()):
        cursor = self.conn.cursor()
        cursor.execute(qmark_to_psycopg(sql), params)
        return cursor

    def executescript(self, sql):
        cursor = self.conn.cursor()
        cursor.execute(sql)
        return cursor

    def commit(self):
        self.conn.commit()

    def close(self):
        self.conn.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        if exc_type:
            self.conn.rollback()
        else:
            self.conn.commit()
        self.close()


def ensure_postgres_schema(conn):
    global POSTGRES_SCHEMA_READY
    if POSTGRES_SCHEMA_READY:
        return
    schema_path = PROJECT_ROOT / "postgres_schema.sql"
    conn.executescript(schema_path.read_text(encoding="utf-8"))
    conn.commit()
    POSTGRES_SCHEMA_READY = True


def postgres_database_url():
    return os.environ.get("DONUTDEX_DATABASE_URL")


def connect(db_path):
    database_url = postgres_database_url()
    if database_url:
        conn = PostgresDashboardConn(database_url)
        ensure_postgres_schema(conn)
        return conn
    uri = f"file:{db_path}?mode=ro"
    conn = sqlite3.connect(uri, uri=True, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 30000")
    return conn


def connect_write(db_path):
    database_url = postgres_database_url()
    if database_url:
        conn = PostgresDashboardConn(database_url)
        ensure_postgres_schema(conn)
        return conn
    conn = sqlite3.connect(db_path, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 30000")
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.execute("PRAGMA foreign_keys = ON")
    ensure_account_tables(conn)
    return conn


def ensure_account_tables(conn):
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_name TEXT,
            minecraft_name TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS user_identities (
            provider TEXT NOT NULL,
            provider_user_id TEXT NOT NULL,
            user_id INTEGER NOT NULL,
            email TEXT,
            display_name TEXT,
            avatar_url TEXT,
            raw_json TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (provider, provider_user_id),
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_user_identities_user
            ON user_identities(user_id);

        CREATE TABLE IF NOT EXISTS user_sessions (
            session_id TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            created_at INTEGER NOT NULL,
            expires_at INTEGER NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_user_sessions_user
            ON user_sessions(user_id);

        CREATE TABLE IF NOT EXISTS oauth_states (
            state TEXT PRIMARY KEY,
            provider TEXT NOT NULL,
            created_at INTEGER NOT NULL,
            expires_at INTEGER NOT NULL,
            next_path TEXT
        );
        """
    )
    conn.commit()


def rows(conn, sql, params=()):
    return [dict(row) for row in conn.execute(sql, params).fetchall()]


def one(conn, sql, params=()):
    row = conn.execute(sql, params).fetchone()
    return dict(row) if row else None


def public_base_url(handler):
    configured = os.environ.get("DONUTDEX_PUBLIC_BASE_URL")
    if configured:
        return configured.rstrip("/")
    host = handler.headers.get("X-Forwarded-Host") or handler.headers.get("Host") or "127.0.0.1:8095"
    proto = handler.headers.get("X-Forwarded-Proto") or "http"
    return f"{proto}://{host}".rstrip("/")


def auth_secret():
    secret = os.environ.get("DONUTDEX_AUTH_SECRET")
    if secret:
        return secret.encode("utf-8")
    fallback = ROOT.parent / ".donutdex_auth_secret"
    if not fallback.exists():
        fallback.write_text(secrets.token_urlsafe(48), encoding="utf-8")
        try:
            fallback.chmod(0o600)
        except OSError:
            pass
    return fallback.read_text(encoding="utf-8").strip().encode("utf-8")


def sign_value(value):
    digest = hmac.new(auth_secret(), value.encode("utf-8"), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def make_cookie_value(session_id):
    return f"{session_id}.{sign_value(session_id)}"


def parse_cookies(header):
    cookies = {}
    for part in (header or "").split(";"):
        if "=" not in part:
            continue
        key, value = part.strip().split("=", 1)
        cookies[key] = value
    return cookies


def valid_session_id(cookie_value):
    if not cookie_value or "." not in cookie_value:
        return None
    session_id, signature = cookie_value.rsplit(".", 1)
    if hmac.compare_digest(signature, sign_value(session_id)):
        return session_id
    return None


def json_request(handler):
    length = int(handler.headers.get("Content-Length") or 0)
    if length <= 0:
        return {}
    return json.loads(handler.rfile.read(length).decode("utf-8"))


def provider_config(provider):
    config = OAUTH_PROVIDERS.get(provider)
    if not config:
        return None
    client_id = os.environ.get(config["client_id_env"])
    client_secret = os.environ.get(config["client_secret_env"])
    return {**config, "client_id": client_id, "client_secret": client_secret, "configured": bool(client_id and client_secret)}


def oauth_redirect_uri(handler, provider):
    return f"{public_base_url(handler)}/auth/{provider}/callback"


def fetch_form_json(url, form_data, headers=None):
    body = urllib.parse.urlencode(form_data).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json", **(headers or {})},
    )
    with urllib.request.urlopen(req, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def fetch_bearer_json(url, token):
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def normalize_oauth_profile(provider, payload):
    if provider == "discord":
        avatar = payload.get("avatar")
        user_id = str(payload.get("id") or "")
        avatar_url = f"https://cdn.discordapp.com/avatars/{user_id}/{avatar}.png" if avatar and user_id else None
        return {
            "provider_user_id": user_id,
            "email": payload.get("email"),
            "display_name": payload.get("global_name") or payload.get("username") or "Discord User",
            "avatar_url": avatar_url,
        }
    if provider == "google":
        return {
            "provider_user_id": str(payload.get("sub") or ""),
            "email": payload.get("email"),
            "display_name": payload.get("name") or payload.get("email") or "Google User",
            "avatar_url": payload.get("picture"),
        }
    if provider == "microsoft":
        return {
            "provider_user_id": str(payload.get("id") or ""),
            "email": payload.get("mail") or payload.get("userPrincipalName"),
            "display_name": payload.get("displayName") or payload.get("userPrincipalName") or "Microsoft User",
            "avatar_url": None,
        }
    return {"provider_user_id": "", "email": None, "display_name": "User", "avatar_url": None}


def clamp_limit(value, default=25, maximum=100):
    try:
        return max(1, min(maximum, int(value)))
    except (TypeError, ValueError):
        return default


def timeframe_limit(value):
    limits = {
        "1h": 60,
        "6h": 360,
        "24h": 1440,
        "7d": 7 * 1440,
        "30d": 30 * 1440,
        "all": 2000,
    }
    return limits.get((value or "24h").lower(), limits["24h"])


def movement_expr():
    return """
        CASE
            WHEN sold_median_7d IS NOT NULL AND sold_median_7d > 0 AND sold_median_24h IS NOT NULL
            THEN (sold_median_24h - sold_median_7d) * 100.0 / sold_median_7d
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
        "minecraft:white_banner",
        "minecraft:orange_banner",
        "minecraft:magenta_banner",
        "minecraft:light_blue_banner",
        "minecraft:yellow_banner",
        "minecraft:lime_banner",
        "minecraft:pink_banner",
        "minecraft:gray_banner",
        "minecraft:light_gray_banner",
        "minecraft:cyan_banner",
        "minecraft:purple_banner",
        "minecraft:blue_banner",
        "minecraft:brown_banner",
        "minecraft:green_banner",
        "minecraft:red_banner",
        "minecraft:black_banner",
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
        "minecraft:saddle",
        "minecraft:leather_horse_armor",
        "minecraft:iron_horse_armor",
        "minecraft:golden_horse_armor",
        "minecraft:diamond_horse_armor",
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
        "minecraft:leather": {
            "summary": "Common crafting material used for item frames and leather armor.",
            "crafting": [
                {
                    "result": {"item_id": "minecraft:book", "name": "Book", "quantity": 1},
                    "ingredients": [
                        {"item_id": "minecraft:paper", "name": "Paper", "quantity": 3},
                        {"item_id": "minecraft:leather", "name": "Leather", "quantity": 1},
                    ],
                },
                {
                    "result": {"item_id": "minecraft:item_frame", "name": "Item Frame", "quantity": 1},
                    "ingredients": [
                        {"item_id": "minecraft:stick", "name": "Stick", "quantity": 8},
                        {"item_id": "minecraft:leather", "name": "Leather", "quantity": 1},
                    ],
                },
                {
                    "result": {"item_id": "minecraft:leather_helmet", "name": "Leather Helmet", "quantity": 1},
                    "ingredients": [
                        {"item_id": "minecraft:leather", "name": "Leather", "quantity": 5},
                    ],
                },
                {
                    "result": {"item_id": "minecraft:leather_chestplate", "name": "Leather Tunic", "quantity": 1},
                    "ingredients": [
                        {"item_id": "minecraft:leather", "name": "Leather", "quantity": 8},
                    ],
                },
                {
                    "result": {"item_id": "minecraft:leather_leggings", "name": "Leather Pants", "quantity": 1},
                    "ingredients": [
                        {"item_id": "minecraft:leather", "name": "Leather", "quantity": 7},
                    ],
                },
                {
                    "result": {"item_id": "minecraft:leather_boots", "name": "Leather Boots", "quantity": 1},
                    "ingredients": [
                        {"item_id": "minecraft:leather", "name": "Leather", "quantity": 4},
                    ],
                },
            ],
        },
    }
    return uses.get(item_id, {"summary": "", "crafting": []})


def decorate_items(items):
    items = [item for item in items if not is_excluded_item(item.get("item_id"))]
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
            listing_count,
            listed_quantity,
            sales_count_24h,
            volume_24h
        FROM market_stats
        WHERE item_id IN ({placeholders})
          AND {excluded_sql()}
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
            "listing_count": row.get("listing_count"),
            "listed_quantity": row.get("listed_quantity"),
            "sales_count_24h": row.get("sales_count_24h"),
            "volume_24h": row.get("volume_24h"),
            "max_stack": max_stack_size(item_id),
        }
    return prices


def enrich_recipe_economics(conn, uses):
    recipes = [
        recipe for recipe in uses.get("crafting", [])
        if not is_excluded_item((recipe.get("result") or {}).get("item_id"))
    ]
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
        result["sales_count_24h"] = result_price.get("sales_count_24h")
        result["volume_24h"] = result_price.get("volume_24h")

        ingredients = []
        known_cost = 0
        missing_prices = []
        if result["total_value"] is None:
            missing_prices.append(result.get("name") or result.get("item_id") or "Result")
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


def suggested_prices(stats):
    market = stats.get("market_value") or stats.get("sold_median_24h") or stats.get("lowest_listing")
    if market is None:
        return {"quick": None, "market": None, "max_profit": None}
    lowest = stats.get("lowest_listing")
    if lowest is not None and lowest > 0:
        market_list = min(max(market * 1.02, lowest * 0.99), market * 1.12)
    else:
        market_list = market * 1.03
    return {
        "quick": round(market * 0.95, 2),
        "market": round(market_list, 2),
        "max_profit": round(market * 1.12, 2),
    }


def recent_sales(conn, item_key, limit=12):
    return rows(
        conn,
        """
        SELECT sold_at_ms, quantity, price_each, total_price, seller_name
        FROM auction_sales
        WHERE item_key = ?
        ORDER BY sold_at_ms DESC
        LIMIT ?
        """,
        (item_key, limit),
    )


def current_listings(conn, item_key, limit=48):
    return rows(
        conn,
        """
        WITH latest_page_scans AS (
            SELECT page, MAX(snapshot_at) AS snapshot_at
            FROM auction_listing_snapshots
            GROUP BY page
        )
        SELECT
            listings.snapshot_at,
            listings.quantity,
            listings.price_each,
            listings.total_price,
            listings.seller_name,
            listings.time_left
        FROM auction_listing_snapshots listings
        JOIN latest_page_scans latest
          ON latest.page = listings.page
         AND latest.snapshot_at = listings.snapshot_at
        WHERE listings.item_key = ?
        ORDER BY listings.price_each ASC, listings.total_price ASC
        LIMIT ?
        """,
        (item_key, limit),
    )


def current_user(conn, handler):
    cookies = parse_cookies(handler.headers.get("Cookie"))
    session_id = valid_session_id(cookies.get(SESSION_COOKIE))
    if not session_id:
        return None
    now = int(time.time())
    user = one(
        conn,
        """
        SELECT users.*
        FROM user_sessions
        JOIN users ON users.id = user_sessions.user_id
        WHERE user_sessions.session_id = ?
          AND user_sessions.expires_at > ?
        """,
        (session_id, now),
    )
    if not user:
        return None
    identities = rows(
        conn,
        """
        SELECT provider, email, display_name, avatar_url
        FROM user_identities
        WHERE user_id = ?
        ORDER BY provider
        """,
        (user["id"],),
    )
    return {**user, "identities": identities, "session_id": session_id}


def create_session(conn, user_id):
    session_id = secrets.token_urlsafe(32)
    now = int(time.time())
    conn.execute(
        "INSERT INTO user_sessions(session_id, user_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
        (session_id, user_id, now, now + SESSION_TTL_SECONDS),
    )
    conn.commit()
    return session_id


def upsert_oauth_user(conn, provider, profile, raw_payload):
    existing = one(
        conn,
        "SELECT user_id FROM user_identities WHERE provider = ? AND provider_user_id = ?",
        (provider, profile["provider_user_id"]),
    )
    now = now_iso()
    if existing:
        user_id = existing["user_id"]
    else:
        if getattr(conn, "is_postgres", False):
            row = conn.execute(
                "INSERT INTO users(account_name, minecraft_name, created_at, updated_at) VALUES (?, ?, ?, ?) RETURNING id",
                (profile["display_name"], None, now, now),
            ).fetchone()
            user_id = row["id"]
        else:
            conn.execute(
                "INSERT INTO users(account_name, minecraft_name, created_at, updated_at) VALUES (?, ?, ?, ?)",
                (profile["display_name"], None, now, now),
            )
            user_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.execute(
        """
        INSERT INTO user_identities(
            provider, provider_user_id, user_id, email, display_name, avatar_url, raw_json, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(provider, provider_user_id) DO UPDATE SET
            email = excluded.email,
            display_name = excluded.display_name,
            avatar_url = excluded.avatar_url,
            raw_json = excluded.raw_json,
            updated_at = excluded.updated_at
        """,
        (
            provider,
            profile["provider_user_id"],
            user_id,
            profile.get("email"),
            profile.get("display_name"),
            profile.get("avatar_url"),
            json.dumps(raw_payload, sort_keys=True),
            now,
            now,
        ),
    )
    conn.execute("UPDATE users SET updated_at = ? WHERE id = ?", (now, user_id))
    conn.commit()
    return user_id


def user_public_payload(user):
    if not user:
        return None
    return {
        "id": user["id"],
        "account_name": user.get("account_name"),
        "minecraft_name": user.get("minecraft_name"),
        "created_at": user.get("created_at"),
        "identities": user.get("identities", []),
    }


def provider_status():
    return [
        {
            "provider": key,
            "label": config["label"],
            "configured": provider_config(key)["configured"],
        }
        for key, config in OAUTH_PROVIDERS.items()
    ]


def player_transaction_history(conn, minecraft_name, limit=100):
    if not minecraft_name:
        return {"summary": None, "sales": [], "purchases": []}
    limited = max(1, min(200, int(limit or 100)))
    seller_summary = one(
        conn,
        f"""
        SELECT
            COUNT(*) AS sales,
            COALESCE(SUM(quantity), 0) AS items,
            COALESCE(SUM(total_price), 0) AS money
        FROM auction_sales
        WHERE lower(seller_name) = lower(?)
          AND {excluded_sql()}
        """,
        (minecraft_name,),
    )
    seller_rows = rows(
        conn,
        f"""
        SELECT sold_at_ms, item_key, item_id, display_name, quantity, price_each, total_price
        FROM auction_sales
        WHERE lower(seller_name) = lower(?)
          AND {excluded_sql()}
        ORDER BY sold_at_ms DESC
        LIMIT ?
        """,
        (minecraft_name, limited),
    )
    return {
        "summary": seller_summary,
        "sales": seller_rows,
        "purchases": [],
        "note": "Donut's transaction data exposes seller names here. Buyer history can be added if the API exposes buyer names.",
    }


def table_count_value(conn, table):
    if getattr(conn, "is_postgres", False):
        row = one(conn, "SELECT COALESCE(reltuples, 0)::bigint AS value FROM pg_class WHERE oid = ?::regclass", (table,))
        return row["value"] if row else 0
    return one(conn, f"SELECT COUNT(*) AS value FROM {table}")["value"]


def summary(conn):
    now_ms = int(time.time() * 1000)
    day_ms = 24 * 60 * 60 * 1000
    if getattr(conn, "is_postgres", False):
        last_24h = one(
            conn,
            """
            SELECT
                COALESCE(SUM(sales_count_24h), 0)::bigint AS transactions,
                COALESCE(SUM(units_sold_24h), 0)::bigint AS units,
                COALESCE(SUM(volume_24h), 0)::double precision AS volume
            FROM market_stats
            """,
        )
        previous_24h = {"volume": 0}
    else:
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
        "sales": table_count_value(conn, "auction_sales"),
        "listings": table_count_value(conn, "auction_listing_snapshots"),
        "items": table_count_value(conn, "market_stats"),
        "candles": table_count_value(conn, "item_candles_1m"),
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
          AND {excluded_sql()}
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
                (sold_median_24h - sold_median_7d) * 100.0 / sold_median_7d AS change_pct
            FROM market_stats
            WHERE sold_median_24h IS NOT NULL
              AND sold_median_7d IS NOT NULL
              AND sold_median_7d > 0
              AND sales_count_24h >= 5
              AND {excluded_sql()}
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
        f"""
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
                (market_value - lowest_listing) * 100.0 / market_value AS discount_pct
            FROM market_stats
            WHERE market_value IS NOT NULL
              AND lowest_listing IS NOT NULL
              AND market_value > 0
              AND lowest_listing < market_value
              AND sales_count_24h >= ?
              AND {excluded_sql()}
        )
        ORDER BY discount_pct DESC, liquidity_score DESC
        LIMIT ?
        """,
        (min_sales, limit),
    )
    return decorate_items(result)


def villager_items(conn, params):
    profession_filter = params.get("profession", ["all"])[0]
    trade_items = [
        trade for trade in VILLAGER_TRADE_ITEMS
        if not is_excluded_item(trade["item_id"])
        and (profession_filter == "all" or trade["profession"] == profession_filter)
    ]
    item_ids = sorted({trade["item_id"] for trade in trade_items})
    prices = market_prices(conn, item_ids)
    professions = sorted({trade["profession"] for trade in VILLAGER_TRADE_ITEMS})
    rows_out = []
    seen = set()
    for trade in trade_items:
        key = (trade["profession"], trade["level"], trade["item_id"])
        if key in seen:
            continue
        seen.add(key)
        price = prices.get(trade["item_id"], {})
        name = price.get("display_name") or readable_name_from_id(trade["item_id"])
        row = {
            **trade,
            "name": name,
            "display_name": name,
            "item_key": price.get("item_key"),
            "market_value": price.get("market_value"),
            "sold_median_24h": price.get("sold_median_24h"),
            "lowest_listing": price.get("lowest_listing"),
            "sales_count_24h": price.get("sales_count_24h") or 0,
            "volume_24h": price.get("volume_24h") or 0,
            "listing_count": price.get("listing_count") or 0,
            "listed_quantity": price.get("listed_quantity") or 0,
            "max_stack": max_stack_size(trade["item_id"]),
        }
        row["price_each"] = price.get("price_each")
        row["price_stack"] = row["price_each"] * row["max_stack"] if row["price_each"] is not None else None
        rows_out.append(row)

    order_map = {
        "price": lambda row: (row["price_each"] is None, -(row["price_each"] or 0), row["profession"], row["name"]),
        "sales": lambda row: (-(row["sales_count_24h"] or 0), row["profession"], row["name"]),
        "listed": lambda row: (row["lowest_listing"] is None, row["lowest_listing"] or 0, row["profession"], row["name"]),
        "profession": lambda row: (row["profession"], row["level"], row["name"]),
    }
    sort = params.get("sort", ["sales"])[0]
    rows_out.sort(key=order_map.get(sort, order_map["sales"]))
    return {"professions": professions, "items": decorate_items(rows_out)}


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
        WHERE (
               lower(COALESCE(display_name, '')) LIKE ?
            OR lower(item_id) LIKE ?
        )
          AND {excluded_sql()}
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
    limit = timeframe_limit(params.get("range", ["24h"])[0])
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
                THEN (sold_median_24h - sold_median_7d) * 100.0 / sold_median_7d
                ELSE NULL
            END AS change_pct
        FROM market_stats
        WHERE item_key = ?
           OR base_item_key = ?
           OR item_id = ?
        ORDER BY
            CASE WHEN item_key = ? THEN 0 ELSE 1 END,
            sales_count_24h DESC,
            volume_24h DESC
        LIMIT 1
        """,
        (item_key, item_key, item_key, item_key),
    )
    if not stats:
        return None
    if is_excluded_item(stats.get("item_id")):
        return None
    stats["variant_note"] = variant_note(stats.get("item_id"))
    stats["max_stack"] = max_stack_size(stats.get("item_id"))
    price_each = stats.get("market_value") or stats.get("sold_median_24h") or stats.get("lowest_listing")
    stats["price_each"] = price_each
    stats["price_stack"] = price_each * stats["max_stack"] if price_each is not None else None
    stats["suggested_prices"] = suggested_prices(stats)
    stats["uses"] = enrich_recipe_economics(conn, item_uses(stats.get("item_id")))
    stats["candles"] = candles(conn, {"item_key": [item_key], "range": [params.get("range", ["24h"])[0]]})
    stats["recent_sales"] = recent_sales(conn, item_key)
    stats["current_listings"] = current_listings(conn, item_key)
    stats["listing_observed_at"] = (
        max((row.get("snapshot_at") for row in stats["current_listings"] if row.get("snapshot_at")), default=None)
    )
    return stats


class DashboardHandler(SimpleHTTPRequestHandler):
    db_path = None

    def translate_path(self, path):
        parsed = urlparse(path)
        if parsed.path == "/" or parsed.path.startswith("/item/") or parsed.path in {"/account", "/villagers"}:
            return str(STATIC_ROOT / "index.html")
        return str(STATIC_ROOT / parsed.path.lstrip("/"))

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path.startswith("/auth/"):
            self.handle_auth_get(parsed)
            return
        if parsed.path.startswith("/api/"):
            self.handle_api(parsed)
            return
        super().do_GET()

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path.startswith("/api/"):
            self.handle_api_post(parsed)
            return
        self.send_json({"error": "not found"}, status=404)

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
                elif parsed.path == "/api/villagers":
                    key = f"villagers:{parsed.query}"
                    payload = cached(key, 30, lambda: villager_items(conn, params))
                elif parsed.path == "/api/search":
                    key = f"search:{parsed.query}"
                    payload = cached(key, 10, lambda: search(conn, params))
                elif parsed.path == "/api/candles":
                    key = f"candles:{parsed.query}"
                    payload = cached(key, 30, lambda: candles(conn, params))
                elif parsed.path == "/api/item":
                    key = f"item:{parsed.query}"
                    payload = cached(key, 15, lambda: item_detail(conn, params))
                elif parsed.path == "/api/auth/me":
                    with connect_write(self.db_path) as write_conn:
                        user = current_user(write_conn, self)
                    payload = {"user": user_public_payload(user), "providers": provider_status()}
                elif parsed.path == "/api/account/transactions":
                    with connect_write(self.db_path) as write_conn:
                        user = current_user(write_conn, self)
                    if not user:
                        self.send_json({"error": "login required"}, status=401)
                        return
                    payload = player_transaction_history(conn, user.get("minecraft_name"), params.get("limit", ["100"])[0])
                else:
                    self.send_json({"error": "not found"}, status=404)
                    return
            self.send_json(payload)
        except Exception as error:
            self.send_json({"error": str(error)}, status=500)

    def handle_api_post(self, parsed):
        try:
            with connect_write(self.db_path) as conn:
                user = current_user(conn, self)
                if parsed.path == "/api/account/profile":
                    if not user:
                        self.send_json({"error": "login required"}, status=401)
                        return
                    payload = json_request(self)
                    account_name = (payload.get("account_name") or "").strip()[:40] or None
                    minecraft_name = (payload.get("minecraft_name") or "").strip()[:40] or None
                    conn.execute(
                        "UPDATE users SET account_name = ?, minecraft_name = ?, updated_at = ? WHERE id = ?",
                        (account_name, minecraft_name, now_iso(), user["id"]),
                    )
                    conn.commit()
                    updated = current_user(conn, self)
                    self.send_json({"user": user_public_payload(updated)})
                    return
                if parsed.path == "/api/auth/logout":
                    if user:
                        conn.execute("DELETE FROM user_sessions WHERE session_id = ?", (user["session_id"],))
                        conn.commit()
                    self.send_json({"ok": True}, clear_session=True)
                    return
            self.send_json({"error": "not found"}, status=404)
        except Exception as error:
            self.send_json({"error": str(error)}, status=500)

    def handle_auth_get(self, parsed):
        parts = [part for part in parsed.path.split("/") if part]
        if len(parts) < 2:
            self.redirect("/account?auth_error=not_found")
            return
        provider = parts[1]
        config = provider_config(provider)
        if not config:
            self.redirect("/account?auth_error=unknown_provider")
            return
        if len(parts) == 2:
            self.start_oauth(provider, config, parsed)
            return
        if len(parts) == 3 and parts[2] == "callback":
            self.finish_oauth(provider, config, parsed)
            return
        self.redirect("/account?auth_error=not_found")

    def start_oauth(self, provider, config, parsed):
        if not config["configured"]:
            self.redirect(f"/account?auth_error={provider}_not_configured")
            return
        query = parse_qs(parsed.query)
        next_path = query.get("next", ["/account"])[0]
        if not next_path.startswith("/"):
            next_path = "/account"
        state = secrets.token_urlsafe(32)
        now = int(time.time())
        with connect_write(self.db_path) as conn:
            conn.execute("DELETE FROM oauth_states WHERE expires_at <= ?", (now,))
            conn.execute(
                "INSERT INTO oauth_states(state, provider, created_at, expires_at, next_path) VALUES (?, ?, ?, ?, ?)",
                (state, provider, now, now + OAUTH_STATE_TTL_SECONDS, next_path),
            )
            conn.commit()
        params = {
            "client_id": config["client_id"],
            "redirect_uri": oauth_redirect_uri(self, provider),
            "response_type": "code",
            "scope": config["scope"],
            "state": state,
        }
        if provider == "google":
            params["access_type"] = "offline"
            params["prompt"] = "select_account"
        self.redirect(f"{config['authorize_url']}?{urlencode(params)}")

    def finish_oauth(self, provider, config, parsed):
        params = parse_qs(parsed.query)
        code = params.get("code", [""])[0]
        state = params.get("state", [""])[0]
        if not code or not state:
            self.redirect("/account?auth_error=missing_code")
            return
        now = int(time.time())
        with connect_write(self.db_path) as conn:
            state_row = one(
                conn,
                "SELECT * FROM oauth_states WHERE state = ? AND provider = ? AND expires_at > ?",
                (state, provider, now),
            )
            if not state_row:
                self.redirect("/account?auth_error=bad_state")
                return
            conn.execute("DELETE FROM oauth_states WHERE state = ?", (state,))
            conn.commit()
        try:
            token = fetch_form_json(
                config["token_url"],
                {
                    "client_id": config["client_id"],
                    "client_secret": config["client_secret"],
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": oauth_redirect_uri(self, provider),
                },
            )
            access_token = token.get("access_token")
            if not access_token:
                raise RuntimeError("provider did not return access token")
            profile_payload = fetch_bearer_json(config["userinfo_url"], access_token)
            profile = normalize_oauth_profile(provider, profile_payload)
            if not profile.get("provider_user_id"):
                raise RuntimeError("provider did not return user id")
            with connect_write(self.db_path) as conn:
                user_id = upsert_oauth_user(conn, provider, profile, profile_payload)
                session_id = create_session(conn, user_id)
            self.redirect(state_row.get("next_path") or "/account", session_id=session_id)
        except Exception as error:
            self.redirect(f"/account?auth_error={urllib.parse.quote(str(error)[:120])}")

    def redirect(self, location, session_id=None):
        self.send_response(302)
        self.send_header("Location", location)
        if session_id:
            self.send_session_cookie(session_id)
        self.end_headers()

    def send_session_cookie(self, session_id):
        secure = "Secure; " if os.environ.get("DONUTDEX_COOKIE_SECURE", "0") == "1" else ""
        self.send_header(
            "Set-Cookie",
            f"{SESSION_COOKIE}={make_cookie_value(session_id)}; Path=/; Max-Age={SESSION_TTL_SECONDS}; HttpOnly; {secure}SameSite=Lax",
        )

    def clear_session_cookie(self):
        self.send_header("Set-Cookie", f"{SESSION_COOKIE}=; Path=/; Max-Age=0; HttpOnly; SameSite=Lax")

    def send_json(self, payload, status=200, clear_session=False):
        data = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(data)))
        if clear_session:
            self.clear_session_cookie()
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, fmt, *args):
        print(f"{time.strftime('%Y-%m-%dT%H:%M:%S')} {self.address_string()} {fmt % args}")


def main():
    load_env_file(PROJECT_ROOT / ".env.dashboard")
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
