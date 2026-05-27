# Sub-Spec 3 — Wave 추천 엔진 Implementation Plan

> Chain: lane-strategy-v3 | Phase: P3.5 (implementation)
> Design ref: `_AutoResearch/SCM/outputs/2026-05-27-sub-spec-3-wave-recommender-design.md`
> Selisi 작업: 2~3주 / Tasks: 13

## Validation Contract (C1~C8)

P3.5 종료 조건. 모든 Task 완료 후 self-check 스크립트 PASS.

| Contract | Pass 기준 | 검증 명령 |
|---|---|---|
| **C1** | 자동 대상 필터 (project + 이동목적 + 미발송 + 7일 rolling) sample 50건 100% 일치 | `python scripts/verification/verify_c1_filter.py` |
| **C2** | 배송슬롯 자동 결정 정확도 ≥ 80% (25-01~26-05-27 7,588건 역사 데이터) | `python scripts/verification/verify_c2_slot.py` |
| **C3** | Multi-PNA consolidation sample 10 case 정확 그룹화 | `python -m pytest tests/dispatch/test_consolidation.py` |
| **C4** | 자체 기사 capacity 초과 없음 (이장훈 ≤4.5·≤3 / 조희선 ≤7.616·≤6 / 박종성 ≤9.486·≤8) | `python -m pytest tests/dispatch/test_capacity.py` |
| **C5** | Locked-in 9 records recommender override 0건 | `python scripts/verification/verify_c5_lockin.py` |
| **C6** | Slack 다이제스트 quiet hours (22:00~07:00) 발송 0건 | `python -m pytest tests/dispatch/test_quiet_hours.py` |
| **C7** | wave_locked=True 처리 (override 다음 cycle skip) | `python -m pytest tests/dispatch/test_override.py` |
| **C8** | 7일 rolling 영업일 기준 정확 | `python -m pytest tests/dispatch/test_rolling_window.py` |

**Failure mode:** 어느 Contract 1개라도 FAIL 시 production 배포 금지, 해당 Task 재작업.

---

## Task 0 — Pre-flight (백업 + 의존성 확인)

**Goal:** P1·P2 산출 + 환경 점검.

```bash
# 1. git log 확인 (P1 P2 commit 포함)
git log --oneline -8
# Expected: 87feb4b chain(v3): P1 실행 + P2 brainstorm 완료

# 2. AIRTABLE_PAT 환경변수 확인
test -n "$AIRTABLE_PAT" || echo "❌ Missing"

# 3. P1 resource_loader 정상 동작
python -c "from harness.dispatch.resource_loader import load_drivers, load_partners; print(len(load_drivers()), len(load_partners()))"
# Expected: 3 16 (또는 4 16 — 조희선 새 추가 반영)

# 4. 기존 Shipment 필드 확인 (배송슬롯 = singleSelect, fldcSrlxCngYQHtSV)
python -c "import json; s=json.load(open('harness/_core/schema_pin.json')); print('배송슬롯 OK' if 'fldcSrlxCngYQHtSV' in str(s) else 'MISSING')"
```

**산출:** `harness/_core/schema_pin.json.bak.2026-MM-DD` (백업).

**검증:** 모든 step OK 출력.

---

## Task 1 — Shipment 테이블 신규 4 필드 추가

**Goal:** wave_recommendation / wave_confidence / wave_locked / wave_updated_at PATCH.

**MCP 호출 (`mcp__claude_ai_Airtable__create_field`, TMS base):**
1. `wave_recommendation` (singleSelect) — choices: `W1`, `W2`, `W3`, `spillover_고고엑스`, `spillover_로젠`, `수동`, `locked-in`
2. `wave_confidence` (number, decimal precision 2)
3. `wave_locked` (checkbox, default false)
4. `wave_updated_at` (dateTime — note: lastModifiedTime은 fld 전체 변경 추적이라 부적합, explicit dateTime 권장)

**Idempotent:** field 이미 존재 시 skip.

**산출:** `harness/_core/schema_pin.json` 4 신규 fldXXX ID 등록 (총 Shipment 필드 수 + 4).

