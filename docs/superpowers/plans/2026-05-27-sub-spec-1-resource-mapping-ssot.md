# Sub-Spec 1: 자원 매핑 SSOT (tms_drivers + tms_3pl_partners + dispatch_advisor 갱신) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** SCM TMS에 자체 기사 3명 + 외주 3PL/carrier 5개사의 단일 진실 원천(SSOT) Airtable 테이블 2개를 신규 생성·시드하고, `dispatch_advisor.py`의 driver roster를 정정(CA-0004 김민준 → 조희선)한다.

**Architecture:** Airtable TMS base(`app4x70a8mOrIKsMf`)에 `tms_drivers` + `tms_3pl_partners` 테이블 신규 → 초기 데이터 시드(3명 + 5개사) → `harness/_core/schema_pin.json`에 신규 테이블 ID + 필드 ID 등록 → 신규 `harness/dispatch/resource_loader.py`로 Airtable 조회 함수 제공 → `dispatch_advisor.py` line 50~57 갱신 (CA-0004 → 조희선 + hardcoded roster를 resource_loader 호출로 전환은 차후 Sub-Spec). 

**Tech Stack:**
- Airtable MCP (`mcp__claude_ai_Airtable__create_table`, `create_records_for_table`, `get_table_schema`)
- Python 3.11+ (requests, pytest)
- harness/_core/airtable.py 패턴 (rate limiting + schema_pin)
- 기존 dispatch_advisor.py (supabase_client, virtual_sap 모듈)

**Validation Contract (Sub-Spec 1 종료 시 모두 PASS 필수):**
- **C1:** Airtable `tms_drivers` 테이블 존재 + 13개 필드 모두 존재 + 3개 record (이장훈/조희선/박종성) 삽입 완료
- **C2:** Airtable `tms_3pl_partners` 테이블 존재 + 11개 필드 모두 존재 + 5개 record (다영기획/베스트원/로지비/로젠택배/고고엑스) 삽입 완료
- **C3:** `harness/_core/schema_pin.json`에 신규 테이블 2개 ID + 24개 필드 ID 모두 반영
- **C4:** 신규 `harness/dispatch/resource_loader.py`의 `load_drivers()` 호출 시 3건 / `load_partners()` 호출 시 5건 dict list 반환 + pytest 통과
- **C5:** `dispatch_advisor.py` line 50~54의 INHOUSE_DRIVERS 갱신 (CA-0004 김민준 → CA-NEW-1 조희선) + 기존 _allocate() unit test 모두 통과

---

## File Structure

| 파일 | 책임 | 신규/수정 |
|------|------|---------|
| Airtable `tms_drivers` (테이블) | 자체 기사 master data SSOT | 🆕 신규 |
| Airtable `tms_3pl_partners` (테이블) | 외주 3PL·carrier master data SSOT | 🆕 신규 |
| `harness/_core/schema_pin.json` | TMS base 스키마 핀 — 신규 테이블 2개 ID + 필드 ID 추가 | ✏️ 수정 |
| `harness/dispatch/__init__.py` | dispatch 패키지 marker | 🆕 신규 (빈 파일) |
| `harness/dispatch/resource_loader.py` | tms_drivers/tms_3pl_partners를 dict list로 로드 | 🆕 신규 |
| `harness/virtual_sap/agents/dispatch_advisor.py` | 기존 — INHOUSE_DRIVERS line 50~54 갱신 | ✏️ 수정 (5줄) |
| `tests/dispatch/test_resource_loader.py` | resource_loader 단위 테스트 | 🆕 신규 |
| `tests/virtual_sap/test_dispatch_advisor_roster.py` | dispatch_advisor 새 roster 회귀 테스트 | 🆕 신규 |
| `scripts/seed/seed_tms_drivers.py` | tms_drivers 시드 스크립트 (재실행 가능 idempotent) | 🆕 신규 |
| `scripts/seed/seed_tms_3pl_partners.py` | tms_3pl_partners 시드 스크립트 | 🆕 신규 |
| `.claude/feature_list.json` | SCM-LANE-SUBSPEC-1 상태 pending → done | ✏️ 수정 |

---

## Task 0: Pre-flight 상태 확인 + 백업

**Files:**
- Read: `harness/_core/schema_pin.json`
- Read: `harness/virtual_sap/agents/dispatch_advisor.py:48-58`
- Backup: `harness/virtual_sap/agents/dispatch_advisor.py.bak.2026-05-27`

- [ ] **Step 1: 현재 schema_pin.json 백업 확인**

```bash
cp "c:/Users/yjisu/Desktop/SCM_WORK/harness/_core/schema_pin.json" \
   "c:/Users/yjisu/Desktop/SCM_WORK/harness/_core/schema_pin.json.bak.2026-05-27"
```

- [ ] **Step 2: dispatch_advisor.py 백업**

```bash
cp "c:/Users/yjisu/Desktop/SCM_WORK/harness/virtual_sap/agents/dispatch_advisor.py" \
   "c:/Users/yjisu/Desktop/SCM_WORK/harness/virtual_sap/agents/dispatch_advisor.py.bak.2026-05-27"
```

- [ ] **Step 3: 현재 TMS base 테이블 목록 확인 (충돌 없음 검증)**

`mcp__claude_ai_Airtable__list_tables_for_base` 호출 — baseId = `app4x70a8mOrIKsMf`

Expected: `tms_drivers`·`tms_3pl_partners` 이름의 테이블 *없음* 확인. 있으면 Task 1·3 skip하고 Task 5(schema_pin)부터 시작.

- [ ] **Step 4: pytest 환경 검증**

```bash
cd "c:/Users/yjisu/Desktop/SCM_WORK" && python -m pytest --version
```

Expected: pytest version 출력. 없으면 `pip install pytest`

---

## Task 1: Airtable `tms_drivers` 테이블 생성 (13개 필드)

**Files:**
- Create: Airtable 테이블 `tms_drivers` in base `app4x70a8mOrIKsMf`

- [ ] **Step 1: tms_drivers 테이블 + 13개 필드 일괄 생성 (MCP create_table)**

`mcp__claude_ai_Airtable__create_table` 호출 — params:

