# Donut Market

Collector and dashboard for DonutSMP auction listings and completed auction transactions.

The API key is read from `DONUT_API_KEY`. Do not hardcode it into source files.

## Run Once

```sh
export DONUT_API_KEY='your key here'
python3 collector.py --db donut_market.sqlite --transaction-pages 10 --listing-pages 20
```

## Run Transaction-First Service

```sh
export DONUT_API_KEY='your key here'
python3 collector.py \
  --db donut_market.sqlite \
  --service \
  --transaction-pages 10 \
  --tx-interval 5 \
  --listing-pages-per-cycle 8 \
  --aggregate-interval 300
```

This polls all 10 transaction pages every 5 seconds:

```text
10 pages * 12 cycles/minute = 120 transaction requests/minute
```

With 8 listing pages per cycle:

```text
8 pages * 12 cycles/minute = 96 listing requests/minute
```

Total planned load is roughly `216 requests/minute`, leaving reserve under the documented `250 requests/minute` API limit.

Candles and market stats are refreshed outside the hot transaction loop every `300` seconds by default. This keeps transaction polling close to the target 5-second cadence.

## Tables

`auction_sales` stores completed transactions.

`auction_listing_snapshots` stores current listing snapshots.

`market_stats` stores a first-pass per-item summary:

- sold median over 1h, 24h, and 7d
- current lowest listing
- current median listing
- 24h sales count, unit volume, and dollar volume
- simple liquidity score

`item_candles_1m` stores one-minute OHLC/median/VWAP preaggregates for charting.

`collector_state` stores service state such as the next active-listing page to scan.

## Item Identity

The collector stores both:

```text
base_item_key     minecraft:diamond_pickaxe
item_key          hash(id + display_name + lore + enchants + contents)
```

That allows commodity-level analytics and separate variant analytics for enchanted/custom items.

## Example Query

```sh
sqlite3 donut_market.sqlite "
SELECT display_name, item_id, market_value, lowest_listing, sales_count_24h
FROM market_stats
WHERE market_value IS NOT NULL
ORDER BY sales_count_24h DESC
LIMIT 20;"
```

## PostgreSQL

PostgreSQL is the live collector and dashboard database. SQLite remains on disk as the
pre-cutover database and rollback/reference copy.

The private connection string is read from `DONUTDEX_DATABASE_URL` in `.env.dashboard`.
Do not commit `.env.dashboard`.

Apply the PostgreSQL schema only:

```sh
python3 migrate_sqlite_to_postgres.py --schema-only
```

Run a small smoke import:

```sh
python3 migrate_sqlite_to_postgres.py --skip-schema --limit 1000 --batch-size 250
```

Run a resumable table import:

```sh
python3 migrate_sqlite_to_postgres.py --skip-schema --table auction_sales --batch-size 5000
```

Resume a single-primary-key table after the highest primary key already in PostgreSQL:

```sh
python3 migrate_sqlite_to_postgres.py \
  --skip-schema \
  --table auction_sales \
  --batch-size 5000 \
  --skip-count \
  --resume-from-postgres \
  --sleep-between-batches 0.5
```

Catch up recent completed sales after a long backfill:

```sh
python3 migrate_sqlite_to_postgres.py \
  --skip-schema \
  --table auction_sales \
  --batch-size 5000 \
  --skip-count \
  --sales-since-minutes 180 \
  --sleep-between-batches 0.25
```

The migration script uses primary-key `ON CONFLICT DO NOTHING`, so interrupted runs can
be started again. Do not run a full import until disk headroom has been checked; keeping
SQLite and PostgreSQL side-by-side temporarily duplicates a large amount of data.

Completed sales were backfilled into PostgreSQL before cutover. The rolling listing
scanner is rebuilding PostgreSQL listing coverage over time; old listing snapshots should
not be copied blindly without a retention plan.