**검증:**
```bash
python -c "
import json
s = json.load(open('harness/_core/schema_pin.json'))
text = json.dumps(s)
for f in ['wave_recommendation', 'wave_confidence', 'wave_locked', 'wave_updated_at']:
    print(f'{f}: {chr(0x2705) if f in text else chr(0x274C)}')"
```

---

## Task 2 — `harness/dispatch/region_classifier.py` 신규 (Address → Region)

**Goal:** 수령인(주소) rollup → region cluster 분류.

```python
# harness/dispatch/region_classifier.py
"""Address rollup → driver eligibility tier (v2 data-driven, 24-01~26-05 5,056건 분석).

Tier scheme:
- tier1_seoul: 이장훈·조희선·박종성 모두 가능 (이장훈 91.6% / 조희선 74.3% / 박종성 42.7%)
- tier2_이장훈_gyeonggi: 이장훈 overflow 가능 경기 city set (사용자 명시 + 데이터 ≥1건)
- tier3_gyeonggi_etc: 그 외 경기 — 조희선·박종성만 가능
- tier4_incheon: 조희선·박종성 가능 (데이터 1.7% / 4.4%)
- tier5_provincial: 박종성 only (전국 데이터 cover) → fallback spillover_로젠
- unknown: NULL → 수동 처리
"""
from typing import Optional

# 이장훈 가능 경기 city set (사용자 명시 + 데이터 ≥1건 hist union)
IJANGHOON_GYEONGGI_CITIES = {
    '구리', '광명', '성남', '고양',   # 사용자 명시
    '하남', '부천', '안양', '과천', '안산',  # 데이터 ≥1건
    '군포', '남양주', '수원',  # 데이터 ≥1건
}

def classify_region(address: Optional[str]) -> str:
    if not address:
        return 'unknown'
    addr = str(address)

    if '서울' in addr:
        return 'tier1_seoul'

    if '경기' in addr:
        if any(city in addr for city in IJANGHOON_GYEONGGI_CITIES):
            return 'tier2_이장훈_gyeonggi'
        return 'tier3_gyeonggi_etc'

    if '인천' in addr:
        return 'tier4_incheon'

    return 'tier5_provincial'  # 지방 광역시·도 (박종성 가능)
```

**산출:** 신규 파일.

**검증:** Task 5 pytest에서 `tests/dispatch/test_region_classifier.py` (5 tests) 검증.

---

## Task 3 — `harness/dispatch/slot_decider.py` 신규 (Stage A)

**Goal:** Rule-based 3단계 배송슬롯 결정 + 시간 텍스트 파싱.