```json
{
  "baseId": "app4x70a8mOrIKsMf",
  "name": "tms_drivers",
  "description": "신시어리 자체 기사 master data SSOT. Sub-Spec 1 (2026-05-27 design doc §1.1)",
  "fields": [
    {"name": "driver_id", "type": "singleLineText", "description": "Primary key 예: CA-0002"},
    {"name": "name", "type": "singleLineText"},
    {"name": "vehicle_model", "type": "singleLineText", "description": "예: 현대 스타리아, 포터, 봉고"},
    {"name": "cbm_capacity", "type": "number", "options": {"precision": 2}, "description": "화물칸 적재 가능 부피 m³"},
    {"name": "residence", "type": "singleLineText", "description": "거주지 시·구 예: 서울 성북구"},
    {"name": "work_hours_start", "type": "singleLineText", "description": "예: 09:00"},
    {"name": "work_hours_end", "type": "singleLineText", "description": "예: 13:00 또는 18:00"},
    {"name": "daily_fixed_cost", "type": "currency", "options": {"precision": 0, "symbol": "₩"}, "description": "일 고정비 (개인사업자 변동비는 0)"},
    {"name": "max_daily_orders", "type": "number", "options": {"precision": 0}, "description": "일 최대 처리 건수"},
    {"name": "contract_type", "type": "singleSelect", "options": {"choices": [{"name": "계약직"}, {"name": "개인사업자"}]}},
    {"name": "wave_pattern", "type": "singleSelect", "options": {"choices": [{"name": "W1-시간고정"}, {"name": "W2-시간고정"}, {"name": "W3-Trigger기반"}]}},
    {"name": "status", "type": "singleSelect", "options": {"choices": [{"name": "active"}, {"name": "inactive"}]}},
    {"name": "notes", "type": "multilineText"}
  ]
}
```

Expected: 응답에 `id` (테이블 ID, `tblXXXX...` 형식) + `fields` 배열에 각 필드 ID (`fldXXXX...`) 포함. 모두 메모해두기 (Task 5에서 사용).

- [ ] **Step 2: 테이블 생성 검증**

`mcp__claude_ai_Airtable__get_table_schema` 호출:

```json
{
  "baseId": "app4x70a8mOrIKsMf",
  "tables": [{"tableId": "<Step 1에서 받은 테이블 ID>"}]
}
```

Expected: 13개 필드 모두 정상 반환.

- [ ] **Step 3: Commit**

```bash
cd "c:/Users/yjisu/Desktop/SCM_WORK" && git add -A && git status --short
git commit --allow-empty -m "feat(airtable): tms_drivers 테이블 신규 (Sub-Spec 1 Task 1)

13개 필드 — driver_id/name/vehicle_model/cbm_capacity/residence/work_hours_start/work_hours_end/daily_fixed_cost/max_daily_orders/contract_type/wave_pattern/status/notes

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: tms_drivers 초기 데이터 3건 시드 (시드 스크립트 작성)

**Files:**
- Create: `scripts/seed/seed_tms_drivers.py`

- [ ] **Step 1: scripts/seed/ 디렉토리 확인**

```bash
mkdir -p "c:/Users/yjisu/Desktop/SCM_WORK/scripts/seed"
```

- [ ] **Step 2: 시드 스크립트 작성**

Create `c:/Users/yjisu/Desktop/SCM_WORK/scripts/seed/seed_tms_drivers.py`:

```python
"""tms_drivers 초기 데이터 시드 — 자체 기사 3명.

재실행 가능 (idempotent): 같은 driver_id 있으면 skip.

Source of truth: _AutoResearch/SCM/outputs/2026-05-27-driver-lane-consolidation-strategy.md §1.1
Run: python scripts/seed/seed_tms_drivers.py
"""
from __future__ import annotations
import os
import sys
import requests

BASE_ID = "app4x70a8mOrIKsMf"
TABLE_NAME = "tms_drivers"  # 또는 schema_pin.json에서 ID 조회로 전환

# 2026-05-27 brainstorm 결과 + 사용자 확정 값
DRIVERS = [
    {
        "driver_id": "CA-0002",
        "name": "이장훈",
        "vehicle_model": "현대 스타리아 (운전석 외 화물칸 활용)",
        "cbm_capacity": 4.5,  # ⚠️ 추정값. 정확 사양은 차량 등록증 확인 필요 (Open Decision 1)
        "residence": "서울 성북구",
        "work_hours_start": "09:00",
        "work_hours_end": "13:00",
        "daily_fixed_cost": 160000,
        "max_daily_orders": 3,
        "contract_type": "계약직",
        "wave_pattern": "W1-시간고정",
        "status": "active",
        "notes": "오후 개인사업으로 오전 슬롯만 가능. 거리 멀면 광명/성남 1건 + 서울 1건 정도. CBM 최소화 운영.",
    },
    {
        "driver_id": "CA-NEW-1",  # 김민준 (CA-0004) 탈퇴 → 신규 발급
        "name": "조희선",
        "vehicle_model": "(확인 필요)",
        "cbm_capacity": 7.6,  # 추정 (기존 INHOUSE_DRIVERS 기본값) — 정확 사양 확인 필요
        "residence": "서울 양천구",
        "work_hours_start": "09:00",
        "work_hours_end": "18:00",
        "daily_fixed_cost": 360000,
        "max_daily_orders": 6,
        "contract_type": "계약직",
        "wave_pattern": "W2-시간고정",
        "status": "active",
        "notes": "오전 3 + 오후 3 = 6건 콘솔 적재. 경기·서울·인천 전역. 99% 오전 1 wave (1% 예외 오후 추가 wave).",
    },
    {
        "driver_id": "CA-0003",
        "name": "박종성",
        "vehicle_model": "(확인 필요)",
        "cbm_capacity": 7.6,  # 추정 — 정확 사양 확인 필요
        "residence": "서울 중랑구",
        "work_hours_start": "",  # 유연 (새벽·낮·야간)
        "work_hours_end": "",
        "daily_fixed_cost": 0,  # 개인사업자 — 배차 시만 지급
        "max_daily_orders": 8,
        "contract_type": "개인사업자",
        "wave_pattern": "W3-Trigger기반",
        "status": "active",
        "notes": "전국 커버, 건수 제한 없음 (7~8건 가능). 새벽 상차·야간 모두 OK. 잔여 1~2건 lightweight wave. 다영기획 임가공 → 퀵 발송 90% 담당.",
    },
]


def _headers(pat: str) -> dict:
    return {"Authorization": f"Bearer {pat}", "Content-Type": "application/json"}


