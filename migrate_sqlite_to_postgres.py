#!/usr/bin/env python3
import argparse
import os
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import psycopg2
from psycopg2.extras import execute_values


ROOT = Path(__file__).resolve().parent
DEFAULT_SQLITE = ROOT / "donut_market.sqlite"
DEFAULT_SCHEMA = ROOT / "postgres_schema.sql"
ENV_FILE = ROOT / ".env.dashboard"

TABLES = {
    "auction_sales": {
        "pk": "sale_key",
        "columns": [
            "sale_key",
            "sale_fingerprint",
            "sold_at",
            "sold_at_ms",
            "collected_first_at",
            "collected_last_at",
            "observation_count",
            "base_item_key",
            "item_key",
            "item_hash",
            "item_id",
            "display_name",
            "quantity",
            "total_price",
            "price_each",
            "seller_name",
            "seller_uuid",
            "enchants_json",
            "lore_json",
            "contents_json",
            "raw_json",
            "inserted_at",
        ],
    },
    "auction_listing_snapshots": {
        "pk": "listing_key",
        "columns": [
            "listing_key",
            "snapshot_at",
            "page",
            "row_index",
            "base_item_key",
            "item_key",
            "item_hash",
            "item_id",
            "display_name",
            "quantity",
            "total_price",
            "price_each",
            "seller_name",
            "seller_uuid",
            "time_left",
            "enchants_json",
            "lore_json",
            "contents_json",
            "raw_json",
        ],
    },
    "market_stats": {
        "pk": "item_key",
        "columns": [
            "item_key",
            "calculated_at",
            "base_item_key",
            "item_id",
            "display_name",
            "sold_median_1h",
            "sold_median_24h",
            "sold_median_7d",
            "units_sold_24h",
            "sales_count_24h",
            "volume_24h",
            "lowest_listing",
            "median_listing",
            "listing_count",
            "listed_quantity",
            "market_value",
            "liquidity_score",
        ],
    },
    "item_candles_1m": {
        "pk": ("item_key", "minute_ms"),
        "columns": [
            "item_key",
            "minute_ms",
            "base_item_key",
            "item_id",
            "display_name",
            "open",
            "high",
            "low",
            "close",
            "median",
            "vwap",
            "units",
            "transactions",
            "volume",
            "updated_at",
        ],
    },
    "collector_state": {
        "pk": "key",
        "columns": ["key", "value"],
    },
    "users": {
        "pk": "id",
        "columns": ["id", "account_name", "minecraft_name", "created_at", "updated_at"],
    },
    "user_identities": {
        "pk": ("provider", "provider_user_id"),
        "columns": [
            "provider",
            "provider_user_id",
            "user_id",
            "email",
            "display_name",
            "avatar_url",
            "raw_json",
            "created_at",
            "updated_at",
        ],
    },
    "user_sessions": {
        "pk": "session_id",
        "columns": ["session_id", "user_id", "created_at", "expires_at"],
    },
    "oauth_states": {
        "pk": "state",
        "columns": ["state", "provider", "created_at", "expires_at", "next_path"],
    },
}


def load_env_file(path):
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def pg_connect():
    load_env_file(ENV_FILE)
    url = os.environ.get("DONUTDEX_DATABASE_URL")
    if not url:
        raise SystemExit("Set DONUTDEX_DATABASE_URL in .env.dashboard or the environment.")
    return psycopg2.connect(url)


def sqlite_connect(path):
    uri = f"file:{path}?mode=ro"
    conn = sqlite3.connect(uri, uri=True, timeout=60)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 60000")
    return conn


def apply_schema(pg_conn, schema_path):
    sql = schema_path.read_text(encoding="utf-8")
    with pg_conn.cursor() as cursor:
        cursor.execute(sql)
    pg_conn.commit()


def table_exists(sqlite_conn, table):
    row = sqlite_conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table,),
    ).fetchone()
    return row is not None


def table_count(sqlite_conn, table):
    if not table_exists(sqlite_conn, table):
        return 0
    return sqlite_conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def iso_minutes_ago(minutes):
    return (datetime.now(timezone.utc) - timedelta(minutes=minutes)).isoformat(timespec="seconds")


def select_batch(sqlite_conn, table, columns, pk, last_pk, batch_size, extra_where_sql="", extra_params=()):
    column_sql = ", ".join(columns)
    order_sql = ", ".join(pk) if isinstance(pk, tuple) else pk
    where_parts = []
    params = []
    if extra_where_sql:
        where_parts.append(f"({extra_where_sql})")
        params.extend(extra_params)
    if last_pk is not None:
        if isinstance(pk, tuple):
            where_parts.append(f"({', '.join(pk)}) > ({', '.join('?' for _ in pk)})")
            params.extend(last_pk)
        else:
            where_parts.append(f"{pk} > ?")
            params.append(last_pk)
    where_sql = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""
    params.append(batch_size)
    return sqlite_conn.execute(
        f"SELECT {column_sql} FROM {table} {where_sql} ORDER BY {order_sql} LIMIT ?",
        params,
    ).fetchall()


