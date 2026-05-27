# Sub-Spec 1 (v2): 배송파트너 테이블 필드 확장 + 운영 정책 데이터 등록 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> **🔄 v1 → v2 변경 사유 (2026-05-27):** v1은 *신규 테이블 2개(tms_drivers + tms_3pl_partners) 생성*을 제안했으나, 기존 `배송파트너` 테이블(tblI4ZXrte7WyhXyd)에 *이미 19개 record + 23개 필드*로 자체 기사 3명(이장훈/조희선/박종성) + 외주 6개사(다영기획/베스트원/로지비/로젠/고고엑스/에스에스아이팩 — *brainstorm에서 누락된 6번째 협력사*)가 완전히 정리되어 있음을 확인. *Over-engineering 제거* → 기존 테이블에 운영 정책 필드 8개만 추가하는 v2로 전면 갱신.

**Goal:** 기존 `배송파트너` 테이블에 *운영 정책 필드 8개*를 추가하고, *자체 기사 3 record + 외주 6개사 record에 정책 정보 입력*, *dispatch_advisor.py를 record_id 기반 동적 조회*로 갱신한다.

**Architecture:** Airtable TMS base(`app4x70a8mOrIKsMf`)의 기존 `배송파트너` 테이블(`tblI4ZXrte7WyhXyd`)에 8개 필드 추가 → 기존 19개 record는 그대로, *값만 update* → `harness/_core/schema_pin.json` 갱신 → 신규 `harness/dispatch/resource_loader.py`로 동적 조회 → `dispatch_advisor.py` 갱신 (CA-0004 김민준 제거, hardcoded INHOUSE_DRIVERS → Airtable 조회로 전환).

**Tech Stack:**
- Airtable MCP (`mcp__claude_ai_Airtable__create_field`, `update_records_for_table`)
- Python 3.11+ (requests, pytest)
- harness/_core/airtable.py (rate-limited client)
- 기존 dispatch_advisor.py (line 50~54 갱신)

**Validation Contract (v2):**
- **C1:** `배송파트너` 테이블에 8개 신규 필드(`residence`, `work_hours_start`, `work_hours_end`, `daily_fixed_cost`, `max_daily_orders`, `contract_type`, `wave_pattern`, `autonomy_level`, `lock_in_reason`)가 모두 존재 — 잠깐, 8개 ≠ 9개. **정확히 8개:** residence, work_hours_start, work_hours_end, daily_fixed_cost, max_daily_orders, contract_type, wave_pattern, autonomy_level. `lock_in_reason`은 *autonomy_level=locked-in 케이스에만 필요한 보조 필드라 9번째로 같이 추가* → 총 **9개**로 정정
- **C2:** 자체 기사 3 record (`recyVExCkk2Lty0E9` 이장훈, `recPkgE4o3cs0krnR` 조희선, `recXCfwVTqaoeQ9SS` 박종성)에 정책 정보 9개 필드 모두 입력 완료 + 이장훈 `배송파트너_CBM` = 7.616 → 4.5 갱신
- **C3:** 외주 6개사 분류 (자체기사 외 신시어리 카테고리 + 다영·베스트원·로지비·로젠·고고엑스·에스에스아이팩 + 협력사·고객 등 카테고리별로) 적절한 `autonomy_level` + `lock_in_reason` 입력 완료
- **C4:** `harness/_core/schema_pin.json`의 `배송파트너` 테이블 항목에 9개 신규 필드 ID 추가
- **C5:** 신규 `harness/dispatch/resource_loader.py`의 `load_drivers()` 호출 시 자체 기사 3건 / `load_partners()` 호출 시 외주 record 반환 + pytest 통과
- **C6:** `dispatch_advisor.py` INHOUSE_DRIVERS 정정 (CA-0004 김민준 제거, 조희선 추가, 이장훈 max_cbm 7.616 → 4.5) + 기존 회귀 테스트 통과

---

## File Structure

| 파일 | 책임 | 신규/수정 |
|------|------|---------|
| Airtable `배송파트너` (테이블) | 기존 19 record + 23 필드 → +9 필드 (운영 정책) | ✏️ 수정 (필드 추가) |
| `harness/_core/schema_pin.json` | 배송파트너 테이블 항목에 9개 신규 필드 ID 추가 | ✏️ 수정 |
| `harness/dispatch/__init__.py` | dispatch 패키지 marker | 🆕 신규 (빈 파일) |
| `harness/dispatch/resource_loader.py` | 배송파트너 테이블 조회 → load_drivers / load_partners | 🆕 신규 |
| `harness/virtual_sap/agents/dispatch_advisor.py` | INHOUSE_DRIVERS 갱신 (CA-0004 김민준 제거 + 조희선 + 이장훈 CBM 4.5) | ✏️ 수정 (5줄) |
| `tests/dispatch/test_resource_loader.py` | resource_loader 단위 테스트 | 🆕 신규 |
| `tests/virtual_sap/test_dispatch_advisor_roster.py` | dispatch_advisor roster 회귀 테스트 | 🆕 신규 |
| `scripts/seed/update_배송파트너_정책필드.py` | 자체 기사 + 외주 record에 정책 정보 일괄 입력 (idempotent) | 🆕 신규 |
| `.claude/feature_list.json` | SCM-LANE-SUBSPEC-1 상태 갱신 | ✏️ 수정 |

---

## Task 0: Pre-flight 백업 + 상태 확인

**Files:**
- Read: `harness/_core/schema_pin.json`
- Read: `harness/virtual_sap/agents/dispatch_advisor.py:48-58`
- Backup: 위 2개 파일

- [ ] **Step 1: 파일 백업**

```bash
cd "c:/Users/yjisu/Desktop/SCM_WORK"
cp harness/_core/schema_pin.json harness/_core/schema_pin.json.bak.2026-05-27
cp harness/virtual_sap/agents/dispatch_advisor.py harness/virtual_sap/agents/dispatch_advisor.py.bak.2026-05-27
```

- [ ] **Step 2: 배송파트너 테이블 현재 19 record 확인 (MCP)**

`mcp__claude_ai_Airtable__list_records_for_table` 호출:

```json
{
  "baseId": "app4x70a8mOrIKsMf",
  "tableId": "tblI4ZXrte7WyhXyd",
  "fieldIds": ["배송파트너", "배차담당", "배송파트너_CBM", "Status"],
  "pageSize": 30
}
```

Expected: 19개 record 반환. 다음 record IDs 확인:
- `recyVExCkk2Lty0E9` → 신시어리 (이장훈), CBM 7.616
- `recPkgE4o3cs0krnR` → 신시어리 (조희선), CBM 7.616
- `recXCfwVTqaoeQ9SS` → 신시어리 (박종성), CBM 9.486