def _existing_driver_ids(headers: dict) -> set[str]:
    url = f"https://api.airtable.com/v0/{BASE_ID}/{TABLE_NAME}"
    params = {"fields[]": ["driver_id"], "pageSize": 100}
    out: set[str] = set()
    offset = None
    while True:
        if offset:
            params["offset"] = offset
        r = requests.get(url, headers=headers, params=params, timeout=30)
        r.raise_for_status()
        data = r.json()
        for rec in data.get("records", []):
            did = rec.get("fields", {}).get("driver_id")
            if did:
                out.add(did)
        offset = data.get("offset")
        if not offset:
            break
    return out


def seed(dry_run: bool = False) -> dict:
    pat = os.environ.get("AIRTABLE_PAT")
    if not pat:
        sys.exit("ERROR: AIRTABLE_PAT 환경변수 필요")

    headers = _headers(pat)
    existing = _existing_driver_ids(headers)

    to_insert = [d for d in DRIVERS if d["driver_id"] not in existing]
    skipped = [d["driver_id"] for d in DRIVERS if d["driver_id"] in existing]

    print(f"기존: {len(existing)}건 / 신규 시드: {len(to_insert)}건 / 스킵: {len(skipped)}건")

    if dry_run:
        for d in to_insert:
            print(f"  [DRY] {d['driver_id']} {d['name']}")
        return {"inserted": 0, "skipped": len(skipped), "would_insert": len(to_insert)}

    inserted = 0
    if to_insert:
        url = f"https://api.airtable.com/v0/{BASE_ID}/{TABLE_NAME}"
        payload = {"records": [{"fields": d} for d in to_insert]}
        r = requests.post(url, headers=headers, json=payload, timeout=30)
        r.raise_for_status()
        inserted = len(r.json().get("records", []))
        print(f"✅ 신규 {inserted}건 시드 완료")

    return {"inserted": inserted, "skipped": len(skipped)}


if __name__ == "__main__":
    dry = "--dry-run" in sys.argv
    result = seed(dry_run=dry)
    print(result)
```

- [ ] **Step 3: Dry-run으로 검증**

```bash
cd "c:/Users/yjisu/Desktop/SCM_WORK" && python scripts/seed/seed_tms_drivers.py --dry-run
```

Expected: `기존: 0건 / 신규 시드: 3건 / 스킵: 0건` + 3개 driver_id 출력

- [ ] **Step 4: 실제 시드 실행**

```bash
cd "c:/Users/yjisu/Desktop/SCM_WORK" && python scripts/seed/seed_tms_drivers.py
```

Expected: `✅ 신규 3건 시드 완료`

- [ ] **Step 5: Airtable에서 직접 검증 (MCP list_records_for_table)**

`mcp__claude_ai_Airtable__list_records_for_table` 호출:

```json
{"baseId": "app4x70a8mOrIKsMf", "tableId": "<Task 1에서 받은 ID>", "maxRecords": 10}
```

Expected: 3개 record (이장훈/조희선/박종성) 모두 13개 필드 채워서 반환.

- [ ] **Step 6: 재실행으로 idempotent 검증**

```bash
cd "c:/Users/yjisu/Desktop/SCM_WORK" && python scripts/seed/seed_tms_drivers.py
```

Expected: `기존: 3건 / 신규 시드: 0건 / 스킵: 3건` — 중복 삽입 안 됨

- [ ] **Step 7: Commit**

```bash
cd "c:/Users/yjisu/Desktop/SCM_WORK" && git add scripts/seed/seed_tms_drivers.py
git commit -m "feat(seed): tms_drivers 초기 3건 시드 스크립트 (Sub-Spec 1 Task 2)

이장훈(CA-0002, 스타리아 ~4.5m³, 오전만, 일 16만)
조희선(CA-NEW-1, 콘솔 6건, 일 36만)
박종성(CA-0003, 전국 7~8건, 변동비 0원)

⚠️ Open Decisions: 이장훈 스타리아 정확 CBM / 조희선·박종성 차량 spec 추후 확정 필요

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: Airtable `tms_3pl_partners` 테이블 생성 (11개 필드)

**Files:**
- Create: Airtable 테이블 `tms_3pl_partners` in base `app4x70a8mOrIKsMf`

- [ ] **Step 1: tms_3pl_partners 테이블 + 11개 필드 일괄 생성 (MCP create_table)**

`mcp__claude_ai_Airtable__create_table` 호출:

```json
{
  "baseId": "app4x70a8mOrIKsMf",
  "name": "tms_3pl_partners",
  "description": "외주 3PL · carrier master data SSOT. Sub-Spec 1 (2026-05-27 design doc §1.2)",
  "fields": [
    {"name": "partner_id", "type": "singleLineText", "description": "Primary key 예: PT-0001"},
    {"name": "partner_name", "type": "singleLineText"},
    {"name": "partner_type", "type": "singleSelect", "options": {"choices": [{"name": "carrier"}, {"name": "3PL"}]}, "description": "carrier = 진짜 운송사 / 3PL = 보관·임가공·풀필먼트 협력사"},
    {"name": "primary_role", "type": "singleLineText", "description": "예: 프로젝트 임가공 협력사, 재고보관 창고, 풀필먼트 보관·출하 협력사"},
    {"name": "location", "type": "singleLineText", "description": "물류 거점 위치 (시·구)"},
    {"name": "autonomy_level", "type": "singleSelect", "options": {"choices": [{"name": "autonomous"}, {"name": "partial"}, {"name": "locked-in"}]}, "description": "우리가 변경 가능한 자율 영역인지"},
    {"name": "lock_in_reason", "type": "singleSelect", "options": {"choices": [{"name": "distance"}, {"name": "customer-designated"}, {"name": "none"}]}, "description": "lock-in 사유"},
    {"name": "monthly_volume_cbm", "type": "number", "options": {"precision": 2}, "description": "월간 처리 CBM (확인 후 입력)"},
    {"name": "contact_info", "type": "multilineText"},
    {"name": "status", "type": "singleSelect", "options": {"choices": [{"name": "active"}, {"name": "inactive"}]}},
    {"name": "notes", "type": "multilineText"}
  ]
}
```

Expected: 테이블 ID + 11개 필드 ID 반환. 메모.

- [ ] **Step 2: 테이블 생성 검증**

