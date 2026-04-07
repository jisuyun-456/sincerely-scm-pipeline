# ================================================================
# 실제배송일수 백필 스크립트
# ================================================================
# [로직]
#   배송방식(rollup)에 "택배" 포함 AND 구간유형=수도권      → 2
#   배송방식(rollup)에 "택배" 포함 AND 구간유형=지방/도서   → 3
#   배송방식(rollup)에 "택배" 미포함 (퀵/직납 등)           → 0 (당일)
#
# [대상]
#   발송상태_TMS = "출하 완료" AND 실제배송일수 = BLANK()
#
# [환경변수]
#   AIRTABLE_PAT : Airtable Personal Access Token
# ================================================================

import os
import time
import requests

# ── 설정 ──────────────────────────────────────────────────────────
PAT        = os.environ.get("AIRTABLE_PAT", "")
BASE_ID    = "app4x70a8mOrIKsMf"
TABLE_ID   = "tbllg1JoHclGYer7m"
API_BASE   = f"https://api.airtable.com/v0/{BASE_ID}/{TABLE_ID}"

HEADERS = {
    "Authorization": f"Bearer {PAT}",
    "Content-Type": "application/json",
}

# ── 필드 ID ────────────────────────────────────────────────────────
FLD_DELIVERY_DAYS  = "fld1EJjUSSKKboinl"   # 실제배송일수 (number)
FLD_DELIVERY_TYPE  = "flduzH5tS7orqGG3o"   # 배송방식 (rollup)
FLD_ZONE           = "fldp6haTDFzzF5C74"   # 구간유형 (singleSelect)
FLD_STATUS         = "fldOhibgxg6LIpRTi"   # 발송상태_TMS

# ── 구간유형 분류 ───────────────────────────────────────────────────
ZONE_2DAY = {"수도권"}
ZONE_3DAY = {"지방(광역시)", "지방(기타)", "도서산간"}


def calc_days(delivery_type_raw, zone: str) -> int | None:
    """배송방식과 구간유형으로 실제배송일수 계산. 출하확정일 없으면 None."""
    # rollup 필드는 문자열 또는 리스트로 반환될 수 있음
    if isinstance(delivery_type_raw, list):
        type_str = " ".join(str(v) for v in delivery_type_raw)
    else:
        type_str = str(delivery_type_raw) if delivery_type_raw else ""

    if "택배" in type_str:
        if zone in ZONE_2DAY:
            return 2
        else:
            return 3
    else:
        return 0


def fetch_all_records() -> list[dict]:
    """필터 조건에 맞는 Shipment 레코드 전체 조회 (페이지네이션)."""
    records = []
    offset = None
    page = 1

    formula = 'AND({발송상태_TMS}="출하 완료",{실제배송일수}=BLANK())'
    fields  = [FLD_DELIVERY_DAYS, FLD_DELIVERY_TYPE, FLD_ZONE, FLD_STATUS]

    while True:
        params: dict = {
            "filterByFormula": formula,
            "fields[]": fields,
            "pageSize": 100,
            "returnFieldsByFieldId": "true",  # 응답 키를 field ID로 반환
        }
        if offset:
            params["offset"] = offset

        resp = requests.get(API_BASE, headers=HEADERS, params=params)
        resp.raise_for_status()
        data = resp.json()

        batch = data.get("records", [])
        records.extend(batch)
        print(f"  page {page}: {len(batch)}건 수신 (누적 {len(records)}건)")

        offset = data.get("offset")
        if not offset:
            break

        page += 1
        time.sleep(0.2)  # rate limit 방지

    return records


def patch_records(updates: list[dict]) -> None:
    """최대 10건씩 PATCH 업데이트."""
    for i in range(0, len(updates), 10):
        batch = updates[i : i + 10]
        payload = {
            "records": [
                {
                    "id": rec["id"],
                    "fields": {FLD_DELIVERY_DAYS: rec["days"]},
                }
                for rec in batch
            ]
        }
        resp = requests.patch(API_BASE, headers=HEADERS, json=payload)
        resp.raise_for_status()
        time.sleep(0.2)


def main() -> None:
    if not PAT:
        raise ValueError("AIRTABLE_PAT 환경변수가 설정되지 않았습니다.")

    print("=" * 60)
    print("실제배송일수 백필 시작")
    print("=" * 60)

    print("\n[1] 대상 레코드 조회 중...")
    records = fetch_all_records()
    print(f"  총 {len(records)}건 조회 완료\n")

    if not records:
        print("백필 대상 레코드 없음. 종료.")
        return

    # ── 로직 적용 ─────────────────────────────────────────────────
    updates = []
    cnt = {"2일": 0, "3일": 0, "당일(0)": 0, "스킵(구간유형 없음)": 0}

    for rec in records:
        flds = rec.get("fields", {})
        delivery_type = flds.get(FLD_DELIVERY_TYPE)
        zone          = flds.get(FLD_ZONE, "")

        if not zone and "택배" in str(delivery_type or ""):
            # 구간유형 없는 택배 → 스킵 (수동 확인 필요)
            cnt["스킵(구간유형 없음)"] += 1
            continue

        days = calc_days(delivery_type, zone)

        if days == 2:
            cnt["2일"] += 1
        elif days == 3:
            cnt["3일"] += 1
        else:
            cnt["당일(0)"] += 1

        updates.append({"id": rec["id"], "days": days})

    print("[2] 분류 결과:")
    for label, c in cnt.items():
        print(f"  {label}: {c}건")
    print(f"  → 업데이트 예정: {len(updates)}건\n")

    # ── 업데이트 ──────────────────────────────────────────────────
    if not updates:
        print("업데이트 대상 없음. 종료.")
        return

    print("[3] Airtable 업데이트 중...")
    patch_records(updates)
    print(f"  완료: {len(updates)}건 업데이트\n")

    print("=" * 60)
    print("백필 완료")
    print("=" * 60)


if __name__ == "__main__":
    main()
