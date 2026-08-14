# Donut Market

SQLite collector for DonutSMP auction listings and completed auction transactions.

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
  --listing-pages-per-cycle 8
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