`mcp__claude_ai_Airtable__get_table_schema` 호출 — 11개 필드 정상 확인.

- [ ] **Step 3: Commit**

```bash
cd "c:/Users/yjisu/Desktop/SCM_WORK" && git add -A
git commit --allow-empty -m "feat(airtable): tms_3pl_partners 테이블 신규 (Sub-Spec 1 Task 3)

11개 필드 — partner_id/partner_name/partner_type/primary_role/location/autonomy_level/lock_in_reason/monthly_volume_cbm/contact_info/status/notes

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: tms_3pl_partners 초기 데이터 5건 시드

**Files:**
- Create: `scripts/seed/seed_tms_3pl_partners.py`

- [ ] **Step 1: 시드 스크립트 작성**

Create `c:/Users/yjisu/Desktop/SCM_WORK/scripts/seed/seed_tms_3pl_partners.py`:

```python
"""tms_3pl_partners 초기 데이터 시드 — 외주 5개사.

재실행 가능 (idempotent).
Source: _AutoResearch/SCM/outputs/2026-05-27-driver-lane-consolidation-strategy.md §1.2
Run: python scripts/seed/seed_tms_3pl_partners.py
"""
from __future__ import annotations
import os
import sys
import requests

BASE_ID = "app4x70a8mOrIKsMf"
TABLE_NAME = "tms_3pl_partners"

PARTNERS = [
    {
        "partner_id": "PT-0001",
        "partner_name": "다영기획",
        "partner_type": "3PL",
        "primary_role": "프로젝트 임가공 협력사",
        "location": "(확인 필요)",
        "autonomy_level": "partial",
        "lock_in_reason": "customer-designated",
        "contact_info": "",
        "status": "active",
        "notes": "임가공 후 *퀵 발송*은 박종성 기사 90% 흡수 가능 (이미 정착 패턴). *택배 발송*은 다영 자체 (고객 지정 케이스).",
    },
    {
        "partner_id": "PT-0002",
        "partner_name": "베스트원",
        "partner_type": "3PL",
        "primary_role": "재고보관 창고 (3PL 보관)",
        "location": "경기 광주시",
        "autonomy_level": "locked-in",
        "lock_in_reason": "distance",
        "contact_info": "",
        "status": "active",
        "notes": "재고 보관 창고 → 퀵·택배 본인 활용. 자체 기사 거주지(서울)에서 광주시 거리 비효율로 lock-in. 비수기 한정 박종성 시범 흡수 후보.",
    },
    {
        "partner_id": "PT-0003",
        "partner_name": "로지비",
        "partner_type": "3PL",
        "primary_role": "풀필먼트 보관·출하 협력사",
        "location": "경기 이천시",
        "autonomy_level": "locked-in",
        "lock_in_reason": "distance",
        "contact_info": "",
        "status": "active",
        "notes": "풀필먼트 프로젝트 보관 + 출하. 이천시 거리 비효율로 자체 기사 흡수 어려움.",
    },
    {
        "partner_id": "PT-0004",
        "partner_name": "로젠택배",
        "partner_type": "carrier",
        "primary_role": "전국 택배망",
        "location": "(전국)",
        "autonomy_level": "autonomous",
        "lock_in_reason": "none",
        "contact_info": "",
        "status": "active",
        "notes": "진짜 carrier. 단가 협상 가능 — Sub-Spec 4 분기 RFQ 대상.",
    },
    {
        "partner_id": "PT-0005",
        "partner_name": "고고엑스",
        "partner_type": "carrier",
        "primary_role": "spillover 즉시 퀵",
        "location": "(수도권 즉시)",
        "autonomy_level": "autonomous",
        "lock_in_reason": "none",
        "contact_info": "",
        "status": "active",
        "notes": "성수기 자체 기사 capacity 초과 시 spillover 퀵. 단가 협상 가능 — Sub-Spec 4 분기 RFQ 대상.",
    },
]


def _headers(pat: str) -> dict:
    return {"Authorization": f"Bearer {pat}", "Content-Type": "application/json"}


def _existing_partner_ids(headers: dict) -> set[str]:
    url = f"https://api.airtable.com/v0/{BASE_ID}/{TABLE_NAME}"
    params = {"fields[]": ["partner_id"], "pageSize": 100}
    out: set[str] = set()
    offset = None
    while True:
        if offset:
            params["offset"] = offset
        r = requests.get(url, headers=headers, params=params, timeout=30)
        r.raise_for_status()
        data = r.json()
        for rec in data.get("records", []):
            pid = rec.get("fields", {}).get("partner_id")
            if pid:
                out.add(pid)
        offset = data.get("offset")
        if not offset:
            break
    return out


def seed(dry_run: bool = False) -> dict:
    pat = os.environ.get("AIRTABLE_PAT")
    if not pat:
        sys.exit("ERROR: AIRTABLE_PAT 환경변수 필요")

    headers = _headers(pat)
    existing = _existing_partner_ids(headers)

    to_insert = [p for p in PARTNERS if p["partner_id"] not in existing]
    skipped = [p["partner_id"] for p in PARTNERS if p["partner_id"] in existing]

    print(f"기존: {len(existing)}건 / 신규 시드: {len(to_insert)}건 / 스킵: {len(skipped)}건")

    if dry_run:
        for p in to_insert:
            print(f"  [DRY] {p['partner_id']} {p['partner_name']}")
        return {"inserted": 0, "skipped": len(skipped), "would_insert": len(to_insert)}

    inserted = 0
    if to_insert:
        url = f"https://api.airtable.com/v0/{BASE_ID}/{TABLE_NAME}"
        payload = {"records": [{"fields": p} for p in to_insert]}
        r = requests.post(url, headers=headers, json=payload, timeout=30)
        r.raise_for_status()
        inserted = len(r.json().get("records", []))
        print(f"✅ 신규 {inserted}건 시드 완료")

    return {"inserted": inserted, "skipped": len(skipped)}


if __name__ == "__main__":
    dry = "--dry-run" in sys.argv
    result = seed(dry_run=dry)
    print(result)
```

- [ ] **Step 2: Dry-run + 실행 + 재실행 검증**

```bash
cd "c:/Users/yjisu/Desktop/SCM_WORK" && python scripts/seed/seed_tms_3pl_partners.py --dry-run
# Expected: 기존: 0 / 신규 시드: 5 / 스킵: 0