def upsert_batch(pg_conn, table, columns, pk, batch):
    if not batch:
        return
    rows = [[row[column] for column in columns] for row in batch]
    column_sql = ", ".join(columns)
    conflict_sql = ", ".join(pk) if isinstance(pk, tuple) else pk
    with pg_conn.cursor() as cursor:
        execute_values(
            cursor,
            f"""
            INSERT INTO {table} ({column_sql})
            VALUES %s
            ON CONFLICT ({conflict_sql}) DO NOTHING
            """,
            rows,
            page_size=len(rows),
        )
    pg_conn.commit()


def reset_sequences(pg_conn):
    with pg_conn.cursor() as cursor:
        cursor.execute(
            """
            SELECT setval(
                pg_get_serial_sequence('users', 'id'),
                COALESCE((SELECT MAX(id) FROM users), 1),
                (SELECT COUNT(*) > 0 FROM users)
            )
            """
        )
    pg_conn.commit()


def pg_max_pk(pg_conn, table, pk):
    if isinstance(pk, tuple):
        raise ValueError("--resume-from-postgres only supports single-column primary keys")
    with pg_conn.cursor() as cursor:
        cursor.execute(f"SELECT MAX({pk}) FROM {table}")
        row = cursor.fetchone()
    return row[0] if row else None


def migrate_table(
    sqlite_conn,
    pg_conn,
    table,
    spec,
    batch_size,
    limit,
    skip_count,
    resume_from_postgres,
    sleep_seconds,
    sales_since_minutes,
):
    if not table_exists(sqlite_conn, table):
        print(f"{table}: skipped missing sqlite table")
        return 0

    if resume_from_postgres:
        last_pk = pg_max_pk(pg_conn, table, spec["pk"])
        if last_pk is not None:
            print(f"{table}: resuming after {spec['pk']}={last_pk}", flush=True)
    else:
        last_pk = None

    extra_where_sql = ""
    extra_params = ()
    if sales_since_minutes is not None:
        if table != "auction_sales":
            raise ValueError("--sales-since-minutes can only be used with auction_sales")
        cutoff_iso = iso_minutes_ago(sales_since_minutes)
        extra_where_sql = "sold_at >= ?"
        extra_params = (cutoff_iso,)
        print(f"{table}: copying rows with sold_at >= {cutoff_iso}", flush=True)

    if skip_count or extra_where_sql:
        total = None
    else:
        total = table_count(sqlite_conn, table)
        if limit:
            total = min(total, limit)

    copied = 0
    started = time.monotonic()
    while limit is None or copied < limit:
        remaining = batch_size if limit is None else min(batch_size, limit - copied)
        if remaining <= 0:
            break
        batch = select_batch(
            sqlite_conn,
            table,
            spec["columns"],
            spec["pk"],
            last_pk,
            remaining,
            extra_where_sql=extra_where_sql,
            extra_params=extra_params,
        )
        if not batch:
            break
        upsert_batch(pg_conn, table, spec["columns"], spec["pk"], batch)
        copied += len(batch)
        pk = spec["pk"]
        last_row = batch[-1]
        last_pk = tuple(last_row[column] for column in pk) if isinstance(pk, tuple) else last_row[pk]
        elapsed = max(0.001, time.monotonic() - started)
        rate = copied / elapsed
        total_label = f"{total:,}" if total is not None else "unknown"
        print(f"{table}: copied {copied:,}/{total_label} rows ({rate:,.0f} rows/sec)", flush=True)
        if sleep_seconds > 0:
            time.sleep(sleep_seconds)

    return copied


def parse_args():
    parser = argparse.ArgumentParser(description="Migrate DonutDex SQLite data into PostgreSQL.")
    parser.add_argument("--sqlite-db", default=str(DEFAULT_SQLITE))
    parser.add_argument("--schema", default=str(DEFAULT_SCHEMA))
    parser.add_argument("--batch-size", type=int, default=5000)
    parser.add_argument("--limit", type=int, default=None, help="Per-table row limit for smoke tests")
    parser.add_argument("--table", action="append", choices=sorted(TABLES), help="Copy only this table; can be repeated")
    parser.add_argument("--schema-only", action="store_true")
    parser.add_argument("--skip-schema", action="store_true")
    parser.add_argument("--skip-count", action="store_true", help="Do not count source rows before copying")
    parser.add_argument("--resume-from-postgres", action="store_true", help="Start after the highest primary key already in PostgreSQL")
    parser.add_argument("--sleep-between-batches", type=float, default=0.0, help="Seconds to sleep after each committed batch")
    parser.add_argument("--sales-since-minutes", type=int, default=None, help="Copy recent auction_sales by sold_at timestamp")
    return parser.parse_args()


def main():
    args = parse_args()
    sqlite_path = Path(args.sqlite_db)
    schema_path = Path(args.schema)
    selected_tables = args.table or list(TABLES)

    with pg_connect() as pg_conn:
        if not args.skip_schema:
            apply_schema(pg_conn, schema_path)
            print(f"schema applied from {schema_path}")
        if args.schema_only:
            return

        with sqlite_connect(sqlite_path) as sqlite_conn:
            for table in selected_tables:
                migrate_table(
                    sqlite_conn,
                    pg_conn,
                    table,
                    TABLES[table],
                    max(1, args.batch_size),
                    args.limit,
                    args.skip_count,
                    args.resume_from_postgres,
                    max(0.0, args.sleep_between_batches),
                    args.sales_since_minutes,
                )
        reset_sequences(pg_conn)
        print("migration pass complete")


if __name__ == "__main__":
    main()