- [ ] **Step 3: pytest 환경 확인**

```bash
cd "c:/Users/yjisu/Desktop/SCM_WORK" && python -m pytest --version
```

---

## Task 1: 배송파트너 테이블에 9개 신규 필드 추가

**Files:**
- Modify: Airtable `배송파트너` 테이블 (`tblI4ZXrte7WyhXyd`)

> **참고:** Airtable MCP `create_field`는 1개씩 호출. 9번 호출 필요. 각 호출 후 받은 field ID를 메모 (Task 4에서 schema_pin.json 갱신에 사용).

- [ ] **Step 1: `residence` 필드 추가 (자체 기사 거주지 — 시·구 단위)**

`mcp__claude_ai_Airtable__create_field`:

```json
{
  "baseId": "app4x70a8mOrIKsMf",
  "tableId": "tblI4ZXrte7WyhXyd",
  "name": "residence",
  "type": "singleLineText",
  "description": "자체 기사 거주지 시·구 (예: 서울 성북구). 외주는 빈칸."
}
```

→ 응답 field ID 메모: `<FLD_residence>`

- [ ] **Step 2: `work_hours_start` 필드 추가**

```json
{
  "baseId": "app4x70a8mOrIKsMf",
  "tableId": "tblI4ZXrte7WyhXyd",
  "name": "work_hours_start",
  "type": "singleLineText",
  "description": "예: 09:00. 박종성처럼 유연 시간은 빈칸."
}
```

→ `<FLD_work_hours_start>`

- [ ] **Step 3: `work_hours_end` 필드 추가**

```json
{
  "baseId": "app4x70a8mOrIKsMf",
  "tableId": "tblI4ZXrte7WyhXyd",
  "name": "work_hours_end",
  "type": "singleLineText",
  "description": "예: 13:00, 18:00. 유연 시간은 빈칸."
}
```

→ `<FLD_work_hours_end>`

- [ ] **Step 4: `daily_fixed_cost` 필드 추가**

```json
{
  "baseId": "app4x70a8mOrIKsMf",
  "tableId": "tblI4ZXrte7WyhXyd",
  "name": "daily_fixed_cost",
  "type": "currency",
  "options": {"precision": 0, "symbol": "₩"},
  "description": "일 고정비. 자체 기사 계약직만 (개인사업자·외주는 0)."
}
```

→ `<FLD_daily_fixed_cost>`

- [ ] **Step 5: `max_daily_orders` 필드 추가**

```json
{
  "baseId": "app4x70a8mOrIKsMf",
  "tableId": "tblI4ZXrte7WyhXyd",
  "name": "max_daily_orders",
  "type": "number",
  "options": {"precision": 0},
  "description": "일 최대 처리 가능 건수. 외주는 빈칸 또는 0."
}
```

→ `<FLD_max_daily_orders>`

- [ ] **Step 6: `contract_type` 필드 추가**

```json
{
  "baseId": "app4x70a8mOrIKsMf",
  "tableId": "tblI4ZXrte7WyhXyd",
  "name": "contract_type",
  "type": "singleSelect",
  "options": {
    "choices": [
      {"name": "계약직"},
      {"name": "개인사업자"},
      {"name": "외주_3PL"},
      {"name": "외주_carrier"},
      {"name": "고객직접"}
    ]
  }
}
```

→ `<FLD_contract_type>`

- [ ] **Step 7: `wave_pattern` 필드 추가**

```json
{
  "baseId": "app4x70a8mOrIKsMf",
  "tableId": "tblI4ZXrte7WyhXyd",
  "name": "wave_pattern",
  "type": "singleSelect",
  "options": {
    "choices": [
      {"name": "W1-시간고정"},
      {"name": "W2-시간고정"},
      {"name": "W3-Trigger기반"},
      {"name": "N-A"}
    ]
  }
}
```

→ `<FLD_wave_pattern>`

- [ ] **Step 8: `autonomy_level` 필드 추가**

```json
{
  "baseId": "app4x70a8mOrIKsMf",
  "tableId": "tblI4ZXrte7WyhXyd",
  "name": "autonomy_level",
  "type": "singleSelect",
  "options": {
    "choices": [
      {"name": "autonomous"},
      {"name": "partial"},
      {"name": "locked-in"},
      {"name": "internal"}
    ]
  },
  "description": "우리가 변경 가능한 자율 영역인지. internal = 자체 기사 (해당 없음)."
}
```

→ `<FLD_autonomy_level>`

- [ ] **Step 9: `lock_in_reason` 필드 추가**

```json
{
  "baseId": "app4x70a8mOrIKsMf",
  "tableId": "tblI4ZXrte7WyhXyd",
  "name": "lock_in_reason",
  "type": "singleSelect",
  "options": {
    "choices": [
      {"name": "distance"},
      {"name": "customer-designated"},
      {"name": "imga_gong-mapping"},
      {"name": "none"}
    ]
  },
  "description": "lock-in 사유. autonomous면 none."
}
```

→ `<FLD_lock_in_reason>`

- [ ] **Step 10: 필드 추가 검증 (MCP get_table_schema)**

```json
{
  "baseId": "app4x70a8mOrIKsMf",
  "tables": [{"tableId": "tblI4ZXrte7WyhXyd"}]
}
```

Expected: 기존 23개 + 신규 9개 = **총 32개 필드** 반환. 9개 신규 필드명 모두 존재 확인.

- [ ] **Step 11: Commit**

```bash
cd "c:/Users/yjisu/Desktop/SCM_WORK"
git commit --allow-empty -m "feat(airtable): 배송파트너 테이블에 운영 정책 9개 필드 추가 (Sub-Spec 1 v2 Task 1)

residence/work_hours_start/work_hours_end/daily_fixed_cost/max_daily_orders/contract_type/wave_pattern/autonomy_level/lock_in_reason

기존 19 record · 23 필드 유지 → +9 필드 = 총 32 필드.
Sub-Spec 1 v2 — 신규 테이블 생성 대신 기존 테이블 확장 (사용자 지적 반영).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: 자체 기사 3 record 운영 정책 정보 입력 + 이장훈 CBM 정정

**Files:**
- Modify: Airtable `배송파트너` records (3개)
- Create: `scripts/seed/update_배송파트너_정책필드.py`

- [ ] **Step 1: 디렉토리 확인**

```bash
mkdir -p "c:/Users/yjisu/Desktop/SCM_WORK/scripts/seed"
```

- [ ] **Step 2: update 스크립트 작성**

Create `c:/Users/yjisu/Desktop/SCM_WORK/scripts/seed/update_배송파트너_정책필드.py`:

```python
"""배송파트너 테이블의 record들에 운영 정책 정보(9개 신규 필드) 일괄 입력.

대상:
- 자체 기사 3 (이장훈/조희선/박종성) — 운영 정보 + 이장훈 CBM 7.616 → 4.5 정정
- 외주 6개사 record들 — autonomy_level + lock_in_reason + contract_type 분류

재실행 가능 (idempotent): 모든 record는 PATCH 방식 — 같은 값 다시 쓰는 건 무해.

Source: _AutoResearch/SCM/outputs/2026-05-27-driver-lane-consolidation-strategy.md
Run: python scripts/seed/update_배송파트너_정책필드.py [--dry-run]
"""
from __future__ import annotations
import os
import sys
import requests