python scripts/seed/seed_tms_3pl_partners.py
# Expected: ✅ 신규 5건 시드 완료

python scripts/seed/seed_tms_3pl_partners.py
# Expected: 기존: 5 / 신규 시드: 0 / 스킵: 5
```

- [ ] **Step 3: MCP로 5건 검증**

`mcp__claude_ai_Airtable__list_records_for_table` 호출 — 5개 record 정상 반환 확인.

- [ ] **Step 4: Commit**

```bash
cd "c:/Users/yjisu/Desktop/SCM_WORK" && git add scripts/seed/seed_tms_3pl_partners.py
git commit -m "feat(seed): tms_3pl_partners 초기 5건 시드 스크립트 (Sub-Spec 1 Task 4)

다영기획(3PL, 임가공, partial-자율)
베스트원(3PL, 광주시 재고보관, distance lock-in)
로지비(3PL, 이천시 풀필먼트, distance lock-in)
로젠택배(carrier, 전국, autonomous)
고고엑스(carrier, 수도권 퀵, autonomous)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: schema_pin.json 갱신 (신규 테이블 2개 + 24개 필드 ID)

**Files:**
- Modify: `harness/_core/schema_pin.json`

- [ ] **Step 1: schema_pin.json 파일 마지막 위치 확인**

```bash
cd "c:/Users/yjisu/Desktop/SCM_WORK" && python -c "
import json
with open('harness/_core/schema_pin.json', 'r', encoding='utf-8') as f:
    data = json.load(f)
print('Tables count:', len(data['tables']))
print('Table names:', [t['name'] for t in data['tables'].values()])
"
```

Expected: 현재 17개 테이블 (배송요청·Shipment·배송파트너·Location·... etc.) 확인.

- [ ] **Step 2: Task 1·3에서 받은 테이블 ID + 필드 ID를 schema_pin.json에 추가**

`harness/_core/schema_pin.json`의 `tables` dict에 두 항목 추가 (Task 1·3 응답에서 받은 실제 ID로 `<TBL_ID>`, `<FLD_XXX>` 치환):

```json
"<TBL_drivers_ID>": {
  "name": "tms_drivers",
  "fields": {
    "<FLD_driver_id>": {"name": "driver_id", "type": "singleLineText"},
    "<FLD_name>": {"name": "name", "type": "singleLineText"},
    "<FLD_vehicle_model>": {"name": "vehicle_model", "type": "singleLineText"},
    "<FLD_cbm_capacity>": {"name": "cbm_capacity", "type": "number"},
    "<FLD_residence>": {"name": "residence", "type": "singleLineText"},
    "<FLD_work_hours_start>": {"name": "work_hours_start", "type": "singleLineText"},
    "<FLD_work_hours_end>": {"name": "work_hours_end", "type": "singleLineText"},
    "<FLD_daily_fixed_cost>": {"name": "daily_fixed_cost", "type": "currency"},
    "<FLD_max_daily_orders>": {"name": "max_daily_orders", "type": "number"},
    "<FLD_contract_type>": {"name": "contract_type", "type": "singleSelect"},
    "<FLD_wave_pattern>": {"name": "wave_pattern", "type": "singleSelect"},
    "<FLD_status>": {"name": "status", "type": "singleSelect"},
    "<FLD_notes>": {"name": "notes", "type": "multilineText"}
  }
},
"<TBL_partners_ID>": {
  "name": "tms_3pl_partners",
  "fields": {
    "<FLD_partner_id>": {"name": "partner_id", "type": "singleLineText"},
    "<FLD_partner_name>": {"name": "partner_name", "type": "singleLineText"},
    "<FLD_partner_type>": {"name": "partner_type", "type": "singleSelect"},
    "<FLD_primary_role>": {"name": "primary_role", "type": "singleLineText"},
    "<FLD_location>": {"name": "location", "type": "singleLineText"},
    "<FLD_autonomy_level>": {"name": "autonomy_level", "type": "singleSelect"},
    "<FLD_lock_in_reason>": {"name": "lock_in_reason", "type": "singleSelect"},
    "<FLD_monthly_volume_cbm>": {"name": "monthly_volume_cbm", "type": "number"},
    "<FLD_contact_info>": {"name": "contact_info", "type": "multilineText"},
    "<FLD_status>": {"name": "status", "type": "singleSelect"},
    "<FLD_notes>": {"name": "notes", "type": "multilineText"}
  }
}
```

또한 `generated_at` 필드를 `"2026-05-27T00:00:00+09:00"`로 갱신.

- [ ] **Step 3: JSON 유효성 검증**

```bash
cd "c:/Users/yjisu/Desktop/SCM_WORK" && python -c "
import json
with open('harness/_core/schema_pin.json', 'r', encoding='utf-8') as f:
    data = json.load(f)
new_tables = [t for t in data['tables'].values() if t['name'] in ('tms_drivers', 'tms_3pl_partners')]
assert len(new_tables) == 2, f'Expected 2 new tables, got {len(new_tables)}'
assert len(new_tables[0]['fields']) + len(new_tables[1]['fields']) == 24, 'Expected 24 total fields'
print('✅ schema_pin.json valid: tms_drivers + tms_3pl_partners 신규 등록 확인')
"
```

Expected: `✅ schema_pin.json valid: ...`

- [ ] **Step 4: Commit**

```bash
cd "c:/Users/yjisu/Desktop/SCM_WORK" && git add harness/_core/schema_pin.json
git commit -m "chore(schema): schema_pin.json에 tms_drivers + tms_3pl_partners 등록 (Sub-Spec 1 Task 5)

24개 필드 ID 모두 핀 (drivers 13개 + partners 11개)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: `harness/dispatch/resource_loader.py` 신규 작성 + 테스트

**Files:**
- Create: `harness/dispatch/__init__.py` (empty)
- Create: `harness/dispatch/resource_loader.py`
- Create: `tests/dispatch/__init__.py` (empty)
- Create: `tests/dispatch/test_resource_loader.py`

- [ ] **Step 1: 디렉토리 + 빈 __init__.py**

```bash
mkdir -p "c:/Users/yjisu/Desktop/SCM_WORK/harness/dispatch"
mkdir -p "c:/Users/yjisu/Desktop/SCM_WORK/tests/dispatch"
touch "c:/Users/yjisu/Desktop/SCM_WORK/harness/dispatch/__init__.py"
touch "c:/Users/yjisu/Desktop/SCM_WORK/tests/dispatch/__init__.py"
```

- [ ] **Step 2: 실패하는 테스트 작성**

Create `c:/Users/yjisu/Desktop/SCM_WORK/tests/dispatch/test_resource_loader.py`:

```python
"""Tests for harness.dispatch.resource_loader."""
from __future__ import annotations
from unittest.mock import patch, MagicMock
import pytest