```python
# harness/dispatch/slot_decider.py
"""Stage A — 배송슬롯 자동 결정.

3단계 분기:
1. 배송방식 ∈ {택배(일반)/택배(제주산간)/신시어리택배} → 무관 (32%+ 즉시)
2. 퀵·자체 중 고객 희망 수령 시간 → parse_time_window → slot
3. 그 외 퀵·자체 → 오전 default (50%+ historical pattern)
"""
import re
from dataclasses import dataclass
from typing import Optional, Tuple

PARCEL_METHODS = {'택배(일반)', '택배(제주산간)', '신시어리택배'}
QUICK_METHODS = {'퀵(수도권)', '퀵(지방)', '자체기사', '바로고', '고객직접퀵배차', '신시어리퀵'}

@dataclass
class TimeWindow:
    start_h: float  # 24h decimal (e.g., 9.5 = 09:30)
    end_h: float
    is_split: bool = False  # "10:00~11:45, 13:00~19:00" 같은 split
    is_well_formed: bool = True

# 정규식 패턴 (실제 데이터 기반)
HHMM_RANGE = re.compile(r'(\d{1,2})(?::(\d{2}))?\s*[~\-–]\s*(\d{1,2})(?::(\d{2}))?')
KOREAN_TIME = re.compile(r'(오전|오후|저녁|아침|밤)')

def parse_time_window(text: str) -> Optional[TimeWindow]:
    if not text:
        return None

    matches = HHMM_RANGE.findall(text)
    if matches:
        ranges = []
        for h1, m1, h2, m2 in matches:
            start = int(h1) + (int(m1) / 60 if m1 else 0)
            end = int(h2) + (int(m2) / 60 if m2 else 0)
            ranges.append((start, end))
        if len(ranges) > 1:
            # split 같은 케이스 — broadest
            return TimeWindow(min(r[0] for r in ranges), max(r[1] for r in ranges), is_split=True)
        return TimeWindow(ranges[0][0], ranges[0][1])

    # Korean keyword fallback
    if '오전' in text:
        return TimeWindow(9, 12)
    if '오후' in text:
        return TimeWindow(13, 18)
    if '저녁' in text or '퇴근' in text or '밤' in text:
        return TimeWindow(18, 22)

    return None  # malformed

def map_window_to_slot(w: TimeWindow) -> str:
    span = w.end_h - w.start_h

    if w.is_split or span >= 6:
        return '무관'

    if w.end_h <= 12:
        return '오전'

    if 13 <= w.start_h and w.end_h <= 16:
        return '오후 1 (오후 2시 - 4시)'

    if 16 <= w.start_h and w.end_h <= 18:
        return '오후 2 (오후 4시 - 6시)'

    if w.start_h >= 18:
        return '야간'

    if span < 2:
        return '특정시간 (희망수령시간 확인)'

    return '무관'  # broad / edge

def decide_slot(method: str, hope_time_text: Optional[str]) -> Tuple[Optional[str], float]:
    """배송슬롯 + confidence (0~1).

    Returns (None, 0.0) → NULL 유지 + 수동 검토 flag.
    """
    if method in PARCEL_METHODS:
        return '무관', 1.0

    if hope_time_text:
        window = parse_time_window(hope_time_text)
        if window:
            slot = map_window_to_slot(window)
            confidence = 0.9 if window.is_well_formed and not window.is_split else 0.7
            return slot, confidence

    if method in QUICK_METHODS:
        return '오전', 0.8

    return None, 0.0
```

**산출:** 신규 파일.

**검증:** Task 5 pytest에서 `test_slot_decider.py` (10+ tests).

---

## Task 4 — `harness/dispatch/wave_assigner.py` 신규 (Stage B+C+D)

**Goal:** Multi-PNA consolidation + Priority 순차 + Spillover + Override.