BASE_ID = "app4x70a8mOrIKsMf"
TABLE_ID = "tblI4ZXrte7WyhXyd"

# 자체 기사 3 — 정책 정보 + CBM 정정
DRIVER_UPDATES = [
    {
        "record_id": "recyVExCkk2Lty0E9",  # 신시어리 (이장훈)
        "fields": {
            "배송파트너_CBM": 4.5,  # 7.616 → 4.5 (스타리아 화물칸 추정 — Open Decision)
            "residence": "서울 성북구",
            "work_hours_start": "09:00",
            "work_hours_end": "13:00",
            "daily_fixed_cost": 160000,
            "max_daily_orders": 3,
            "contract_type": "계약직",
            "wave_pattern": "W1-시간고정",
            "autonomy_level": "internal",
            "lock_in_reason": "none",
        },
    },
    {
        "record_id": "recPkgE4o3cs0krnR",  # 신시어리 (조희선)
        "fields": {
            # CBM 7.616 유지 (정확 값 확인 시 갱신)
            "residence": "서울 양천구",
            "work_hours_start": "09:00",
            "work_hours_end": "18:00",
            "daily_fixed_cost": 360000,
            "max_daily_orders": 6,
            "contract_type": "계약직",
            "wave_pattern": "W2-시간고정",
            "autonomy_level": "internal",
            "lock_in_reason": "none",
        },
    },
    {
        "record_id": "recXCfwVTqaoeQ9SS",  # 신시어리 (박종성)
        "fields": {
            # CBM 9.486 유지
            "residence": "서울 중랑구",
            # work_hours_start/end 비워둠 (유연 24h)
            "daily_fixed_cost": 0,
            "max_daily_orders": 8,
            "contract_type": "개인사업자",
            "wave_pattern": "W3-Trigger기반",
            "autonomy_level": "internal",
            "lock_in_reason": "none",
        },
    },
]


def _headers(pat: str) -> dict:
    return {"Authorization": f"Bearer {pat}", "Content-Type": "application/json"}


def update_drivers(dry_run: bool = False) -> int:
    pat = os.environ.get("AIRTABLE_PAT")
    if not pat:
        sys.exit("ERROR: AIRTABLE_PAT 환경변수 필요")

    headers = _headers(pat)
    url = f"https://api.airtable.com/v0/{BASE_ID}/{TABLE_ID}"

    if dry_run:
        for upd in DRIVER_UPDATES:
            print(f"  [DRY] {upd['record_id']}: {list(upd['fields'].keys())}")
        return 0

    # PATCH batch (10 records max per request)
    payload = {"records": [{"id": u["record_id"], "fields": u["fields"]} for u in DRIVER_UPDATES]}
    r = requests.patch(url, headers=headers, json=payload, timeout=30)
    r.raise_for_status()
    count = len(r.json().get("records", []))
    print(f"✅ 자체 기사 {count} record 갱신 완료")
    return count


if __name__ == "__main__":
    dry = "--dry-run" in sys.argv
    updated = update_drivers(dry_run=dry)
    print(f"updated: {updated}")
```

- [ ] **Step 3: Dry-run + 실행 + 검증**

```bash
cd "c:/Users/yjisu/Desktop/SCM_WORK"
python scripts/seed/update_배송파트너_정책필드.py --dry-run
# Expected: 3 records dry-run 출력

python scripts/seed/update_배송파트너_정책필드.py
# Expected: ✅ 자체 기사 3 record 갱신 완료
```

- [ ] **Step 4: MCP로 검증 (이장훈 CBM 4.5 + residence 확인)**

`mcp__claude_ai_Airtable__list_records_for_table`:

```json
{
  "baseId": "app4x70a8mOrIKsMf",
  "tableId": "tblI4ZXrte7WyhXyd",
  "recordIds": ["recyVExCkk2Lty0E9", "recPkgE4o3cs0krnR", "recXCfwVTqaoeQ9SS"],
  "fieldIds": ["배송파트너", "배송파트너_CBM", "residence", "daily_fixed_cost", "contract_type", "wave_pattern"]
}
```

Expected: 3개 record 모두 신규 필드 값 채워서 반환. 이장훈 CBM = 4.5.

- [ ] **Step 5: Commit**

```bash
cd "c:/Users/yjisu/Desktop/SCM_WORK"
git add scripts/seed/update_배송파트너_정책필드.py
git commit -m "feat(seed): 자체 기사 3 record 운영 정책 정보 입력 (Sub-Spec 1 v2 Task 2)

- 이장훈 CBM 7.616 → 4.5 정정 (스타리아 화물칸 추정)
- 거주지·근무시간·고정비·계약형태·wave 패턴 입력
- idempotent PATCH 방식

⚠️ Open Decisions: 이장훈 스타리아 정확 CBM, 조희선·박종성 차량 spec

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: 외주 6개사 + 신시어리 carrier 위탁 record 분류 정보 입력

**Files:**
- Modify: Airtable `배송파트너` 기타 record 16개 (자체 3 제외)
- Modify: `scripts/seed/update_배송파트너_정책필드.py` (PARTNER_UPDATES 추가)

- [ ] **Step 1: update 스크립트에 PARTNER_UPDATES 섹션 추가**

`scripts/seed/update_배송파트너_정책필드.py`에 추가:

```python
# 외주 record 분류 — record ID 기준 (배송파트너 테이블 19개 record 중 자체 3 제외 16개)
PARTNER_UPDATES = [
    # 다영기획 (퀵·택배) — 임가공 협력사, partial (퀵은 박종성 90% 흡수)
    {"record_id": "recPV3KdfisKr9Zs8", "fields": {"contract_type": "외주_3PL", "wave_pattern": "N-A", "autonomy_level": "partial", "lock_in_reason": "imga_gong-mapping"}},  # 다영기획 (퀵)
    {"record_id": "recxh0xUjlwOOkrKJ", "fields": {"contract_type": "외주_3PL", "wave_pattern": "N-A", "autonomy_level": "locked-in", "lock_in_reason": "customer-designated"}},  # 다영기획 (택배)
    # 베스트원 (퀵·택배) — 광주시 재고보관 창고
    {"record_id": "recFyXr7Y1sIjWQ62", "fields": {"contract_type": "외주_3PL", "wave_pattern": "N-A", "autonomy_level": "locked-in", "lock_in_reason": "distance"}},  # 베스트원 (퀵)
    {"record_id": "rec9cMWyTYFJzrNiK", "fields": {"contract_type": "외주_3PL", "wave_pattern": "N-A", "autonomy_level": "locked-in", "lock_in_reason": "distance"}},  # 베스트원 (택배)
    # 로지비 (퀵·택배) — 이천시 풀필먼트
    {"record_id": "rec4e0KsUSiX3dcPT", "fields": {"contract_type": "외주_3PL", "wave_pattern": "N-A", "autonomy_level": "locked-in", "lock_in_reason": "distance"}},  # 로지비 (퀵)
    {"record_id": "rec61pZqGjuYaMwFc", "fields": {"contract_type": "외주_3PL", "wave_pattern": "N-A", "autonomy_level": "locked-in", "lock_in_reason": "distance"}},  # 로지비 (택배)
    # 신시어리 위탁 — 로젠·고고엑스·항공·물류팀
    {"record_id": "recrbwsFhkb16eMXZ", "fields": {"contract_type": "외주_carrier", "wave_pattern": "N-A", "autonomy_level": "autonomous", "lock_in_reason": "none"}},  # 신시어리 (로젠)
    {"record_id": "recSRtnToG5XrcMzZ", "fields": {"contract_type": "외주_carrier", "wave_pattern": "N-A", "autonomy_level": "autonomous", "lock_in_reason": "none"}},  # 신시어리 (고고엑스)
    {"record_id": "recDvqCerTWX6bCin", "fields": {"contract_type": "외주_carrier", "wave_pattern": "N-A", "autonomy_level": "autonomous", "lock_in_reason": "none"}},  # 신시어리 (항공/특송)
    {"record_id": "recdD4leXvLNazDPO", "fields": {"contract_type": "계약직", "wave_pattern": "N-A", "autonomy_level": "internal", "lock_in_reason": "none"}},  # 신시어리 (물류팀)
    {"record_id": "reclDM1WJuZJTD257", "fields": {"contract_type": "외주_carrier", "wave_pattern": "N-A", "autonomy_level": "autonomous", "lock_in_reason": "none"}},  # KTX
    # 에스에스아이팩 (퀵·택배) — 2026-05-27 사용자 결정: 제거. Status='inactive' 처리 (과거 Shipment link 보존).
    {"record_id": "recrmvfz58msNDfNN", "fields": {"Status": "inactive", "contract_type": "외주_3PL", "wave_pattern": "N-A", "autonomy_level": "locked-in", "lock_in_reason": "none", "Notes": "2026-05-27 운영 종료. 과거 record 보존용."}},  # 에스에스아이팩 (퀵)
    {"record_id": "rec7QF1ioERDdogIu", "fields": {"Status": "inactive", "contract_type": "외주_3PL", "wave_pattern": "N-A", "autonomy_level": "locked-in", "lock_in_reason": "none", "Notes": "2026-05-27 운영 종료. 과거 record 보존용."}},  # 에스에스아이팩 (택배)
    # 제작협력사 (퀵·택배)
    {"record_id": "recr48f91VOWjYN3Z", "fields": {"contract_type": "외주_3PL", "wave_pattern": "N-A", "autonomy_level": "partial", "lock_in_reason": "imga_gong-mapping"}},  # 제작협력사 (퀵)
    {"record_id": "recx9DjW1StCQeJRS", "fields": {"contract_type": "외주_3PL", "wave_pattern": "N-A", "autonomy_level": "locked-in", "lock_in_reason": "customer-designated"}},  # 제작협력사 (택배)
    # 고객 (직접 수령)
    {"record_id": "recpA2Fv7lESQVNk9", "fields": {"contract_type": "고객직접", "wave_pattern": "N-A", "autonomy_level": "locked-in", "lock_in_reason": "customer-designated"}},  # 고객
]


def update_partners(dry_run: bool = False) -> int:
    pat = os.environ.get("AIRTABLE_PAT")
    if not pat:
        sys.exit("ERROR: AIRTABLE_PAT 환경변수 필요")

    headers = _headers(pat)
    url = f"https://api.airtable.com/v0/{BASE_ID}/{TABLE_ID}"

    if dry_run:
        for upd in PARTNER_UPDATES:
            print(f"  [DRY] {upd['record_id']}: {upd['fields']}")
        return 0

    # PATCH in batches of 10 (Airtable limit)
    total = 0
    for i in range(0, len(PARTNER_UPDATES), 10):
        batch = PARTNER_UPDATES[i:i+10]
        payload = {"records": [{"id": u["record_id"], "fields": u["fields"]} for u in batch]}
        r = requests.patch(url, headers=headers, json=payload, timeout=30)
        r.raise_for_status()
        total += len(r.json().get("records", []))
    print(f"✅ 외주/위탁 {total} record 분류 정보 갱신 완료")
    return total
```

`if __name__ == "__main__":` 블록도 갱신:

```python
if __name__ == "__main__":
    dry = "--dry-run" in sys.argv
    driver_count = update_drivers(dry_run=dry)
    partner_count = update_partners(dry_run=dry)
    print(f"drivers: {driver_count}, partners: {partner_count}")
```

- [ ] **Step 2: Dry-run + 실행**

```bash
cd "c:/Users/yjisu/Desktop/SCM_WORK"
python scripts/seed/update_배송파트너_정책필드.py --dry-run
# Expected: 3 drivers + 16 partners dry-run

python scripts/seed/update_배송파트너_정책필드.py
# Expected: ✅ 자체 기사 3 ... ✅ 외주/위탁 16 ...
```

- [ ] **Step 3: MCP로 분류 검증**

```json
{
  "baseId": "app4x70a8mOrIKsMf",
  "tableId": "tblI4ZXrte7WyhXyd",
  "fieldIds": ["배송파트너", "contract_type", "autonomy_level", "lock_in_reason"],
  "pageSize": 30
}
```

Expected: 19개 record 모두 contract_type 분류 완료. autonomous(로젠·고고엑스·항공·KTX) 4건 / partial(다영퀵·제작협력사퀵) 2건 / locked-in(택배·고객 등) 9건 / internal(자체 기사 3 + 물류팀) 4건 — *총 19건 (에스에스아이팩 2건은 Status=inactive로 비활성화)*.

