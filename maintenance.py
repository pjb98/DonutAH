#!/usr/bin/env python3
import argparse
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path


def utc_now():
    return datetime.now(timezone.utc)


def iso(dt):
    return dt.isoformat(timespec="seconds")


def db_files(db_path):
    base = Path(db_path)
    return [base, Path(f"{db_path}-wal"), Path(f"{db_path}-shm")]


def file_sizes(db_path):
    sizes = {}
    for path in db_files(db_path):
        sizes[str(path)] = path.stat().st_size if path.exists() else 0
    return sizes


def mb(value):
    return round(value / 1024 / 1024, 2)


def table_count(conn, table):
    return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def connect(db_path):
    conn = sqlite3.connect(db_path, timeout=60)
    conn.execute("PRAGMA busy_timeout = 60000")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def ensure_indexes(conn):
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_listing_snapshot_at
            ON auction_listing_snapshots(snapshot_at)
        """
    )
    conn.commit()


def count_old_rows(conn, listing_cutoff_iso, sales_cutoff_ms):
    old_listings = conn.execute(
        """
        SELECT COUNT(*)
        FROM auction_listing_snapshots
        WHERE snapshot_at < ?
        """,
        (listing_cutoff_iso,),
    ).fetchone()[0]
    old_sales = conn.execute(
        """
        SELECT COUNT(*)
        FROM auction_sales
        WHERE sold_at_ms IS NOT NULL
          AND sold_at_ms < ?
        """,
        (sales_cutoff_ms,),
    ).fetchone()[0]
    return old_listings, old_sales


def checkpoint(conn):
    return conn.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchall()


def run_with_retries(label, attempts, delay_seconds, action):
    for attempt in range(1, attempts + 1):
        try:
            return action()
        except sqlite3.OperationalError as error:
            if "locked" not in str(error).lower() or attempt == attempts:
                raise
            print(f"{label}_locked attempt={attempt} retry_in_sec={delay_seconds}")
            time.sleep(delay_seconds)
    return None


def run(args):
    started = time.monotonic()
    now = utc_now()
    listing_cutoff = now - timedelta(hours=args.listing_retention_hours)
    sales_cutoff = now - timedelta(days=args.sales_retention_days)
    listing_cutoff_iso = iso(listing_cutoff)
    sales_cutoff_ms = int(sales_cutoff.timestamp() * 1000)

    print(f"{iso(now)} maintenance_start db={args.db}")
    print(
        f"retention listing_hours={args.listing_retention_hours} "
        f"sales_days={args.sales_retention_days} vacuum={args.vacuum} dry_run={args.dry_run}"
    )

    before_sizes = file_sizes(args.db)
    print("sizes_before_mb " + " ".join(f"{path}={mb(size)}" for path, size in before_sizes.items()))

    with connect(args.db) as conn:
        if args.ensure_indexes:
            ensure_indexes(conn)
        before = {}
        if not args.skip_counts:
            before = {
                "auction_sales": table_count(conn, "auction_sales"),
                "auction_listing_snapshots": table_count(conn, "auction_listing_snapshots"),
                "item_candles_1m": table_count(conn, "item_candles_1m"),
                "market_stats": table_count(conn, "market_stats"),
            }
        if before:
            print("counts_before " + " ".join(f"{key}={value}" for key, value in before.items()))
        old_listings = old_sales = None
        if not args.skip_eligible_counts:
            old_listings, old_sales = count_old_rows(conn, listing_cutoff_iso, sales_cutoff_ms)
            print(f"eligible_for_delete listings={old_listings} sales={old_sales}")
        else:
            print("eligible_for_delete skipped=1")

        if not args.dry_run:
            if args.skip_eligible_counts or old_listings or old_sales:
                def delete_old_rows():
                    before_changes = conn.total_changes
                    conn.execute(
                        """
                        DELETE FROM auction_listing_snapshots
                        WHERE snapshot_at < ?
                        """,
                        (listing_cutoff_iso,),
                    )
                    conn.execute(
                        """
                        DELETE FROM auction_sales
                        WHERE sold_at_ms IS NOT NULL
                          AND sold_at_ms < ?
                        """,
                        (sales_cutoff_ms,),
                    )
                    conn.commit()
                    return conn.total_changes - before_changes

                deleted_rows = run_with_retries("delete", args.lock_retries, args.lock_retry_delay, delete_old_rows)
                print(f"deleted_rows={deleted_rows}")
            else:
                print("delete_skipped no_eligible_rows=1")

            try:
                checkpoint_result = run_with_retries(
                    "checkpoint",
                    args.lock_retries,
                    args.lock_retry_delay,
                    lambda: checkpoint(conn),
                )
                print(f"wal_checkpoint={checkpoint_result}")
            except sqlite3.OperationalError as error:
                print(f"wal_checkpoint_skipped reason={error}")

            if args.vacuum:
                print("vacuum_start")
                run_with_retries("vacuum", args.lock_retries, args.lock_retry_delay, lambda: conn.execute("VACUUM"))
                print("vacuum_done")

        if not args.skip_counts:
            after = {
                "auction_sales": table_count(conn, "auction_sales"),
                "auction_listing_snapshots": table_count(conn, "auction_listing_snapshots"),
                "item_candles_1m": table_count(conn, "item_candles_1m"),
                "market_stats": table_count(conn, "market_stats"),
            }
            print("counts_after " + " ".join(f"{key}={value}" for key, value in after.items()))

    after_sizes = file_sizes(args.db)
    print("sizes_after_mb " + " ".join(f"{path}={mb(size)}" for path, size in after_sizes.items()))
    print(f"{iso(utc_now())} maintenance_done elapsed_sec={time.monotonic() - started:.2f}")


def main():
    parser = argparse.ArgumentParser(description="Prune and compact Donut market SQLite data.")
    parser.add_argument("--db", default="/root/donut-market/donut_market.sqlite")
    parser.add_argument("--listing-retention-hours", type=int, default=48)
    parser.add_argument("--sales-retention-days", type=int, default=30)
    parser.add_argument("--vacuum", action="store_true", help="Run VACUUM after pruning")
    parser.add_argument("--dry-run", action="store_true", help="Report eligible rows without deleting")
    parser.add_argument("--skip-counts", action="store_true", help="Skip full table counts for faster live maintenance")
    parser.add_argument("--skip-eligible-counts", action="store_true", help="Skip eligible-row counts and delete directly")
    parser.add_argument("--ensure-indexes", action="store_true", help="Create maintenance helper indexes before pruning")
    parser.add_argument("--lock-retries", type=int, default=5)
    parser.add_argument("--lock-retry-delay", type=float, default=10.0)
    args = parser.parse_args()

    args.listing_retention_hours = max(1, args.listing_retention_hours)
    args.sales_retention_days = max(1, args.sales_retention_days)
    run(args)


if __name__ == "__main__":
    main()