```python
# harness/dispatch/wave_assigner.py
"""Stage B+C+D — Wave 배정 알고리즘.

Pipeline:
1. group_by(slot, region, 배송_차수)
2. PNA cluster (project_code) within group
3. Try W1 → W2 → W3 priority + region 적합도
4. Overflow → spillover_로젠 (지방·대형) or spillover_고고엑스 (peak 시즌)
5. Apply autonomy_level filter (autonomous 제외, locked-in 강제 라벨)
6. Override 처리 (wave_locked=True → skip)
"""
from collections import defaultdict
from dataclasses import dataclass, field
from typing import List, Dict, Optional

DRIVER_LIMITS = {
    'W1': {'driver_id': 'CA-0002', 'name': '이장훈', 'max_cbm': 4.5, 'max_count': 3,
           'regions': {'tier1_seoul', 'tier2_이장훈_gyeonggi'},
           'preferred_slots': {'오전'},
           'pattern': '09:00_고정'},
    'W2': {'driver_id': 'CA-NEW-1', 'name': '조희선', 'max_cbm': 7.616, 'max_count': 6,
           'regions': {'tier1_seoul', 'tier2_이장훈_gyeonggi', 'tier3_gyeonggi_etc', 'tier4_incheon'},
           'preferred_slots': {'무관', '오전', '오후 1 (오후 2시 - 4시)'},
           'pattern': '1회_99%_고정'},
    'W3': {'driver_id': 'CA-0003', 'name': '박종성', 'max_cbm': 9.486, 'max_count': 8,
           'regions': {'tier1_seoul', 'tier2_이장훈_gyeonggi', 'tier3_gyeonggi_etc', 'tier4_incheon', 'tier5_provincial'},
           'preferred_slots': {'무관', '오전', '오후 1 (오후 2시 - 4시)', '오후 2 (오후 4시 - 6시)'},
           'pattern': 'trigger_기반'},
}

@dataclass
class Shipment:
    id: str
    project_code: str
    slot: Optional[str]
    region: str
    cbm: float
    cbm_confidence: float
    slot_confidence: float
    assigned_partner: Optional[str] = None
    wave_locked: bool = False

@dataclass
class WavePlan:
    wave_id: str
    shipments: List[Shipment] = field(default_factory=list)

    @property
    def total_cbm(self) -> float:
        return sum(s.cbm for s in self.shipments)

    @property
    def count(self) -> int:
        return len(self.shipments)

def try_consolidate(wave_id: str, group: List[Shipment], plan: WavePlan) -> bool:
    if wave_id.startswith('spillover') or wave_id == 'locked-in':
        plan.shipments.extend(group)
        return True

    limits = DRIVER_LIMITS[wave_id]
    new_cbm = plan.total_cbm + sum(s.cbm for s in group)
    new_count = plan.count + len(group)

    if new_cbm > limits['max_cbm'] or new_count > limits['max_count']:
        return False

    # region 적합도
    if not all(s.region in limits['regions'] for s in group):
        return False

    plan.shipments.extend(group)
    return True

def get_seasonal_mode(today_iso: str) -> str:
    month = int(today_iso[5:7])
    return 'peak' if month in {11, 12, 1, 2} else 'off-peak'

def assign_waves(shipments: List[Shipment], partner_autonomy: Dict[str, str], today_iso: str) -> Dict[str, WavePlan]:
    """메인 entry point.

    partner_autonomy: {'PNA-001': 'autonomous', 'PNA-002': 'locked-in', ...} P1 resource_loader 산출.
    """
    plans: Dict[str, WavePlan] = {
        'W1': WavePlan('W1'),
        'W2': WavePlan('W2'),
        'W3': WavePlan('W3'),
        'spillover_고고엑스': WavePlan('spillover_고고엑스'),
        'spillover_로젠': WavePlan('spillover_로젠'),
        'locked-in': WavePlan('locked-in'),
        '수동': WavePlan('수동'),  # NULL slot, 수동 검토
    }

    # 1. Override 처리 — wave_locked=True 분리
    active = [s for s in shipments if not s.wave_locked]

    # 2. autonomy filter
    for s in shipments:
        autonomy = partner_autonomy.get(s.assigned_partner, 'unknown')
        if autonomy == 'autonomous':
            continue  # 추천 완전 제외
        if autonomy == 'locked-in':
            plans['locked-in'].shipments.append(s)
            s.wave_locked = True
            continue
        # partial / 자체 / unknown → 통상 처리
        active.append(s) if s not in active else None

    # 3. NULL slot은 수동
    null_slot = [s for s in active if s.slot is None]
    for s in null_slot:
        plans['수동'].shipments.append(s)
    active = [s for s in active if s.slot is not None]

    # 4. Group by (slot, region, 배송_차수)
    by_key = defaultdict(list)
    for s in active:
        by_key[(s.slot, s.region)].append(s)

    # 5. PNA cluster
    for group in by_key.values():
        group.sort(key=lambda s: (s.project_code, -s.cbm))

    # 6. Tier-based Priority 순차 (data-driven)
    TIER_TO_CANDIDATES = {
        'tier1_seoul':            ['W1', 'W2', 'W3'],
        'tier2_이장훈_gyeonggi':   ['W1', 'W2', 'W3'],
        'tier3_gyeonggi_etc':     ['W2', 'W3'],
        'tier4_incheon':          ['W2', 'W3'],
        'tier5_provincial':       ['W3'],  # 박종성 only (전국 가능)
        'unknown':                [],
    }

    mode = get_seasonal_mode(today_iso)

    for (slot, region), group in by_key.items():
        candidates = TIER_TO_CANDIDATES.get(region, [])

        # W1은 오전 슬롯만 적재
        if 'W1' in candidates and slot != '오전':
            candidates = [c for c in candidates if c != 'W1']

        for wave_id in candidates:
            if try_consolidate(wave_id, group, plans[wave_id]):
                break
        else:
            # All eligible self-drivers full → spillover
            if region == 'tier5_provincial':
                plans['spillover_로젠'].shipments.extend(group)
            elif mode == 'peak' and any(s.cbm < 3 for s in group):
                plans['spillover_고고엑스'].shipments.extend(group)
            else:
                plans['spillover_로젠'].shipments.extend(group)

    return plans
```