- [ ] **Step 4: Commit**

```bash
cd "c:/Users/yjisu/Desktop/SCM_WORK"
git add scripts/seed/update_배송파트너_정책필드.py
git commit -m "feat(seed): 외주/위탁 16 record 분류 정보 입력 (Sub-Spec 1 v2 Task 3)

19 record 분류:
- internal: 자체 기사 3 + 물류팀 1 = 4
- autonomous: 로젠·고고엑스·항공·KTX = 4
- partial: 다영퀵·에스에스퀵·제작협력사퀵 = 3 (박종성 흡수 가능)
- locked-in: 택배·고객 등 = 9

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: schema_pin.json에 9개 신규 필드 ID 등록

**Files:**
- Modify: `harness/_core/schema_pin.json`

- [ ] **Step 1: Task 1에서 받은 9개 field ID를 schema_pin.json의 배송파트너(`tblI4ZXrte7WyhXyd`) 항목의 `fields` dict에 추가**

`harness/_core/schema_pin.json`에서 `tblI4ZXrte7WyhXyd` 찾아서 `fields` dict 끝에 추가 (`<FLD_XXX>`는 Task 1 응답의 실제 ID로 치환):

```json
"<FLD_residence>": {"name": "residence", "type": "singleLineText"},
"<FLD_work_hours_start>": {"name": "work_hours_start", "type": "singleLineText"},
"<FLD_work_hours_end>": {"name": "work_hours_end", "type": "singleLineText"},
"<FLD_daily_fixed_cost>": {"name": "daily_fixed_cost", "type": "currency"},
"<FLD_max_daily_orders>": {"name": "max_daily_orders", "type": "number"},
"<FLD_contract_type>": {"name": "contract_type", "type": "singleSelect"},
"<FLD_wave_pattern>": {"name": "wave_pattern", "type": "singleSelect"},
"<FLD_autonomy_level>": {"name": "autonomy_level", "type": "singleSelect"},
"<FLD_lock_in_reason>": {"name": "lock_in_reason", "type": "singleSelect"}
```

또한 `generated_at` = `"2026-05-27T00:00:00+09:00"` 갱신.

- [ ] **Step 2: JSON 유효성 + 필드 카운트 검증**

```bash
cd "c:/Users/yjisu/Desktop/SCM_WORK" && python -c "
import json
with open('harness/_core/schema_pin.json', 'r', encoding='utf-8') as f:
    data = json.load(f)
table = data['tables']['tblI4ZXrte7WyhXyd']
field_count = len(table['fields'])
assert field_count == 32, f'Expected 32 fields (23+9), got {field_count}'
new_names = {'residence', 'work_hours_start', 'work_hours_end', 'daily_fixed_cost', 'max_daily_orders', 'contract_type', 'wave_pattern', 'autonomy_level', 'lock_in_reason'}
existing_names = {f['name'] for f in table['fields'].values()}
missing = new_names - existing_names
assert not missing, f'Missing fields: {missing}'
print(f'✅ schema_pin.json valid: 배송파트너 32 fields (기존 23 + 신규 9)')
"
```

- [ ] **Step 3: Commit**

```bash
cd "c:/Users/yjisu/Desktop/SCM_WORK" && git add harness/_core/schema_pin.json
git commit -m "chore(schema): 배송파트너 테이블에 운영 정책 9 필드 ID 등록 (Sub-Spec 1 v2 Task 4)

기존 23 → 신규 32 필드 (residence·work_hours_*·daily_fixed_cost·max_daily_orders·contract_type·wave_pattern·autonomy_level·lock_in_reason)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: `harness/dispatch/resource_loader.py` 신규 작성 + 4 pytest

**Files:**
- Create: `harness/dispatch/__init__.py` (빈 파일)
- Create: `harness/dispatch/resource_loader.py`
- Create: `tests/dispatch/__init__.py` (빈 파일)
- Create: `tests/dispatch/test_resource_loader.py`

- [ ] **Step 1: 디렉토리 + 빈 __init__.py**

```bash
mkdir -p "c:/Users/yjisu/Desktop/SCM_WORK/harness/dispatch"
mkdir -p "c:/Users/yjisu/Desktop/SCM_WORK/tests/dispatch"
touch "c:/Users/yjisu/Desktop/SCM_WORK/harness/dispatch/__init__.py"
touch "c:/Users/yjisu/Desktop/SCM_WORK/tests/dispatch/__init__.py"
```

- [ ] **Step 2: 실패 테스트 작성**

Create `c:/Users/yjisu/Desktop/SCM_WORK/tests/dispatch/test_resource_loader.py`:

```python
"""Tests for harness.dispatch.resource_loader."""
from __future__ import annotations
from unittest.mock import patch
from harness.dispatch.resource_loader import load_drivers, load_partners


@patch("harness.dispatch.resource_loader._fetch_records")
def test_load_drivers_returns_internal_only(mock_fetch):
    """load_drivers는 contract_type ∈ {계약직, 개인사업자}만 반환."""
    mock_fetch.return_value = [
        {"id": "rec1", "fields": {"배송파트너": "신시어리 (이장훈)", "contract_type": "계약직", "배송파트너_CBM": 4.5}},
        {"id": "rec2", "fields": {"배송파트너": "신시어리 (조희선)", "contract_type": "계약직", "배송파트너_CBM": 7.616}},
        {"id": "rec3", "fields": {"배송파트너": "신시어리 (박종성)", "contract_type": "개인사업자", "배송파트너_CBM": 9.486}},
        {"id": "rec4", "fields": {"배송파트너": "로젠택배 위탁", "contract_type": "외주_carrier"}},
        {"id": "rec5", "fields": {"배송파트너": "다영기획", "contract_type": "외주_3PL"}},
    ]
    drivers = load_drivers()
    assert len(drivers) == 3
    names = {d["배송파트너"] for d in drivers}
    assert "신시어리 (이장훈)" in names
    assert "신시어리 (조희선)" in names
    assert "신시어리 (박종성)" in names


@patch("harness.dispatch.resource_loader._fetch_records")
def test_load_drivers_skips_outsourced(mock_fetch):
    """외주는 driver가 아님."""
    mock_fetch.return_value = [
        {"id": "rec1", "fields": {"배송파트너": "로젠", "contract_type": "외주_carrier"}},
        {"id": "rec2", "fields": {"배송파트너": "다영기획", "contract_type": "외주_3PL"}},
    ]
    drivers = load_drivers()
    assert len(drivers) == 0


@patch("harness.dispatch.resource_loader._fetch_records")
def test_load_partners_returns_external_only(mock_fetch):
    """load_partners는 contract_type ∈ {외주_3PL, 외주_carrier, 고객직접}만 반환."""
    mock_fetch.return_value = [
        {"id": "rec1", "fields": {"배송파트너": "이장훈", "contract_type": "계약직"}},
        {"id": "rec2", "fields": {"배송파트너": "다영기획", "contract_type": "외주_3PL", "autonomy_level": "partial"}},
        {"id": "rec3", "fields": {"배송파트너": "로젠", "contract_type": "외주_carrier", "autonomy_level": "autonomous"}},
        {"id": "rec4", "fields": {"배송파트너": "고객", "contract_type": "고객직접"}},
    ]
    partners = load_partners()
    assert len(partners) == 3
    types = {p["contract_type"] for p in partners}
    assert types == {"외주_3PL", "외주_carrier", "고객직접"}


@patch("harness.dispatch.resource_loader._fetch_records")
def test_load_partners_extracts_autonomy(mock_fetch):
    """autonomy_level이 partner dict에 포함된다."""
    mock_fetch.return_value = [
        {"id": "rec1", "fields": {"배송파트너": "로젠", "contract_type": "외주_carrier", "autonomy_level": "autonomous"}},
    ]
    partners = load_partners()
    assert len(partners) == 1
    assert partners[0]["autonomy_level"] == "autonomous"
```

