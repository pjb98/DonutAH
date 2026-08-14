# DonutSMP Auction API Findings

Date tested: 2026-08-14

API base:

```text
https://api.donutsmp.net
```

Authentication:

```text
Authorization: Bearer <DONUT_API_KEY>
```

The API response did not echo the API key in the tested auction endpoints.

## Tested Endpoints

```text
/v1/auction/list/1
/v1/auction/list/2
/v1/auction/transactions/1
/v1/auction/transactions/2
```

## Active Listing Response Shape

`/v1/auction/list/{page}` returns current auction listings.

Observed records per page:

```text
44
```

Example structure:

```json
{
  "status": 200,
  "result": [
    {
      "seller": {
        "name": ".withyrex2790",
        "uuid": "00000000-0000-0000-0009-01f20f90067a"
      },
      "price": 250000,
      "time_left": 41565049,
      "item": {
        "id": "minecraft:crafter",
        "count": 16,
        "display_name": "",
        "lore": null,
        "enchants": {
          "enchantments": {
            "levels": null
          },
          "trim": {
            "material": "",
            "pattern": ""
          }
        },
        "contents": null
      }
    }
  ]
}
```

Useful normalized fields:

```text
seller.name
seller.uuid
price
time_left
item.id
item.count
item.display_name
item.lore
item.enchants
item.contents
```

## Completed Transaction Response Shape

`/v1/auction/transactions/{page}` returns completed auction sales.

Observed records per page:

```text
100
```

Example structure:

```json
{
  "status": 200,
  "result": [
    {
      "seller": {
        "name": "fqka",
        "uuid": "a16b8690-1971-4989-9125-5d3b59592fdd"
      },
      "price": 100000,
      "unixMillisDateSold": 1786730343771,
      "item": {
        "id": "minecraft:diamond_sword",
        "count": 1,
        "display_name": "",
        "lore": null,
        "enchants": {
          "enchantments": {
            "levels": null
          },
          "trim": {
            "material": "",
            "pattern": ""
          }
        },
        "contents": null
      }
    }
  ]
}
```

Useful normalized fields:

```text
seller.name
seller.uuid
price
unixMillisDateSold
item.id
item.count
item.display_name
item.lore
item.enchants
item.contents
```

No buyer field was observed in the documented or live transaction response.

## Endpoint Counts

Observed from direct test:

```text
/v1/auction/list/1           44 records
/v1/auction/list/2           44 records
/v1/auction/transactions/1   100 records
/v1/auction/transactions/2   100 records
```

## Listing Page Walk

The listing walk was capped at 300 pages.

Observed:

```text
Listing pages checked:       300
Non-empty listing pages:     300
Listings seen:               13,200+
Listings/page:               44
```

Page 300 was still non-empty, so active listings are greater than 13,200.

Implication:

```text
A full active-AH sweep is more than 300 requests.
At a documented 250 req/min limit, a full sweep likely cannot run once per minute.
```

Recommended strategy:

```text
Poll completed transactions frequently.
Run active listing sweeps more slowly as rolling snapshots.
Avoid relying on full active-listing sweeps as the primary historical data source.
```

## Transaction Page Walk

The transaction endpoint exposes up to 10 pages.

Observed:

```text
Transaction pages checked:   10
Transactions seen:           1,000
Oldest/newest window:        32.1 seconds
Approx transaction velocity:  1,869 sales/minute
```

Implication:

```text
The transaction endpoint is very high velocity.
Because only 10 pages are exposed, the visible transaction history window was only about 32 seconds during the test.
The collector should poll /v1/auction/transactions/1..10 roughly every 5 seconds during normal operation.
```

## Collector Design Implications

Recommended V1 polling:

```text
Every 5 seconds:
  fetch /v1/auction/transactions/1..10
  dedupe/observe sales by seller + sold timestamp + price + item payload

Every 5-second cycle with remaining budget:
  fetch roughly 8 active listing pages as a rolling sweep
  store snapshot rows with snapshot timestamp
```

Request budget estimate:

```text
Transaction polling:
10 pages * 12 cycles/minute = 120 req/min

Rolling listing scan:
8 pages * 12 cycles/minute = 96 req/min

Total planned load:
216 req/min

Reserve under 250 req/min:
34 req/min
```

Database should store raw JSON alongside normalized columns because `display_name`, `lore`, `enchants`, and `contents` may matter for custom items and may be null/empty for ordinary vanilla items.

Important calculated fields:

```text
price_each = price / item.count
base_item_key = item.id
item_key = hash(item.id + display_name + lore + enchants + contents)
sale_fingerprint = hash(unixMillisDateSold + price + seller + full item payload)
```

The collector should track `observed_first_at`, `observed_last_at`, and `observation_count` for repeated sightings of the same transaction fingerprint across polls.

The theoretical collision risk remains: without an auction ID, two identical sales by the same seller for the same price in the same millisecond cannot be separated perfectly.

First useful analytics:

```text
24h sold median
7d sold median
current lowest listing
current median listing
24h sales count
24h units sold
24h total volume
liquidity score
discount versus market value
```

Preaggregate candles for charting:

```text
item_candles_1m:
  item_key
  minute_ms
  open
  high
  low
  close
  median
  vwap
  units
  transactions
  volume
```

## Local Files Created

```text
/root/donut-market/collector.py
/root/donut-market/inspect_api.py
/root/donut-market/README.md
/root/donut-market/api_findings.md
```