**산출:** 신규 파일.

**검증:** Task 5 pytest 14+ tests.

---

## Task 5 — pytest 작성 (tests/dispatch/)

**Goal:** Stage A·B·C·D 단위 테스트 + Contract C2·C3·C4·C5·C6·C7·C8 충족.

**파일 목록:**
```
tests/dispatch/test_region_classifier.py     (5 tests, Contract C1·C3 보조)
tests/dispatch/test_slot_decider.py          (12 tests, Contract C2)
tests/dispatch/test_consolidation.py         (10 tests, Contract C3·C4)
tests/dispatch/test_capacity.py              (6 tests, Contract C4)
tests/dispatch/test_lockin.py                (4 tests, Contract C5)
tests/dispatch/test_override.py              (5 tests, Contract C7)
tests/dispatch/test_quiet_hours.py           (3 tests, Contract C6)
tests/dispatch/test_rolling_window.py        (4 tests, Contract C8)
```

총 **49 tests**. 모두 PASS 필수.

**검증:**
```bash
python -m pytest tests/dispatch/ -v
# Expected: 49 passed
```

---

## Task 6 — `harness/dispatch/wave_recommender.py` Main entry

**Goal:** 4-Stage Pipeline 연결 + Airtable PATCH + Slack 다이제스트.

```python
# harness/dispatch/wave_recommender.py
"""Sub-Spec 3 Main Entry — Wave 추천 엔진.

Pipeline:
1. Fetch auto_targets (Airtable Shipment + filter)
2. Stage A: decide_slot per shipment
3. Stage B+C+D: assign_waves (consolidation + priority + spillover + override)
4. Airtable PATCH (wave_recommendation + wave_confidence + wave_locked + 배송슬롯)
5. Slack 다이제스트 (변경분만, quiet hours 준수)
"""
from datetime import datetime
import os
import requests

from harness.dispatch.resource_loader import load_drivers, load_partners
from harness.dispatch.region_classifier import classify_region
from harness.dispatch.slot_decider import decide_slot
from harness.dispatch.wave_assigner import assign_waves, Shipment
from harness.dispatch.cbm_estimator import estimate_cbm  # P2.5 dependency

AIRTABLE_PAT = os.environ['AIRTABLE_PAT']
BASE = 'app4x70a8mOrIKsMf'
SHIPMENT_TABLE = 'tbllg1JoHclGYer7m'

def fetch_auto_targets(today_iso, d_plus=7):
    # filterByFormula로 자동 대상만 fetch
    # (project NOT NULL + 이동목적 + 출하확정일 + 미발송)
    ...

def is_quiet_hour(now):
    h = now.hour
    return h >= 22 or h < 7

def main():
    today = datetime.now()
    today_iso = today.isoformat()[:10]

    # Stage A·B·C·D
    auto_targets = fetch_auto_targets(today_iso)
    partners = load_partners()
    partner_autonomy = {p.partner_id: p.autonomy_level for p in partners}

    shipments = []
    for raw in auto_targets:
        cbm, cbm_conf = estimate_cbm(raw)
        slot, slot_conf = decide_slot(raw.method, raw.hope_time_text)
        region = classify_region(raw.address)
        shipments.append(Shipment(
            id=raw.id, project_code=raw.project_code,
            slot=slot, region=region, cbm=cbm,
            cbm_confidence=cbm_conf, slot_confidence=slot_conf,
            assigned_partner=raw.assigned_partner,
            wave_locked=raw.wave_locked,
        ))

    plans = assign_waves(shipments, partner_autonomy, today_iso)

    # Airtable PATCH (batch 10)
    diff = patch_airtable(plans)

    # Slack 다이제스트 (변경분 + quiet hours)
    if diff and not is_quiet_hour(today):
        send_slack_digest(plans, diff)
    else:
        save_pending_digest(plans, diff)  # 다음 cycle batch

def patch_airtable(plans):
    # batch_size 10, idempotent
    ...

def send_slack_digest(plans, diff):
    ...
```