from harness.dispatch.resource_loader import load_drivers, load_partners


@patch("harness.dispatch.resource_loader._fetch_records")
def test_load_drivers_returns_three(mock_fetch):
    """load_drivers()는 active 상태 driver를 dict list로 반환한다."""
    mock_fetch.return_value = [
        {"fields": {"driver_id": "CA-0002", "name": "이장훈", "status": "active"}},
        {"fields": {"driver_id": "CA-NEW-1", "name": "조희선", "status": "active"}},
        {"fields": {"driver_id": "CA-0003", "name": "박종성", "status": "active"}},
    ]
    drivers = load_drivers()
    assert len(drivers) == 3
    ids = {d["driver_id"] for d in drivers}
    assert ids == {"CA-0002", "CA-NEW-1", "CA-0003"}


@patch("harness.dispatch.resource_loader._fetch_records")
def test_load_drivers_filters_inactive(mock_fetch):
    """status=inactive driver는 제외한다."""
    mock_fetch.return_value = [
        {"fields": {"driver_id": "CA-0002", "name": "이장훈", "status": "active"}},
        {"fields": {"driver_id": "CA-0004", "name": "김민준", "status": "inactive"}},
    ]
    drivers = load_drivers()
    assert len(drivers) == 1
    assert drivers[0]["driver_id"] == "CA-0002"


@patch("harness.dispatch.resource_loader._fetch_records")
def test_load_partners_returns_five(mock_fetch):
    mock_fetch.return_value = [
        {"fields": {"partner_id": f"PT-000{i}", "partner_name": f"파트너{i}", "status": "active"}}
        for i in range(1, 6)
    ]
    partners = load_partners()
    assert len(partners) == 5


@patch("harness.dispatch.resource_loader._fetch_records")
def test_load_partners_filters_inactive(mock_fetch):
    mock_fetch.return_value = [
        {"fields": {"partner_id": "PT-0001", "partner_name": "다영기획", "status": "active"}},
        {"fields": {"partner_id": "PT-9999", "partner_name": "예전사", "status": "inactive"}},
    ]
    partners = load_partners()
    assert len(partners) == 1
    assert partners[0]["partner_name"] == "다영기획"
```

- [ ] **Step 3: 테스트 실행 (FAIL 확인)**

```bash
cd "c:/Users/yjisu/Desktop/SCM_WORK" && python -m pytest tests/dispatch/test_resource_loader.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'harness.dispatch.resource_loader'`

- [ ] **Step 4: resource_loader.py 최소 구현**

Create `c:/Users/yjisu/Desktop/SCM_WORK/harness/dispatch/resource_loader.py`:

```python
"""tms_drivers + tms_3pl_partners SSOT loader.

Source: _AutoResearch/SCM/outputs/2026-05-27-driver-lane-consolidation-strategy.md §1
Tables: TMS base app4x70a8mOrIKsMf — tms_drivers / tms_3pl_partners
"""
from __future__ import annotations
import os
from typing import Any
import requests

BASE_ID = "app4x70a8mOrIKsMf"
DRIVERS_TABLE = "tms_drivers"
PARTNERS_TABLE = "tms_3pl_partners"


def _fetch_records(table_name: str) -> list[dict[str, Any]]:
    """Airtable에서 모든 record를 가져와 raw list로 반환."""
    pat = os.environ.get("AIRTABLE_PAT")
    if not pat:
        raise RuntimeError("AIRTABLE_PAT 환경변수 필요")
    headers = {"Authorization": f"Bearer {pat}"}
    url = f"https://api.airtable.com/v0/{BASE_ID}/{table_name}"
    params: dict[str, Any] = {"pageSize": 100}
    out: list[dict[str, Any]] = []
    offset = None
    while True:
        if offset:
            params["offset"] = offset
        r = requests.get(url, headers=headers, params=params, timeout=30)
        r.raise_for_status()
        data = r.json()
        out.extend(data.get("records", []))
        offset = data.get("offset")
        if not offset:
            break
    return out


def _is_active(rec: dict[str, Any]) -> bool:
    return rec.get("fields", {}).get("status") == "active"


def load_drivers() -> list[dict[str, Any]]:
    """active 상태 driver들의 fields dict를 list로 반환."""
    records = _fetch_records(DRIVERS_TABLE)
    return [r["fields"] for r in records if _is_active(r)]


def load_partners() -> list[dict[str, Any]]:
    """active 상태 3PL/carrier들의 fields dict를 list로 반환."""
    records = _fetch_records(PARTNERS_TABLE)
    return [r["fields"] for r in records if _is_active(r)]
```

- [ ] **Step 5: 테스트 재실행 (PASS 확인)**

```bash
cd "c:/Users/yjisu/Desktop/SCM_WORK" && python -m pytest tests/dispatch/test_resource_loader.py -v
```

Expected: 4 passed

- [ ] **Step 6: 실 Airtable로 smoke test (수동)**

```bash
cd "c:/Users/yjisu/Desktop/SCM_WORK" && python -c "
from harness.dispatch.resource_loader import load_drivers, load_partners
drivers = load_drivers()
partners = load_partners()
print(f'drivers: {len(drivers)}건 — {[d[\"name\"] for d in drivers]}')
print(f'partners: {len(partners)}건 — {[p[\"partner_name\"] for p in partners]}')
assert len(drivers) == 3
assert len(partners) == 5
print('✅ 실 Airtable smoke test 통과')
"
```

Expected: `drivers: 3건 — ['이장훈', '조희선', '박종성']` + `partners: 5건 — [...]` + `✅ 실 Airtable smoke test 통과`

- [ ] **Step 7: Commit**

```bash
cd "c:/Users/yjisu/Desktop/SCM_WORK" && git add harness/dispatch/ tests/dispatch/
git commit -m "feat(dispatch): resource_loader.py — tms_drivers/tms_3pl_partners 로더 (Sub-Spec 1 Task 6)

