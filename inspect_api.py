#!/usr/bin/env python3
import json
import os
import sys
import time
import urllib.error
import urllib.request


API_BASE = "https://api.donutsmp.net"


def fetch(path, api_key):
    req = urllib.request.Request(
        f"{API_BASE}{path}",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
            "User-Agent": "donut-market-inspector/0.1",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")
        return {
            "status": error.code,
            "error": body,
            "path": path,
        }


def summarize(path, data, sample_size=2):
    result = data.get("result")
    count = len(result) if isinstance(result, list) else None
    print(f"\n== {path} ==")
    print(f"status: {data.get('status')}")
    print(f"result_count: {count}")
    if isinstance(result, list):
        print(json.dumps({"status": data.get("status"), "result": result[:sample_size]}, indent=2))
    else:
        print(json.dumps(data, indent=2))


def walk_pages(api_key, prefix, max_pages):
    counts = []
    oldest = None
    newest = None
    for page in range(1, max_pages + 1):
        path = f"{prefix}/{page}"
        data = fetch(path, api_key)
        if data.get("status") and data.get("status") != 200:
            print(f"stopped {prefix} walk at page {page}: status={data.get('status')}")
            break
        result = data.get("result") or []
        counts.append(len(result))
        if prefix.endswith("transactions"):
            for row in result:
                sold = row.get("unixMillisDateSold")
                if sold is not None:
                    oldest = sold if oldest is None else min(oldest, sold)
                    newest = sold if newest is None else max(newest, sold)
        if not result:
            break
        time.sleep(0.25)
    return counts, oldest, newest


def main():
    api_key = os.environ.get("DONUT_API_KEY")
    if not api_key:
        sys.exit("Set DONUT_API_KEY.")

    for path in [
        "/v1/auction/list/1",
        "/v1/auction/list/2",
        "/v1/auction/transactions/1",
        "/v1/auction/transactions/2",
    ]:
        summarize(path, fetch(path, api_key))
        time.sleep(0.05)

    listing_counts, _, _ = walk_pages(api_key, "/v1/auction/list", 300)
    tx_counts, tx_oldest, tx_newest = walk_pages(api_key, "/v1/auction/transactions", 10)

    print("\n== page walk ==")
    print(f"listing_pages_requested: {len(listing_counts)}")
    print(f"listing_non_empty_pages: {sum(1 for count in listing_counts if count)}")
    print(f"listing_counts_first_10: {listing_counts[:10]}")
    print(f"active_listings_seen: {sum(listing_counts)}")
    print(f"transaction_counts: {tx_counts}")
    print(f"transactions_seen: {sum(tx_counts)}")
    print(f"transaction_oldest_ms: {tx_oldest}")
    print(f"transaction_newest_ms: {tx_newest}")
    if tx_oldest and tx_newest and tx_newest > tx_oldest:
        seconds = (tx_newest - tx_oldest) / 1000
        rate = sum(tx_counts) / seconds * 60
        print(f"transaction_window_seconds: {seconds:.1f}")
        print(f"approx_transactions_per_minute_in_window: {rate:.1f}")


if __name__ == "__main__":
    main()