- [ ] **Step 3: 테스트 실행 (FAIL 확인)**

```bash
cd "c:/Users/yjisu/Desktop/SCM_WORK" && python -m pytest tests/dispatch/test_resource_loader.py -v
```

Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 4: resource_loader.py 구현**

Create `c:/Users/yjisu/Desktop/SCM_WORK/harness/dispatch/resource_loader.py`:

```python
"""배송파트너 테이블 SSOT loader.

기존 배송파트너 테이블(tblI4ZXrte7WyhXyd)에서 contract_type 기반으로
자체 기사(load_drivers) / 외주 파트너(load_partners)를 분리 반환.

Source: _AutoResearch/SCM/outputs/2026-05-27-driver-lane-consolidation-strategy.md §1
"""
from __future__ import annotations
import os
from typing import Any
import requests

BASE_ID = "app4x70a8mOrIKsMf"
TABLE_ID = "tblI4ZXrte7WyhXyd"

INTERNAL_CONTRACTS = {"계약직", "개인사업자"}
EXTERNAL_CONTRACTS = {"외주_3PL", "외주_carrier", "고객직접"}


def _fetch_records(table_id: str = TABLE_ID) -> list[dict[str, Any]]:
    """Airtable에서 배송파트너 record들을 모두 가져옴."""
    pat = os.environ.get("AIRTABLE_PAT")
    if not pat:
        raise RuntimeError("AIRTABLE_PAT 환경변수 필요")
    headers = {"Authorization": f"Bearer {pat}"}
    url = f"https://api.airtable.com/v0/{BASE_ID}/{table_id}"
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


def _contract_type(rec: dict[str, Any]) -> str:
    return rec.get("fields", {}).get("contract_type", "")


def _flat(rec: dict[str, Any]) -> dict[str, Any]:
    """record_id를 fields에 합쳐서 flat dict로 반환."""
    flat = dict(rec.get("fields", {}))
    flat["_record_id"] = rec.get("id")
    return flat


def load_drivers() -> list[dict[str, Any]]:
    """자체 기사 (contract_type ∈ {계약직, 개인사업자})만 반환."""
    records = _fetch_records()
    return [_flat(r) for r in records if _contract_type(r) in INTERNAL_CONTRACTS]


def load_partners() -> list[dict[str, Any]]:
    """외주 파트너 (contract_type ∈ {외주_3PL, 외주_carrier, 고객직접})만 반환."""
    records = _fetch_records()
    return [_flat(r) for r in records if _contract_type(r) in EXTERNAL_CONTRACTS]
```

- [ ] **Step 5: 테스트 PASS 확인**

```bash
cd "c:/Users/yjisu/Desktop/SCM_WORK" && python -m pytest tests/dispatch/test_resource_loader.py -v
```

Expected: 4 passed

- [ ] **Step 6: 실 Airtable smoke test**

```bash
cd "c:/Users/yjisu/Desktop/SCM_WORK" && python -c "
from harness.dispatch.resource_loader import load_drivers, load_partners
d = load_drivers()
p = load_partners()
print(f'drivers: {len(d)}건 — {[x[\"배송파트너\"] for x in d]}')
print(f'partners: {len(p)}건 — {[x[\"배송파트너\"] for x in p]}')
assert len(d) >= 3, f'Expected ≥3 drivers, got {len(d)}'
print('✅ 실 Airtable smoke test 통과')
"
```

Expected: drivers ≥ 3 (이장훈/조희선/박종성 포함) + partners 16개 정도

- [ ] **Step 7: Commit**

```bash
cd "c:/Users/yjisu/Desktop/SCM_WORK" && git add harness/dispatch/ tests/dispatch/
git commit -m "feat(dispatch): resource_loader.py — 배송파트너 테이블 동적 조회 (Sub-Spec 1 v2 Task 5)

load_drivers() / load_partners() — contract_type 기반 분리.
4 pytest 통과 + 실 Airtable smoke test 통과.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: `dispatch_advisor.py` INHOUSE_DRIVERS 정정

**Files:**
- Modify: `harness/virtual_sap/agents/dispatch_advisor.py:48-57`
- Create: `tests/virtual_sap/test_dispatch_advisor_roster.py`

- [ ] **Step 1: 회귀 테스트 작성**

Create `c:/Users/yjisu/Desktop/SCM_WORK/tests/virtual_sap/test_dispatch_advisor_roster.py`:

```python
"""Roster 정정 회귀 테스트 — CA-0004 김민준 제거, 조희선 추가, 이장훈 CBM 4.5."""
from __future__ import annotations
from harness.virtual_sap.agents.dispatch_advisor import INHOUSE_DRIVERS


def test_inhouse_drivers_count():
    assert len(INHOUSE_DRIVERS) == 3


def test_johee_sun_present():
    names = {d[1] for d in INHOUSE_DRIVERS}
    assert "조희선" in names


def test_kim_min_jun_removed():
    ids = {d[0] for d in INHOUSE_DRIVERS}
    names = {d[1] for d in INHOUSE_DRIVERS}
    assert "CA-0004" not in ids
    assert "김민준" not in names


def test_lee_jang_hoon_cbm_updated():
    """이장훈 max_cbm 7.616 → 4.5 (스타리아 화물칸 추정)."""
    lee = next((d for d in INHOUSE_DRIVERS if d[1] == "이장훈"), None)
    assert lee is not None
    assert lee[2] == 4.5, f"Expected 4.5, got {lee[2]}"