load_drivers() / load_partners() — active 상태만 필터.
4 pytest 통과 + 실 Airtable smoke test 통과.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 7: `dispatch_advisor.py` 갱신 (CA-0004 김민준 → CA-NEW-1 조희선)

**Files:**
- Modify: `harness/virtual_sap/agents/dispatch_advisor.py:50-54`
- Create: `tests/virtual_sap/test_dispatch_advisor_roster.py`

- [ ] **Step 1: 회귀 테스트 먼저 작성**

Create `c:/Users/yjisu/Desktop/SCM_WORK/tests/virtual_sap/test_dispatch_advisor_roster.py`:

```python
"""Roster 정정 회귀 테스트 — CA-0004 김민준 제거, CA-NEW-1 조희선 추가."""
from __future__ import annotations
from harness.virtual_sap.agents.dispatch_advisor import INHOUSE_DRIVERS


def test_inhouse_drivers_count():
    """자체 기사 3명 유지."""
    assert len(INHOUSE_DRIVERS) == 3


def test_johee_sun_present():
    """조희선 기사 추가됨 (CA-NEW-1)."""
    ids = {d[0] for d in INHOUSE_DRIVERS}
    names = {d[1] for d in INHOUSE_DRIVERS}
    assert "CA-NEW-1" in ids
    assert "조희선" in names


def test_kim_min_jun_removed():
    """김민준 기사 제거됨 (CA-0004)."""
    ids = {d[0] for d in INHOUSE_DRIVERS}
    names = {d[1] for d in INHOUSE_DRIVERS}
    assert "CA-0004" not in ids
    assert "김민준" not in names


def test_existing_drivers_preserved():
    """이장훈·박종성 유지."""
    names = {d[1] for d in INHOUSE_DRIVERS}
    assert "이장훈" in names
    assert "박종성" in names
```

- [ ] **Step 2: 테스트 실행 (FAIL 확인)**

```bash
cd "c:/Users/yjisu/Desktop/SCM_WORK" && python -m pytest tests/virtual_sap/test_dispatch_advisor_roster.py -v
```

Expected: 2 FAIL (test_johee_sun_present + test_kim_min_jun_removed) — 현재 코드는 김민준 있고 조희선 없음

- [ ] **Step 3: dispatch_advisor.py line 50~57 수정**

`c:/Users/yjisu/Desktop/SCM_WORK/harness/virtual_sap/agents/dispatch_advisor.py` 의 line 49~57 부분:

**OLD:**
```python
# In-house driver config: (carrier_id, display_name, max_cbm_per_run)
INHOUSE_DRIVERS = [
    ("CA-0002", "이장훈", 7.6),
    ("CA-0003", "박종성", 7.6),
    ("CA-0004", "김민준", 7.6),
]
```

**NEW:**
```python
# In-house driver config: (carrier_id, display_name, max_cbm_per_run)
# Source of truth: Airtable tms_drivers (TMS base app4x70a8mOrIKsMf)
# 정확한 차량 spec·시간 정책은 harness.dispatch.resource_loader.load_drivers() 참조
# 2026-05-27: CA-0004 김민준 탈퇴 → CA-NEW-1 조희선 교체 (Sub-Spec 1)
INHOUSE_DRIVERS = [
    ("CA-0002", "이장훈", 4.5),   # 현대 스타리아 화물칸 (추정 — Open Decision)
    ("CA-NEW-1", "조희선", 7.6),  # 콘솔 6건 패턴
    ("CA-0003", "박종성", 7.6),   # 변동비 (개인사업자)
]
```

(주의: 이장훈 max_cbm은 7.6 → 4.5로 변경. 스타리아 추정값.)

- [ ] **Step 4: 테스트 재실행 (PASS 확인)**

```bash
cd "c:/Users/yjisu/Desktop/SCM_WORK" && python -m pytest tests/virtual_sap/test_dispatch_advisor_roster.py -v
```

Expected: 4 passed

- [ ] **Step 5: 기존 dispatch_advisor 회귀 테스트도 통과 확인 (있다면)**

```bash
cd "c:/Users/yjisu/Desktop/SCM_WORK" && python -m pytest tests/virtual_sap/ -v 2>&1 | tail -20
```

Expected: 모든 tests pass (또는 기존 test가 없으면 새 4개만 pass)

- [ ] **Step 6: Commit**

```bash
cd "c:/Users/yjisu/Desktop/SCM_WORK" && git add harness/virtual_sap/agents/dispatch_advisor.py tests/virtual_sap/
git commit -m "fix(dispatch): INHOUSE_DRIVERS — CA-0004 김민준 → CA-NEW-1 조희선 (Sub-Spec 1 Task 7)

2026-05-27 brainstorm 결과 반영. 김민준 기사 탈퇴 → 조희선 기사 교체.
이장훈 max_cbm 7.6 → 4.5 (스타리아 화물칸 추정값 — Open Decision).
4 pytest 통과.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 8: feature_list.json + Obsidian log + Validation Contract 검증

**Files:**
- Modify: `.claude/feature_list.json`
- Append: Obsidian `SCM/_AutoResearch/wiki/log.md`

- [ ] **Step 1: feature_list.json에서 SCM-LANE-SUBSPEC-1 상태 갱신**

```bash
cd "c:/Users/yjisu/Desktop/SCM_WORK" && python -c "
import json
with open('.claude/feature_list.json', 'r', encoding='utf-8') as f:
    data = json.load(f)
for task in data['tasks']:
    if task['id'] == 'SCM-LANE-SUBSPEC-1':
        task['status'] = 'done'
        task['notes'] += ' [2026-05-27 Sub-Spec 1 완료 — tms_drivers 3건 + tms_3pl_partners 5건 시드 + dispatch_advisor.py CA-0004→CA-NEW-1 갱신 + resource_loader.py 신규 + 8 pytest 통과]'
        break