**산출:** 신규 파일 + `scripts/cron/wave_recommender_cron.py` (cron entry).

**검증:** Task 9 (smoke test + dry-run).

---

## Task 7 — Polling Integration (P4 piggyback)

**Goal:** P4 Change Detection의 polling 스케줄(3x/day: 09:00 / 14:00 / 17:00)에 추천 엔진 호출 추가.

**옵션 (P4 미완 시):**
- 임시 standalone cron `.github/workflows/wave_recommender.yml` (P4 완료 후 통합)

```yaml
# .github/workflows/wave_recommender.yml
name: Wave Recommender
on:
  schedule:
    - cron: '0 0,5,8 * * 1-5'  # KST 09:00 / 14:00 / 17:00 영업일
jobs:
  run:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: '3.14' }
      - run: pip install -r requirements.txt
      - run: python -m harness.dispatch.wave_recommender
        env:
          AIRTABLE_PAT: ${{ secrets.AIRTABLE_PAT }}
          SLACK_BOT_TOKEN: ${{ secrets.SLACK_BOT_TOKEN }}
```

**산출:** 신규 workflow.

**검증:** GitHub Actions UI에서 1주 cron 실행 안정성 (C6 quiet hours 0건 위반 확인).

---

## Task 8 — Verification Scripts (Contract C1·C2·C5)

**Goal:** Validation Contract 자동 검증 스크립트 (사람 review용 reports 생성).

```
scripts/verification/verify_c1_filter.py     # auto_targets sample 50건 100% 일치 (수동 GT 비교)
scripts/verification/verify_c2_slot.py       # 25-01~26-05-27 7,588건 vs 사용자 결정 분포 ≥80%
scripts/verification/verify_c5_lockin.py     # locked-in 9 records → wave_recommendation='locked-in' 검증
```

`verify_c2_slot.py` 출력 예시:
```
[배송슬롯 정확도] 80% 기준선
Total: 7,588 records (택배 제외)
True positives: 6,250
Mis-classifications: 1,338
Accuracy: 82.4% ✅ PASS

Per-slot accuracy:
  무관: 91.2% (n=3254)
  오전: 78.5% (n=2538)
  오후 1: 65.0% (n=638)
  오후 2: 43.6% (n=55)
  특정시간: 25.0% (n=16)
```

**산출:** 3 신규 스크립트 + 출력 reports → `_AutoResearch/SCM/outputs/verification/`

---

## Task 9 — Smoke Test (Dry-Run + Production Pilot)

**Goal:** Production 배포 전 검증.

```bash
# 1. Dry-run (no PATCH, log only)
DRY_RUN=true python -m harness.dispatch.wave_recommender

# Expected output:
# Stage A: 130 shipments classified (택배 42 / 퀵 88)
# Stage B: W1=8, W2=6, W3=4
# Stage C: spillover_로젠=12, spillover_고고엑스=0 (off-peak)
# Stage D: 5 override skipped
# Total automation: 35/42 (83%)
```

```bash
# 2. Pilot 1 day production
python -m harness.dispatch.wave_recommender
# → 사용자 다음날 추천 수락률 모니터링
# Kill Criteria: 수락률 < 50% → 알고리즘 가중치 재조정
```

**산출:** smoke_test_report.md (1 day pilot 결과).

**검증:** Validation Contract C1~C8 모두 PASS + 수락률 ≥ 50%.

---

## Task 10 — Audit Logging

**Goal:** Override 감지 + 신뢰도 낮은 추천 audit trail.

```python
# harness/dispatch/audit_log.py
"""Wave recommender audit log.

Events:
- override_detected: 사용자가 assigned_carrier 수동 변경
- low_confidence_recommendation: wave_confidence < 0.7
- consolidation_failed: PNA 그룹 wave 배정 실패 (모든 후보 capacity full)
- locked_in_attempted_override: bug check — recommender가 locked-in 강제 변경 시도
"""
import json
from datetime import datetime
from pathlib import Path

LOG_PATH = Path('_AutoResearch/SCM/outputs/audit_log/wave_recommender.jsonl')

def log_event(event_type: str, payload: dict):
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    entry = {'ts': datetime.now().isoformat(), 'event': event_type, **payload}
    with open(LOG_PATH, 'a', encoding='utf-8') as f:
        f.write(json.dumps(entry, ensure_ascii=False) + '\n')
```

