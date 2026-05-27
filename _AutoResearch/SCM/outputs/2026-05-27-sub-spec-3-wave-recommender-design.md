# Sub-Spec 3 — Wave 추천 엔진 Design

> Chain: lane-strategy-v3 | Phase: P3 (brainstorm → design → plan)
> 작성: 2026-05-27
> 입력 의존: P1 (자원 매핑 SSOT, commit 87feb4b), P2 (CBM 추정 엔진 plan, commit 87feb4b)

## 1. Context

P1·P2 산출로 운영 자원 (19 records, 자체 4 + 외주 16) + CBM 추정 (Product 344 매칭) 체계는 갖춰짐. 남은 핵심 — **"언제·누구에게·어떻게 wave를 배정할지"** 자동화. 26년 1,640건 출하 reality check 결과 70~80% 자동 배차 가능 (사용자 결정, Plan v3 #8).

**왜 brainstorm/data-driven 접근:** 25-01 ~ 26-05-27 기간 Shipment 7,588건 (배송슬롯 결정 기록 보유)을 분석해 배송슬롯 패턴을 도출 — 단순 규칙으로 80%+ 자동 분류 가능함을 확인.

**Data-driven Foundation (분석 결과):**
| 슬롯 | 건수 | 비중 | 패턴 |
|---|---|---|---|
| 무관 | 3,254 | 42.9% | 택배(일반/제주/신시어리) 다수 + 시간 무관 퀵 |
| 오전 | 2,538 | 33.4% | 퀵(수도권) 09:00 default |
| NULL | 1,082 | 14.3% | 사용자 미설정 (자동화 핵심 타겟) |
| 오후 1 (PM 2~4) | 638 | 8.4% | 희망수령시간 명시 (e.g., "13:00~18:00") |
| 오후 2 (PM 4~6) | 55 | 0.7% | rare |
| 특정시간 | 16 | 0.2% | narrow window (e.g., "10:00~11:00") |
| 야간 | 5 | 0.1% | edge case |

**입력 필드 사용률 (Shipment 7,588건 기준):**
- `배송 특이사항란` (Shipment): **1%** — 사실상 deprioritize
- `고객 희망 수령 시간` (배송요청): 오후 1·2 슬롯에서 활발 (specific range)
- `배송시간(수정)` (배송요청): **0% 사용** — 입력 routing에서 제외
- `체크파이널` (배송요청): 거의 비어있음

→ Slot 결정에 의미 있는 필드: **배송방식 + 고객 희망 수령 시간** 2개만.

## 2. Architecture (4-Stage Pipeline)

```
[Polling 3x/day]
       ↓
[Filter: 자동 대상]
       ↓
[Stage A] 배송슬롯 자동 결정 (Rule-based 3단계)
       ↓
[Stage B] Multi-PNA Consolidation + Wave 배정 (Priority + Geo)
       ↓
[Stage C] Spillover 분배 (Locked-in skip)
       ↓
[Stage D] Override 처리 (사용자 수동 보호)
       ↓
[Output] Airtable PATCH + Slack 다이제스트
```

**자동 대상 필터 (Plan v3 확정, 변경 없음):**
```python
auto_targets = shipments.filter(
    project IS NOT NULL
    AND 이동목적_from_movement_rollup IN ('고객납품', '생산샘플')
    AND 출하확정일 BETWEEN today AND today + 7
    AND 발송상태_TMS != '출하 완료'
)
# 제외: 재고이동·기타 (project NULL) — 수동 처리
```

## 3. Stage A — 배송슬롯 자동 결정 (Rule-based 3단계)

```python
def decide_slot(shipment) -> Tuple[str, float]:
    """배송슬롯 자동 결정. confidence < 0.7 면 NULL 유지 + 수동 검토 flag."""
    method = shipment.배송방식  # rollup

    # 1단계: 택배 패턴 → 무관 (32%+ 즉시)
    if method in {'택배(일반)', '택배(제주산간)', '신시어리택배'}:
        return '무관', 1.0

    # 2단계: 퀵·자체 중 희망수령시간 파싱
    req = fetch_배송요청(shipment.배송요청_id)
    time_text = req.get('고객 희망 수령 시간')
    if time_text:
        window = parse_time_window(time_text)
        if window:
            slot = map_window_to_slot(window)
            confidence = 0.9 if window.is_well_formed else 0.7
            return slot, confidence

    # 3단계: 그 외 퀵·자체 → 오전 default (50%+ historical pattern)
    if method in {'퀵(수도권)', '퀵(지방)', '자체기사', '바로고', '고객직접퀵배차'}:
        return '오전', 0.8

    # 4단계: edge — 고객직접수령·노벨빌딩·고객퀵 등
    return None, 0.0  # NULL 유지, 수동 검토
```

**시간 윈도우 → 슬롯 매핑 (`map_window_to_slot`):**
```python
def map_window_to_slot(window: TimeWindow) -> str:
    # window: (start_h, end_h) in 24h
    span = window.end_h - window.start_h
    if span >= 6:
        return '무관'  # broad (e.g., "10:00~21:00")
    if window.end_h <= 12:
        return '오전'
    if 13 <= window.start_h and window.end_h <= 16:
        return '오후 1 (오후 2시 - 4시)'
    if 16 <= window.start_h and window.end_h <= 18:
        return '오후 2 (오후 4시 - 6시)'
    if window.start_h >= 18:
        return '야간'
    if span < 2:
        return '특정시간 (희망수령시간 확인)'
    return '무관'  # split AM+PM
```

**시간 텍스트 정규식 (`parse_time_window`):**
```
패턴 매칭 (실제 데이터 기반):
- "13:00~18:00" → (13, 18)
- "10:00 ~ 11:45, 13:00 ~ 19:00" → split → broadest range (10, 19) → 무관
- "10:00~11:00" → (10, 11) → 특정시간
- "AM 9~12" → (9, 12) → 오전
- "오전" → (9, 12) (관습적)
- "오후" → (13, 18) (관습적)
- "퇴근시간 이후" → (18, 22) → 야간
- malformed → None (fall through to 3단계)
```

## 4. Stage B — Multi-PNA Consolidation + Wave 배정 (Priority + Geo)

### Driver Capability Matrix (data-driven, 24-01 ~ 26-05-27 5,056건 분석)

| Driver | 우선 region | 가능 region (≥1 hist record) | 불가 | Max CBM | Max 건수 | Wave 패턴 |
|---|---|---|---|---|---|---|
| **W1 이장훈** | 서울 (91.6%) | 성남, 광명, 고양, 구리, 하남, 부천, 안양, 과천, 안산 (사용자 명시 + 데이터) | 그 외 경기·인천·지방 | 4.5 | 3 | 09:00 확정 |
| **W2 조희선** | 서울 + 경기 전역 | 인천 (1.7%) | 지방 | 7.616 | 6 | 99% 1 wave 고정 |
| **W3 박종성** | 서울·경기 + 인천 (89.6%) | **전국** (대전·강원·부산·충북·경남·대구·충남·전북·울산·경북 + 기타) | (없음, 전국 가능) | 9.486 | 8 | trigger 기반 (70%+) |
| **spillover_고고엑스** | peak 시즌 capacity 초과 | — | — | — | — | — |
| **spillover_로젠** | 박종성 capacity 초과 시 지방 fallback | — | — | — | — | — |

**핵심 변경 (v2):** 박종성이 전국 가능 → 지방 배송도 자체 우선 시도. **spillover_로젠은 박종성 capacity 초과 시에만 fallback**. 비용 절감 효과.

### Region 식별 (v2, data-driven)

```python
# 이장훈 가능 경기 city set (사용자 명시 + ≥1 데이터 hist)
IJANGHOON_GYEONGGI_CITIES = {
    '구리', '광명', '성남', '고양',   # 사용자 명시
    '하남', '부천', '안양', '과천', '안산',  # 데이터 ≥1건
    '군포', '남양주', '수원',  # 데이터 ≥1건
}

def classify_region(shipment) -> str:
    """수령인(주소) rollup → driver eligibility tier.

    Tier scheme:
    - tier1_seoul: 모든 자체 가능
    - tier2_이장훈_gyeonggi: 이장훈·조희선·박종성 가능
    - tier3_gyeonggi_etc: 조희선·박종성만 가능
    - tier4_incheon: 조희선·박종성 가능 (조희선 1.7%, 박종성 4.4% 데이터)
    - tier5_provincial: 박종성만 가능 (전국 데이터 확보)
    - unknown: NULL slot으로
    """
    addr = shipment.수령인_주소  # rollup
    if not addr:
        return 'unknown'
    addr_norm = addr[0] if isinstance(addr, list) else addr

    if '서울' in addr_norm:
        return 'tier1_seoul'

    if any(city in addr_norm for city in IJANGHOON_GYEONGGI_CITIES):
        return 'tier2_이장훈_gyeonggi'

    if '경기' in addr_norm:
        return 'tier3_gyeonggi_etc'

    if '인천' in addr_norm:
        return 'tier4_incheon'

    # 지방 광역시·도 = 박종성만 가능
    return 'tier5_provincial'
```

### Consolidation + 배정 알고리즘

```python
def assign_waves(auto_targets):
    # 1. Stage A 슬롯 결정
    for sh in auto_targets:
        sh.slot, sh.slot_conf = decide_slot(sh)
        sh.region = classify_region(sh)
        sh.cbm = estimate_cbm(sh)[0]  # P2 호출

    # 2. Group by (slot, region_cluster, 배송 차수)
    by_key = defaultdict(list)
    for sh in auto_targets:
        key = (sh.slot, sh.region, sh.배송_차수 or 1)
        by_key[key].append(sh)

    # 3. PNA cluster within group — 같은 project_code 연속 처리
    for key, group in by_key.items():
        group.sort(key=lambda s: (s.project_code, -s.cbm))

    # 4. Wave 후보 평가 (Priority + Geo Tier + Capacity)
    wave_plan = defaultdict(list)
    mode = get_seasonal_mode(today())  # peak 11~2월 / off-peak 3~10월

    # Tier별 후보 driver matrix (data-driven)
    TIER_TO_CANDIDATES = {
        'tier1_seoul':            ['W1', 'W2', 'W3'],        # 서울 = 모두 가능
        'tier2_이장훈_gyeonggi':   ['W1', 'W2', 'W3'],        # 이장훈 overflow + 조박만
        'tier3_gyeonggi_etc':     ['W2', 'W3'],              # 조희선·박종성만
        'tier4_incheon':          ['W2', 'W3'],              # 조희선(1.7%)·박종성(4.4%)
        'tier5_provincial':       ['W3'],                    # 박종성만 (전국 가능)
        'unknown':                [],                        # → 수동 처리
    }

    for key, group in by_key.items():
        slot, region, 차수 = key

        candidates = TIER_TO_CANDIDATES.get(region, [])

        # W1은 AM 슬롯만 적재 (09:00 출발)
        if 'W1' in candidates and slot not in {'오전'}:
            candidates = [c for c in candidates if c != 'W1']

        # Priority 순차 충전
        assigned = False
        for wave in candidates:
            if try_consolidate(wave, group, wave_plan):
                assigned = True
                break

        # 자체 capacity 초과 또는 unknown → spillover
        if not assigned:
            if region == 'tier5_provincial':
                wave_plan['spillover_로젠'].extend(group)  # 박종성 full → 로젠 fallback
            elif mode == 'peak' and any(s.cbm < 3 for s in group):
                wave_plan['spillover_고고엑스'].extend(group)
            else:
                wave_plan['spillover_로젠'].extend(group)

    return wave_plan
```

### `try_consolidate` (자체 기사 capacity 충족 검사)

```python
DRIVER_LIMITS = {
    'W1': {'max_cbm': 4.5, 'max_count': 3, 'driver': '이장훈'},
    'W2': {'max_cbm': 7.616, 'max_count': 6, 'driver': '조희선'},
    'W3': {'max_cbm': 9.486, 'max_count': 8, 'driver': '박종성'},
}

def try_consolidate(wave_id, group, wave_plan):
    if wave_id.startswith('spillover'):
        wave_plan[wave_id].extend(group)
        return True

    limits = DRIVER_LIMITS[wave_id]
    current = wave_plan[wave_id]
    current_cbm = sum(s.cbm for s in current)
    current_count = len(current)

    # 그룹 전체가 들어가는가
    group_cbm = sum(s.cbm for s in group)
    if current_cbm + group_cbm > limits['max_cbm']:
        return False
    if current_count + len(group) > limits['max_count']:
        return False

    wave_plan[wave_id].extend(group)
    return True
```

### Wave 정책 분기 (bed8d7a refactor 반영)

- **W1 이장훈** — 매일 09:00 확정 출발, AM 슬롯만 적재, 수도권 (서울 우선 + 광명/고양/성남 overflow)
- **W2 조희선** — 99% 1 wave 고정 (하루 1회 모아서 출발), 콘솔 ≤6건, 서울·경기 전역
- **W3 박종성** — trigger 기반 (CBM 70%+ 도달 시 즉시 wave 확정), ≤8건, 전국 가능하나 자체 4 capacity 우선 채움

## 5. Stage C — Spillover 분배 (Locked-in skip, v2 박종성 전국 활용)

```python
def assign_spillover(remaining, mode):
    """자체 3 capacity 초과분만 spillover. tier5_provincial은 박종성 우선 시도 후 fallback."""
    for sh in remaining:
        # tier5_provincial이지만 박종성 full → 로젠 fallback
        if sh.region == 'tier5_provincial':
            sh.wave = 'spillover_로젠'
        elif mode == 'peak' and sh.cbm < 3:
            sh.wave = 'spillover_고고엑스'  # peak 소형
        elif sh.cbm > 5:
            sh.wave = 'spillover_로젠'  # 대형
        else:
            sh.wave = 'spillover_고고엑스'

# P1 외주 19 records 분류 활용
def filter_by_autonomy(shipments):
    """autonomous 4 / partial 2 / locked-in 9 처리."""
    # autonomous (4): recommender 완전 제외
    autonomous_pna = load_partners_by_autonomy('autonomous')
    shipments = [s for s in shipments if s.assigned_partner not in autonomous_pna]

    # locked-in (9): override 금지, 'locked-in' 라벨만
    locked_in_pna = load_partners_by_autonomy('locked-in')
    for s in shipments:
        if s.assigned_partner in locked_in_pna:
            s.wave = 'locked-in'
            s.wave_locked = True

    return shipments
```

## 6. Stage D — Override 처리 (사용자 수동 보호)

```python
def respect_override(shipment, new_recommendation):
    # 사용자가 이미 wave_locked=True 설정 → 추천 skip
    if shipment.wave_locked:
        return None

    # 사용자가 assigned_carrier 수동 변경 감지 → wave_locked=True 자동 설정
    if shipment.assigned_carrier != shipment.recommended_carrier_prev:
        return {'wave_locked': True, 'audit': 'user override detected'}

    return new_recommendation
```

## 7. Output (Airtable PATCH + Slack 다이제스트)

### 신규 Shipment 필드 (4개)

| 필드 | 타입 | 설명 |
|---|---|---|
| `wave_recommendation` | singleSelect | `W1`·`W2`·`W3`·`spillover_고고엑스`·`spillover_로젠`·`수동`·`locked-in` |
| `wave_confidence` | number (0~1) | recommender 신뢰도 (slot_conf × cbm_conf 곱) |
| `wave_locked` | checkbox | 사용자 override (recommender skip flag) |
| `wave_updated_at` | dateTime | 마지막 PATCH 시점 (audit) |

### 기존 필드 PATCH

- `배송슬롯` (singleSelect) — Stage A 결정 결과 (1,082 NULL records 대상)

### Slack 다이제스트 (polling 후, 변경분만)

```
🚚 [14:00] Wave 추천 갱신 (2026-MM-DD)

✅ W1 이장훈: 8건 (CBM 4.2/4.5, 93% 적재) — 신규 3건
🔔 W3 박종성: trigger 도달 (CBM 6.8/9.486, 72%) — wave 확정
⚠️ spillover_로젠: 3건 — 지방 대형 (PNA-2024-XXX 등)
🔒 locked-in: 5건 (다영기획 2, 베스트원 2, 로지비 1)
📋 NULL slot: 12건 (수동 검토 요청, 14.3% 평소)
🔧 사용자 override 감지: 2건 (wave_locked 자동 설정)

총 자동화: 26/30 (87%)
```

**Quiet hours:** 22:00 ~ 07:00 발송 안 함 (다음 polling 시 batch 전송).

## 8. Validation Contract C1~C8

| Contract | 정의 | Pass 기준 |
|---|---|---|
| **C1** | 자동 대상 필터 정확 | project + 이동목적 + 미발송 + 7일 rolling — sample 50건 100% 일치 |
| **C2** | 배송슬롯 자동 결정 정확도 | 25-01~26-05-27 7,588건 역사 데이터 검증, ≥80% 매칭 |
| **C3** | Multi-PNA consolidation 정확 그룹화 | sample 10 case 손동작 검증 |
| **C4** | 자체 기사 capacity 초과 없음 | 이장훈 max_cbm 4.5 / 조희선 7.616 / 박종성 9.486 + 건수 ≤3·6·8 |
| **C5** | Locked-in 9 records recommender override 절대 없음 | wave_locked=True 검증, 강제 'locked-in' 라벨 |
| **C6** | Slack 다이제스트 quiet hours 준수 | 22:00~07:00 발송 0건 (테스트 cron 검증) |
| **C7** | wave_locked=True 처리 정확 | 사용자 override 후 다음 cycle skip 보장 |
| **C8** | 7일 rolling 범위 정확 | 영업일 기준 D+1 ~ D+7 산출 (주말 제외) |

## 9. Risks & Open Decisions

| 리스크 | 영향 | 완화 |
|---|---|---|
| **NULL 14.3% 슬롯** | recommender가 default 오전 일관 적용 시 사용자 패턴과 불일치 가능 | C2에서 정확도 ≤80%면 가중치 조정·feedback loop |
| **인천 region 자체 가능 여부** | 자체 capacity 활용 vs spillover 추가 비용 trade-off | 사용자 확인 후 Driver Matrix 조정 |
| **Multi-PNA consolidation 적재율 향상 미달** | 자체 기사 적재율 < 70% 시 ROI 미달 | Kill Criteria: consolidation 시 적재율 +10% 미달 → MVP 단일 PNA로 격하 |
| **시간 텍스트 변형** | "1시 이후", "오후 2시 ASAP" 등 비정형 | parse_time_window 점진 확장, fallback 무관 |
| **외주 19 분류 변경 빈도** | autonomy_level 재분류 시 recommender 영향 | P1 resource_loader 매 polling 호출 (캐시 5분 TTL) |

### Open Decisions (P3 review에서 결정)

1. **인천 region** — ~~Open~~ ✅ 해소: 조희선·박종성 모두 가능 (각 1.7%·4.4% 데이터). 이장훈은 불가.
2. **NULL 슬롯 default 처리** — 오전 default vs 무관 default vs 수동 검토 flag?
3. **W1 이장훈 경기 city overflow 우선순위** — 서울 capacity 안 차도 경기 시도 vs 서울만 우선 채우고 나머지는 조희선·박종성 활용? (현재 v2: tier별 priority 순차)
4. **Multi-PNA consolidation algorithm 복잡도** — greedy first-fit vs simple grouping?
5. **이장훈 경기 city set** — 사용자 명시 "구리·광명·성남·고양 등" + 데이터 ≥1건 hist union (현재 13 cities). 사용자 final list 확인.

### 데이터 분석 산출 (24-01 ~ 26-05-27 5,056건)

자체 3 기사 실제 destination 분포 — `scripts/analysis/analyze_driver_geography.py`:

**이장훈 (n=1,375):** 서울 91.6% / 경기 4.9% (성남 44, 고양 5, 광명 3, 하남 4, 부천 3, 안양 2, 과천 2) / 인천 0.1% / 지방 ~0%
**조희선 (n=2,296):** 서울 74.3% / 경기 20.4% / 인천 1.7% / 지방 ~3%
**박종성 (n=1,385):** 서울 42.7% / 경기 42.5% / 인천 4.4% / **지방 11%** (대전·강원·부산·충북·경남·대구·충남·전북·울산·경북 등 전국 cover)

## 10. Out of Scope (P3.5+)

- 경로 최적화 (TSP variant) — driver 내부 routing 순서
- 자체 기사 시간대별 micro-allocation (e.g., 이장훈 09:00 출발 후 11:00 두 번째 wave)
- Carrier 단가 협상 데이터 활용 — Sub-Spec 5 Scorecard로
- 변경 감지 + 가정 OTIF — Sub-Spec 4
- 사용자 수락률 모니터링·feedback loop — Sub-Spec 5

## 11. Reuse Path

| 자산 | 출처 | 활용 |
|---|---|---|
| `harness.dispatch.resource_loader.load_drivers()` | P1 (Sub-Spec 1) | Driver list + capability matrix |
| `harness.dispatch.resource_loader.load_partners()` | P1 | 외주 19 records (autonomy_level 활용) |
| `harness.dispatch.cbm_estimator.estimate_cbm()` | P2 (Sub-Spec 2, plan only) | per-shipment CBM 추정 |
| `harness.virtual_sap.agents.dispatch_advisor` | 기존 (CA-0004→조희선 정정 완료) | reference impl, 부분 마이그레이션 또는 import |
| `scripts/seed/update_배송파트너_정책필드.py` | P1 | 외주 분류 변경 시 재실행 |

## 12. Dependencies

- **선행 필수**: P1 ✅ (resource_loader, schema_pin 34 필드)
- **선행 권장**: P2.5 (Sub-Spec 2 implementation) — estimate_cbm 실행 가능해야 함 / 단, brainstorm 단계는 P2 plan만 있어도 가능
- **후행**: P4 Change Detection이 wave_recommendation·wave_updated_at 활용
- **후행**: P5 Scorecard가 wave assigned vs actual 비교

## 13. 관련 문서

- Master Roadmap: `docs/superpowers/plans/2026-05-27-lane-strategy-master-roadmap-v3.md` §3
- P0 Backtest: `_AutoResearch/SCM/outputs/2026-05-27-lane-strategy-backtest-2026.md`
- P1 plan: `docs/superpowers/plans/2026-05-27-sub-spec-1-resource-mapping-ssot.md`
- P2 plan: `docs/superpowers/plans/2026-05-27-sub-spec-2-cbm-engine.md`
- P3 handoff: `C:\Users\yjisu\.claude\plans\lane-strategy-v3-p3-handoff.md`
- 분석 스크립트: `scripts/analysis/analyze_delivery_slot.py` (25-01~26-05-27, 7,588건)
