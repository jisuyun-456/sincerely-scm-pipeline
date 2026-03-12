"""
sincerely-scm-pipeline
Airtable movement 테이블 → Supabase movement_log 스냅샷
"""

import os
import requests
from datetime import datetime, timezone

# ── 환경변수 ──────────────────────────────────────────
AIRTABLE_TOKEN   = os.environ["AIRTABLE_TOKEN"]       # GitHub Secret
AIRTABLE_BASE_ID = os.environ["AIRTABLE_BASE_ID"]     # GitHub Secret
AIRTABLE_TABLE   = os.environ.get("AIRTABLE_TABLE", "movement")

SUPABASE_URL     = os.environ["SUPABASE_URL"]         # GitHub Secret
SUPABASE_KEY     = os.environ["SUPABASE_KEY"]         # GitHub Secret
SUPABASE_TABLE   = "movement_log"

# ── Airtable 필드명 → Supabase 컬럼명 매핑 ────────────
# 스크린샷 기준 Airtable 원본 필드명 그대로 사용
FIELD_MAP = {
    "movement_id":   "movement_id",       # movement_id
    "이동물품":       "item_desc",          # 이동물품
    "이동목적":       "movement_type",      # 이동목적 (재고이동 / 재고생산)
    "이동수량(변경)": "qty_change",         # 이동수량(변경)
    "입하수량":       "qty_inbound",        # 입하수량
    "출고수량":       "qty_outbound",       # 출고수량
}

# ── Airtable 전체 레코드 가져오기 ─────────────────────
def fetch_airtable_records():
    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{AIRTABLE_TABLE}"
    headers = {"Authorization": f"Bearer {AIRTABLE_TOKEN}"}
    
    records = []
    params = {"pageSize": 100}
    
    while True:
        res = requests.get(url, headers=headers, params=params)
        res.raise_for_status()
        data = res.json()
        records.extend(data.get("records", []))
        
        offset = data.get("offset")
        if not offset:
            break
        params["offset"] = offset
    
    print(f"✅ Airtable에서 {len(records)}개 레코드 가져옴")
    return records

# ── Airtable 레코드 → Supabase row 변환 ──────────────
def transform(record):
    fields = record.get("fields", {})
    row = {
        "airtable_rec_id": record["id"],
        "snapshot_date":   datetime.now(timezone.utc).date().isoformat(),
    }
    for at_field, sb_col in FIELD_MAP.items():
        row[sb_col] = fields.get(at_field)  # 없으면 None (NULL)
    return row

# ── Supabase upsert ────────────────────────────────
def upsert_to_supabase(rows):
    url = f"{SUPABASE_URL}/rest/v1/{SUPABASE_TABLE}"
    headers = {
        "apikey":        SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type":  "application/json",
        "Prefer":        "resolution=merge-duplicates",  # upsert
    }
    
    # 100개씩 배치 처리
    batch_size = 100
    total = 0
    for i in range(0, len(rows), batch_size):
        batch = rows[i:i+batch_size]
        res = requests.post(url, headers=headers, json=batch)
        if res.status_code not in (200, 201):
            print(f"❌ Supabase 오류 ({res.status_code}): {res.text}")
            res.raise_for_status()
        total += len(batch)
        print(f"  → {total}/{len(rows)} rows upserted")
    
    print(f"✅ Supabase에 {total}개 rows 완료")

# ── 메인 ──────────────────────────────────────────
def main():
    print(f"🚀 파이프라인 시작: {datetime.now(timezone.utc).isoformat()}")
    print(f"   테이블: {AIRTABLE_TABLE} → {SUPABASE_TABLE}")
    
    records = fetch_airtable_records()
    rows = [transform(r) for r in records]
    
    # 샘플 확인 (첫 3개)
    print("\n📋 샘플 데이터 (첫 3개):")
    for row in rows[:3]:
        print(f"  {row}")
    
    upsert_to_supabase(rows)
    print(f"\n🎉 완료: {datetime.now(timezone.utc).isoformat()}")

if __name__ == "__main__":
    main()