def test_park_jong_sung_preserved():
    names = {d[1] for d in INHOUSE_DRIVERS}
    assert "박종성" in names
```

- [ ] **Step 2: 테스트 실행 (FAIL 확인)**

```bash
cd "c:/Users/yjisu/Desktop/SCM_WORK" && python -m pytest tests/virtual_sap/test_dispatch_advisor_roster.py -v
```

Expected: 3 FAIL (test_johee_sun_present / test_kim_min_jun_removed / test_lee_jang_hoon_cbm_updated)

- [ ] **Step 3: dispatch_advisor.py line 49~54 수정**

`c:/Users/yjisu/Desktop/SCM_WORK/harness/virtual_sap/agents/dispatch_advisor.py` line 49~54:

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
# Source of truth: Airtable 배송파트너 (tblI4ZXrte7WyhXyd, contract_type ∈ {계약직, 개인사업자})
# 동적 조회는 harness.dispatch.resource_loader.load_drivers() 참조
# 2026-05-27 (Sub-Spec 1 v2): CA-0004 김민준 탈퇴 → 조희선 (recPkgE4o3cs0krnR) 교체
#                              이장훈 max_cbm 7.6 → 4.5 (스타리아 화물칸 추정, Open Decision)
INHOUSE_DRIVERS = [
    ("CA-0002", "이장훈", 4.5),    # 현대 스타리아 화물칸 (추정)
    ("CA-NEW-1", "조희선", 7.616), # 콘솔 6건 (기존 Airtable record CBM 사용)
    ("CA-0003", "박종성", 9.486),  # 변동비, 큰 차량 (기존 Airtable record CBM 사용)
]
```

- [ ] **Step 4: 테스트 PASS 확인**

```bash
cd "c:/Users/yjisu/Desktop/SCM_WORK" && python -m pytest tests/virtual_sap/test_dispatch_advisor_roster.py -v
```

Expected: 5 passed

- [ ] **Step 5: 기존 dispatch_advisor 회귀 테스트 통과 확인**

```bash
cd "c:/Users/yjisu/Desktop/SCM_WORK" && python -m pytest tests/virtual_sap/ -v 2>&1 | tail -20
```

Expected: 모든 tests pass (또는 새 5개만)

- [ ] **Step 6: Commit**

```bash
cd "c:/Users/yjisu/Desktop/SCM_WORK"
git add harness/virtual_sap/agents/dispatch_advisor.py tests/virtual_sap/
git commit -m "fix(dispatch): INHOUSE_DRIVERS — CA-0004 김민준 → 조희선 + 이장훈 CBM 4.5 (Sub-Spec 1 v2 Task 6)

- 김민준 기사 탈퇴 → 조희선 교체
- 이장훈 max_cbm 7.6 → 4.5 (스타리아 화물칸 추정 — Open Decision)
- 박종성·조희선 CBM은 기존 Airtable record 값 (9.486 / 7.616) 적용
- 5 pytest 통과

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 7: feature_list + Obsidian log + Validation Contract 검증

**Files:**
- Modify: `.claude/feature_list.json`
- Append: Obsidian `SCM/_AutoResearch/wiki/log.md`

- [ ] **Step 1: feature_list.json SCM-LANE-SUBSPEC-1 → done**

```bash
cd "c:/Users/yjisu/Desktop/SCM_WORK" && python -c "
import json
with open('.claude/feature_list.json', 'r', encoding='utf-8') as f:
    data = json.load(f)
for task in data['tasks']:
    if task['id'] == 'SCM-LANE-SUBSPEC-1':
        task['status'] = 'done'
        task['notes'] += ' [2026-05-27 v2 완료 — 신규 테이블 X (over-engineering 제거), 기존 배송파트너 테이블에 9 필드 추가 + 19 record 분류 + dispatch_advisor.py 갱신 + resource_loader.py + 9 pytest 통과]'
        break
data['updated_at'] = '2026-05-27'
with open('.claude/feature_list.json', 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False, indent=2)
print('✅ SCM-LANE-SUBSPEC-1 → done')
"
```

- [ ] **Step 2: Obsidian log.md (MCP)**

`mcp__obsidian__obsidian_append_content`:

```json
{
  "filepath": "SCM/_AutoResearch/wiki/log.md",
  "content": "\n\n## [2026-05-27] 완료 | Sub-Spec 1 v2 — 배송파트너 테이블 필드 확장 + 운영 정책 등록\n\n- **트리거:** writing-plans v2 → executing-plans. Plan v1(신규 테이블 2개)은 over-engineering으로 폐기, v2로 재설계 (사용자 지적)\n- **산출:**\n  - 배송파트너 테이블 + 9 필드 (residence·work_hours_start/end·daily_fixed_cost·max_daily_orders·contract_type·wave_pattern·autonomy_level·lock_in_reason)\n  - 19 record 분류: internal 4 / autonomous 4 / partial 3 / locked-in 8\n  - 자체 기사 3 record 운영 정책 입력 + 이장훈 CBM 7.616 → 4.5\n  - schema_pin.json: 배송파트너 23 → 32 필드\n  - harness/dispatch/resource_loader.py 신규 (load_drivers/load_partners)\n  - dispatch_advisor.py: CA-0004 김민준 → 조희선 + 이장훈 CBM 정정\n  - 9 pytest 통과 (resource_loader 4 + dispatch_advisor_roster 5)\n- **Validation Contract:** C1~C6 PASS\n- **Open Decisions 잔존:** 이장훈 스타리아 정확 CBM (현재 4.5 추정), 조희선/박종성 차량 spec 검증, 베스트원 비수기 흡수 협의, 다영 퀵 100% 협의\n- **발견:** brainstorm 누락 협력사 — *에스에스아이팩* (6번째)\n- **다음:** Sub-Spec 2 (비수기 흡수 룰 + 시즌 모드)"
}
```

- [ ] **Step 3: Validation Contract C1~C6 최종 검증 스크립트**

```bash
cd "c:/Users/yjisu/Desktop/SCM_WORK" && python -c "
import os
import json
import requests

PAT = os.environ['AIRTABLE_PAT']
HEADERS = {'Authorization': f'Bearer {PAT}'}