**Open Decision (P2 brainstorm에서도 surface):** audit_log 위치 — `_AutoResearch/SCM/outputs/audit_log/` 컨벤션 매칭.

**산출:** 신규 파일.

---

## Task 11 — Schema_pin 갱신 + feature_list 업데이트

**Goal:** 신규 4 Shipment 필드 ID 등록 + 태스크 완료 표시.

**산출:**
- `harness/_core/schema_pin.json` 4 fldXXX 추가
- `.claude/feature_list.json` `SCM-LANE-SUBSPEC-3` status `done`, `completed_at: 2026-MM-DD`

---

## Task 12 — Validation Contract Self-Check 스크립트

**Goal:** C1~C8 자동 검증 통합 스크립트.

```bash
python scripts/verification/verify_subspec3_contract.py

# Output:
# ✅ C1 자동 대상 필터: 50/50 (100%)
# ✅ C2 배송슬롯 정확도: 82.4% (≥80%)
# ✅ C3 Multi-PNA consolidation: 10/10
# ✅ C4 capacity 초과 0건
# ✅ C5 locked-in override 0건
# ✅ C6 quiet hours 발송 0건
# ✅ C7 wave_locked skip 정확
# ✅ C8 7일 rolling 영업일 기준 OK
# 
# All Contracts PASS — production ready.
```

---

## Task 13 — Obsidian Log + Handoff + Final Commit

**Goal:** P3.5 종료 + P4 진입 준비.

```markdown
# Obsidian log entry
## [YYYY-MM-DD] 완료 | lane-strategy-v3 P3.5 — Sub-Spec 3 Wave 추천 엔진 implementation

**Phase:** lane-strategy-v3 P3.5
**산출:**
- Stage A·B·C·D 4-stage pipeline (4 신규 module)
- 49 pytest PASS
- Validation Contract C1~C8 ALL PASS
- 1 day pilot 수락률 X% (목표 ≥50%)
- Slack 다이제스트 quiet hours 준수

**다음:** P4 Sub-Spec 4 Change Detection + 가정 OTIF
```

**Master tracker:** P3.5 row → ✅ DONE, P4 row → READY_TO_START

**Final commit:**
```
chain(v3): P3.5 Sub-Spec 3 Wave 추천 엔진 구현 (Contract C1~C8 PASS)

- Stage A: 배송슬롯 자동 결정 (Rule-based 3단계, 7,588건 정확도 82%+)
- Stage B: Multi-PNA consolidation + Priority 순차 (W1·W2·W3)
- Stage C: Spillover 분배 (Locked-in skip, autonomous 제외)
- Stage D: Override 처리 (wave_locked 보호)
- 신규 4 Shipment 필드 + 4 신규 module + 49 pytest PASS
- 1 day pilot 수락률 X% (목표 ≥50%)
- audit_log: override_detected / low_confidence / consolidation_failed
```

---

## Risks & Open Decisions (재공시)

P3 design doc §9의 Open Decisions를 P3.5 구현 전 확정 필요:

1. 인천 region 자체 가능 여부
2. NULL 슬롯 default 처리 (오전 vs 무관 vs 수동 검토)
3. W1 이장훈 광명/고양/성남 overflow 우선순위
4. Multi-PNA consolidation 적재율 향상 측정 baseline

→ 사용자 review에서 확정.

## 작업 순서 요약

```
Task 0 → 1 → [2·3 병렬] → 4 → 5 (pytest) → 6 (main entry)
       → 7 (cron) → 8 (verification) → 9 (smoke) → 10 (audit)
       → 11 (schema) → 12 (contract check) → 13 (handoff + commit)
```

**총 추정:** 2~3주 (코딩 1.5주 + 검증·smoke 0.5주 + buffer 0.5주).

**선행:** P2.5 (Sub-Spec 2 implementation) — 이상적으로 P2.5 완료 후 P3.5 진입. 또는 estimate_cbm stub mock으로 병렬 가능.
