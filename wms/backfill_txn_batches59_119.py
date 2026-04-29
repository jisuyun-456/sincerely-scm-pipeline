"""
WMS_InventoryTransaction backfill — batches 59-119 (610 records)
Airtable REST API, rate-limited to 5 req/sec
"""
import json
import time
import sys
import urllib.request
import urllib.error

PAT = "***REDACTED_PAT***"
BASE_ID = "appLui4ZR5HWcQRri"
TABLE_ID = "tblmNiQDYzcq1A6vp"
URL = f"https://api.airtable.com/v0/{BASE_ID}/{TABLE_ID}"
BATCH_FILE = r"C:\Users\yjisu\Desktop\SCM_WORK\wms\txn_batches.json"

START_BATCH = 59
END_BATCH = 120  # exclusive

def post_batch(records, batch_idx):
    payload = json.dumps(
        {"records": [{"fields": r} for r in records]},
        ensure_ascii=True
    ).encode("utf-8")

    req = urllib.request.Request(
        URL,
        data=payload,
        headers={
            "Authorization": f"Bearer {PAT}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read())
            created = len(result.get("records", []))
            return created, None
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        return 0, f"HTTP {e.code}: {body[:300]}"
    except Exception as e:
        return 0, str(e)


def main():
    sys.stdout.reconfigure(encoding="utf-8")

    with open(BATCH_FILE, encoding="utf-8") as f:
        batches = json.load(f)

    total_batches = END_BATCH - START_BATCH
    total_created = 0
    errors = []

    print(f"Starting backfill: batches {START_BATCH}–{END_BATCH - 1} ({total_batches} batches, ~{total_batches * 10} records)")
    print("=" * 60)

    for i in range(START_BATCH, END_BATCH):
        batch = batches[i]
        created, err = post_batch(batch, i)

        if err:
            errors.append((i, err))
            print(f"[BATCH {i:03d}] ERROR — {err}")
        else:
            total_created += created
            done = i - START_BATCH + 1
            pct = done / total_batches * 100
            print(f"[BATCH {i:03d}] OK +{created} records | total={total_created} ({pct:.1f}%)")

        time.sleep(0.21)  # ~4.8 req/sec, safely under 5 req/sec limit

    print("=" * 60)
    print(f"Done. Created: {total_created} | Errors: {len(errors)}")
    if errors:
        print("Failed batches:")
        for bi, msg in errors:
            print(f"  Batch {bi}: {msg}")


if __name__ == "__main__":
    main()