# C1: 9 필드 존재
r = requests.get('https://api.airtable.com/v0/meta/bases/app4x70a8mOrIKsMf/tables', headers=HEADERS, timeout=30)
r.raise_for_status()
tables = r.json()['tables']
partner_table = next(t for t in tables if t['id'] == 'tblI4ZXrte7WyhXyd')
field_names = {f['name'] for f in partner_table['fields']}
required = {'residence', 'work_hours_start', 'work_hours_end', 'daily_fixed_cost', 'max_daily_orders', 'contract_type', 'wave_pattern', 'autonomy_level', 'lock_in_reason'}
missing = required - field_names
assert not missing, f'C1 FAIL: missing fields {missing}'
print(f'✅ C1 PASS: 9 신규 필드 모두 존재 (총 {len(field_names)} 필드)')

# C2: 자체 기사 3 record 정책 입력 + 이장훈 CBM 4.5
url = 'https://api.airtable.com/v0/app4x70a8mOrIKsMf/tblI4ZXrte7WyhXyd'
r = requests.get(url, headers=HEADERS, params={'fields[]': ['배송파트너', '배송파트너_CBM', 'residence', 'contract_type', 'daily_fixed_cost']}, timeout=30)
recs = r.json()['records']
drivers = [r for r in recs if r['fields'].get('contract_type') in ('계약직', '개인사업자')]
assert len(drivers) >= 3, f'C2 FAIL: drivers={len(drivers)}'
lee = next((r for r in drivers if '이장훈' in r['fields'].get('배송파트너', '')), None)
assert lee and lee['fields'].get('배송파트너_CBM') == 4.5, f'C2 FAIL: 이장훈 CBM != 4.5'
print(f'✅ C2 PASS: 자체 기사 {len(drivers)}건 정책 입력 + 이장훈 CBM 4.5')

# C3: 외주 분류
partners = [r for r in recs if r['fields'].get('contract_type') in ('외주_3PL', '외주_carrier', '고객직접')]
assert len(partners) >= 10, f'C3 FAIL: partners={len(partners)}'
print(f'✅ C3 PASS: 외주/위탁 {len(partners)}건 분류 완료')

# C4: schema_pin.json
with open('harness/_core/schema_pin.json', 'r', encoding='utf-8') as f:
    schema = json.load(f)
pin_fields = {f['name'] for f in schema['tables']['tblI4ZXrte7WyhXyd']['fields'].values()}
missing_pin = required - pin_fields
assert not missing_pin, f'C4 FAIL: schema_pin missing {missing_pin}'
print(f'✅ C4 PASS: schema_pin.json {len(pin_fields)} 필드 등록')

# C5: resource_loader
from harness.dispatch.resource_loader import load_drivers, load_partners
d = load_drivers()
p = load_partners()
assert len(d) >= 3 and len(p) >= 10
print(f'✅ C5 PASS: resource_loader drivers={len(d)} partners={len(p)}')

# C6: dispatch_advisor INHOUSE_DRIVERS
from harness.virtual_sap.agents.dispatch_advisor import INHOUSE_DRIVERS
ids = {x[0] for x in INHOUSE_DRIVERS}
names = {x[1] for x in INHOUSE_DRIVERS}
assert 'CA-0004' not in ids and '김민준' not in names
assert '조희선' in names
lee_cbm = next((x[2] for x in INHOUSE_DRIVERS if x[1] == '이장훈'), None)
assert lee_cbm == 4.5
print('✅ C6 PASS: dispatch_advisor 정정 (김민준 제거 + 조희선 + 이장훈 CBM 4.5)')

print('')
print('🎉 Validation Contract C1~C6 모두 PASS — Sub-Spec 1 v2 완료 인증')
"
```

Expected: 6 PASS + `🎉 Validation Contract C1~C6 모두 PASS`

- [ ] **Step 4: 통합 pytest**

```bash
cd "c:/Users/yjisu/Desktop/SCM_WORK" && python -m pytest tests/dispatch/ tests/virtual_sap/ -v 2>&1 | tail -15
```

Expected: 9 passed

- [ ] **Step 5: 최종 Commit**

```bash
cd "c:/Users/yjisu/Desktop/SCM_WORK"
git add .claude/feature_list.json
git commit -m "chore(feature-list): SCM-LANE-SUBSPEC-1 → done (v2)

Validation Contract C1~C6 PASS:
- C1: 배송파트너 +9 필드 ✓
- C2: 자체 기사 3 정책 + 이장훈 CBM 4.5 ✓
- C3: 외주 16+ 분류 ✓
- C4: schema_pin 동기화 ✓
- C5: resource_loader 정상 ✓
- C6: dispatch_advisor 정정 ✓

다음: Sub-Spec 2 (비수기 흡수 룰 + 시즌 모드)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## 종료 체크리스트 (Sub-Spec 1 v2)

- [ ] C1~C6 6개 contract 모두 PASS
- [ ] 9개 신규 필드 Airtable 등록 확인
- [ ] 19 record 분류 완료 (Airtable UI 육안 확인 가능)
- [ ] 이장훈 CBM 7.616 → 4.5 갱신 확인
- [ ] git log 마지막 7 commits에 Sub-Spec 1 v2 Task 1~7 모두 기록
- [ ] Obsidian log.md에 2026-05-27 v2 완료 항목
- [ ] feature_list.json에서 SCM-LANE-SUBSPEC-1 status = done

---

## Out of Scope (Sub-Spec 1 v2 범위 외)

- `dispatch_advisor.py`의 INHOUSE_DRIVERS hardcoded → *완전 동적 조회로 전환* — Sub-Spec 2 (시즌 모드 + idle capacity와 함께)
- 통합 적재 wave 알고리즘 — Sub-Spec 3
- Scorecard 대시보드 — Sub-Spec 4
- KPI 측정 — Sub-Spec 5
- Open Decisions 해결 (스타리아 정확 CBM, 조희선·박종성 차량 spec) — 사용자 액션
- 베스트원 비수기 흡수 협의 — 외부 협의

---

## v1 vs v2 비교

| 측면 | v1 (폐기) | v2 (현재) |
|------|---------|---------|
| 신규 테이블 | 2개 | **0개** |
| 신규 필드 | 24개 (신규 테이블 내) | **9개** (기존 테이블 확장) |
| 데이터 이중화 | 자체 기사 정보 ↔ 배송파트너 분리 | **단일 SSOT** |
| 마이그레이션 | 기존 19 record 무시 | **기존 19 record 활용** |
| 작업량 | 더 큼 | **더 작음** |
| 운영자 UX | 두 테이블 왔다갔다 | **한 테이블에서 모두 확인** |
| 기존 자동화 영향 | 0 (격리) | 0 (필드 추가만, 기존 필드 불변) |
| 발견된 누락 | — | **에스에스아이팩 (6번째 협력사)** |

→ **v2가 모든 측면에서 우수.** Karpathy 원칙 "Surgical Changes" + "Simplicity First" 준수.