data['updated_at'] = '2026-05-27'
with open('.claude/feature_list.json', 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False, indent=2)
print('✅ SCM-LANE-SUBSPEC-1 → done')
"
```

- [ ] **Step 2: Obsidian log.md 항목 추가 (MCP)**

`mcp__obsidian__obsidian_append_content` 호출:

```json
{
  "filepath": "SCM/_AutoResearch/wiki/log.md",
  "content": "\n\n## [2026-05-27] 완료 | Sub-Spec 1 — 자원 매핑 SSOT (tms_drivers + tms_3pl_partners + dispatch_advisor 갱신)\n\n- **트리거:** writing-plans → executing-plans / Plan §11.7 Sprint 1 후속\n- **산출:**\n  - Airtable tms_drivers 테이블 신규 (13 필드) + 3건 시드 (이장훈/조희선/박종성)\n  - Airtable tms_3pl_partners 테이블 신규 (11 필드) + 5건 시드 (다영/베스트원/로지비/로젠/고고엑스)\n  - schema_pin.json +2 테이블 +24 필드\n  - harness/dispatch/resource_loader.py 신규 (load_drivers / load_partners)\n  - dispatch_advisor.py 갱신 (CA-0004 김민준 → CA-NEW-1 조희선, 이장훈 max_cbm 7.6→4.5)\n  - scripts/seed/seed_tms_drivers.py + scripts/seed/seed_tms_3pl_partners.py (idempotent)\n  - 8 pytest 통과 (resource_loader 4 + dispatch_advisor_roster 4)\n- **Validation Contract:** C1~C5 모두 PASS\n- **Open Decisions 잔존:** 이장훈 스타리아 정확 CBM / 조희선·박종성 차량 spec / 베스트원 비수기 흡수 협의 / 다영 퀵 100% 협의\n- **다음:** Sub-Spec 2 (비수기 흡수 룰 + 시즌 모드)"
}
```

- [ ] **Step 3: Validation Contract C1~C5 최종 검증**

```bash
cd "c:/Users/yjisu/Desktop/SCM_WORK" && python -c "
# C1: tms_drivers 3건
# C2: tms_3pl_partners 5건
from harness.dispatch.resource_loader import load_drivers, load_partners
drivers = load_drivers()
partners = load_partners()
assert len(drivers) == 3, f'C1 FAIL: drivers={len(drivers)}'
assert len(partners) == 5, f'C2 FAIL: partners={len(partners)}'
print('✅ C1 PASS: tms_drivers 3건 확인')
print('✅ C2 PASS: tms_3pl_partners 5건 확인')

# C3: schema_pin.json
import json
with open('harness/_core/schema_pin.json', 'r', encoding='utf-8') as f:
    schema = json.load(f)
new_tables = [t for t in schema['tables'].values() if t['name'] in ('tms_drivers', 'tms_3pl_partners')]
assert len(new_tables) == 2, f'C3 FAIL: new_tables={len(new_tables)}'
total_fields = sum(len(t['fields']) for t in new_tables)
assert total_fields == 24, f'C3 FAIL: total_fields={total_fields}'
print(f'✅ C3 PASS: schema_pin.json 신규 테이블 2개 + 24 필드 등록')

# C4: resource_loader (이미 위에서 검증됨)
print('✅ C4 PASS: resource_loader 3+5 정상 반환')

# C5: dispatch_advisor INHOUSE_DRIVERS
from harness.virtual_sap.agents.dispatch_advisor import INHOUSE_DRIVERS
ids = {d[0] for d in INHOUSE_DRIVERS}
names = {d[1] for d in INHOUSE_DRIVERS}
assert 'CA-0004' not in ids and '김민준' not in names, 'C5 FAIL: 김민준 잔존'
assert 'CA-NEW-1' in ids and '조희선' in names, 'C5 FAIL: 조희선 누락'
print('✅ C5 PASS: dispatch_advisor roster 정정 확인')

print('')
print('🎉 Validation Contract C1~C5 모두 PASS — Sub-Spec 1 완료 인증')
"
```

Expected: 5개 PASS 메시지 + `🎉 ... 모두 PASS — Sub-Spec 1 완료 인증`

- [ ] **Step 4: 통합 pytest 회귀 실행**

```bash
cd "c:/Users/yjisu/Desktop/SCM_WORK" && python -m pytest tests/dispatch/ tests/virtual_sap/ -v 2>&1 | tail -15
```

Expected: 8 passed (4 dispatch + 4 virtual_sap)

- [ ] **Step 5: 최종 Commit**

```bash
cd "c:/Users/yjisu/Desktop/SCM_WORK" && git add .claude/feature_list.json
git commit -m "chore(feature-list): SCM-LANE-SUBSPEC-1 → done

Validation Contract C1~C5 PASS:
- C1: tms_drivers 3건 ✓
- C2: tms_3pl_partners 5건 ✓
- C3: schema_pin.json +2 테이블 +24 필드 ✓
- C4: resource_loader 정상 ✓
- C5: dispatch_advisor roster 정정 ✓

다음: Sub-Spec 2 (비수기 흡수 룰 + 시즌 모드)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## 종료 체크리스트 (Sub-Spec 1)

- [ ] C1~C5 5개 contract 모두 PASS
- [ ] git log 마지막 7~10 commits에 Sub-Spec 1 Task 1~8 모두 기록됨
- [ ] Obsidian log.md에 2026-05-27 완료 항목 추가됨
- [ ] feature_list.json에서 SCM-LANE-SUBSPEC-1 status = done
- [ ] Airtable UI에서 tms_drivers 3건 + tms_3pl_partners 5건 육안 확인
- [ ] Open Decisions 4건 (스타리아 CBM, 조희선/박종성 spec, 베스트원 협의, 다영 퀵 협의) 추적 중

---

## Out of Scope (Sub-Spec 1 범위 외)

- `dispatch_advisor.py`의 hardcoded INHOUSE_DRIVERS를 *resource_loader 동적 호출*로 전환 — Sub-Spec 2에서 진행
- `dispatch_advisor.py`의 region/distance/spillover logic 갱신 — Sub-Spec 2
- 통합 적재 wave 알고리즘 — Sub-Spec 3
- Carrier × 자체기사 scorecard 대시보드 — Sub-Spec 4
- KPI K-LC-1~5 자동 측정 — Sub-Spec 5
- Open Decisions 해결 (스타리아 정확 CBM 등) — 사용자 액션 대기

---

## 다음 Sub-Spec 진입 조건

Sub-Spec 1 모든 commit + Validation Contract 통과 + Obsidian log 기록 + Notion AgentOps sync 완료 후 → **Sub-Spec 2 (비수기 흡수 룰 + 시즌 모드)** brainstorming 또는 writing-plans 진입.
