# Lane Strategy Master Roadmap v3 — 자동 배차 스케줄링 시스템

> **For agentic workers:** 이 문서는 *5개 Sub-Spec의 통합 outline + 의존성 + ROI*. 각 Sub-Spec의 *상세 implementation plan*은 진입 시점에 `docs/superpowers/plans/2026-05-27-sub-spec-N-*.md` 형식으로 별도 작성.

> **v1 → v2 → v3 진화:**
> - v1 (폐기): 신규 테이블 2개 over-engineering
> - v2 (commit 0363050): 기존 배송파트너 테이블 + 9 필드 추가 (Sub-Spec 1만)
> - **v3 (현재):** Backtest reality check + 자동 시스템 결정 + 새 조건들(분할 배송 필터·CBM 시점 분기·가정 OTIF·Polling) 반영한 *전체 5 Sub-Spec roadmap*

**Goal:** 신시어리 자체 기사 3명 + 외주 6개사의 *Lane Mix + 통합 적재* 의사결정을 *Airtable polling 기반 DSS*로 자동화. 70~80% 자동 + 20~30% 사용자 수동 검토. 6~10주 개발, 연 0.3~0.7억 절감 목표.

**Architecture (전체 시스템 흐름):**

```
[D-7 ~ D-1 7일 Rolling]
  ↓ Airtable polling 3회/일 (09·14·17시)
[Filter] project IS NOT NULL AND 이동목적 ∈ {고객납품, 생산샘플}
  ↓
[CBM 추정 엔진] 시점 분기 (임가공 전/후) + Product 매칭
  ↓
[Wave 추천 엔진] 자체 기사 capacity + 분할 배송 그룹화 + 시즌 모드
  ↓
[Change Detection] 직전 스캔 대비 신규/변경/취소 감지
  ↓
[Slack 알림 + Airtable wave_recommendation 필드 update]
  ↓ 사용자 검토·수정·승인 (15분/일)
[D-0 출고 실행] 기존 SK-04/05
  ↓
[가정 OTIF 측정] 퀵·자체 = 출하완료 / 택배 = +3일 추정
  ↓
[Scorecard·KPI 자동 산출] 월간 + 분기 RFQ trigger
```

**Tech Stack:**
- Airtable MCP + REST API (polling)
- Python 3.11+ (harness/dispatch/ 모듈)
- harness/_core/notifier.py (Slack tier + 24h dedup)
- pytest + harness-validator

**자동화 목표:** **70~80%** (SAP 글로벌 표준도 프로젝트 기반은 60~80% — 100% 시도 X)

---

## 1. 5 Sub-Spec 통합 흐름 & 의존성

```
Sub-Spec 1 (자원 매핑 SSOT)
  │ 자체 기사 + 외주 master data
  │ (Plan v2 / commit 0363050)
  ↓
Sub-Spec 2 (CBM 추정 엔진) ← 다음 즉시 진행
  │ Shipment 출하 품목 → Product 매칭 → 예상 CBM
  │ 시점 분기 (임가공 전 = 최종 출하 품목 / 후 = 최종 출고 품목 및 수량)
  ↓
Sub-Spec 3 (Wave 추천 엔진) ← Sub-Spec 1+2 후
  │ 자동 대상 필터 + 분할 배송 그룹화 + 7일 rolling 추천
  │ W1 이장훈 / W2 조희선 콘솔 / W3 박종성 trigger
  ↓
Sub-Spec 4 (Change Detection + 가정 OTIF) ← Sub-Spec 3 후
  │ Polling 3회/일 + 변경 감지 + Slack 알림
  │ 가정 기반 OTIF 측정 (퀵 즉시 / 택배 +3일)
  ↓
Sub-Spec 5 (Scorecard + KPI 대시보드)
  │ 월간 5축 평가 + 분기 RFQ trigger + 6개월 ROI 리뷰
```

**총 기간:** 6~10주 (Sub-Spec 간 일부 병렬 가능)

---

## 2. Sub-Spec 상세 Outline

### Sub-Spec 1 — 자원 매핑 SSOT (1~2주) — **이미 Plan v2 완성**

> **상세 plan:** `docs/superpowers/plans/2026-05-27-sub-spec-1-resource-mapping-ssot.md` (commit 0363050)

**핵심:** 기존 배송파트너 테이블에 9 필드 추가 + 19 record 분류 + dispatch_advisor.py 갱신.

**Validation Contract:** C1~C6 (배송파트너 +9 필드 / 자체 기사 3 정책 / 외주 분류 / schema_pin / resource_loader / dispatch_advisor roster).

**진행 시점:** 즉시 가능 (외부 의존성 없음).

---

### Sub-Spec 2 — CBM 추정 엔진 (2~3주) — **다음 진행**

**Goal:** Shipment의 출하 품목 텍스트를 Product 테이블과 매칭해서 *예상 CBM* 산출. 임가공 완료 trigger 시점에 실제 CBM과 비교·재계산.

**입력:**
- `Shipment.최종 출하 품목` (fldgSupj5XLjJXYQo) — 임가공 전
- `Shipment.최종 출고 품목 및 수량` (fldXXnGOXkm90snKn) — 임가공 후
- `Product 테이블 (tblBNh6oGDlTKGrdQ)` — 344 records, Name·견적코드·CBM·박스당 제품수

**알고리즘:**
```python
def estimate_cbm(shipment):
    is_imga_gong_done = bool(shipment.get('Total_CBM'))
    if is_imga_gong_done:
        # 정확값 사용
        return shipment['Total_CBM'], 1.0  # confidence 100%
    
    # 사전 추정
    text = shipment['최종 출하 품목']  # 임가공 전
    items = parse_lines(text)  # [(제품명, 수량), ...]
    # 패턴: "제품명 본수량+여분" → 본+여분 합산
    
    total_cbm = 0.0
    matched_count = 0
    for name, qty in items:
        product = fuzzy_match(name, Product.Name)
        if product:
            total_cbm += product['CBM'] * qty  # 개당 CBM × 수량
            matched_count += 1
    
    confidence = matched_count / len(items) if items else 0
    return total_cbm, confidence  # confidence < 0.7 면 사용자 검토 flag
```

**신규 파일:**
- `harness/dispatch/cbm_estimator.py` — 추정 엔진 + fuzzy matching
- `harness/dispatch/product_loader.py` — Product 테이블 캐시 loader
- `tests/dispatch/test_cbm_estimator.py` — 매칭률·정확도 테스트

**Validation Contract:**
- C1: Product 테이블 344 record 로드 + 캐시
- C2: sample 100건 출하 품목 파싱 정확도 ≥ 95%
- C3: 매칭률 ≥ 70% (전체) + 임가공 완료 케이스는 Total_CBM 우선 사용
- C4: 임가공 trigger (Total_CBM 신규 입력) 시 자동 재계산

**Kill Criteria:** 매칭률 < 50% 또는 추정 오차 > 50% → 사용자 *수동 입력만* 운영, 자동 추정 비활성화.

---

### Sub-Spec 3 — Wave 추천 엔진 (2~3주)

**Goal:** D-7 ~ D-1 범위의 자동 대상 shipment를 *Wave 그룹화*해서 사용자에게 추천. 분할 배송(같은 PNA)·시즌 모드·자체 기사 capacity 모두 고려.

**자동 대상 필터 (2026-05-27 사용자 확정):**
```python
auto_targets = shipments.filter(
    project IS NOT NULL
    AND 이동목적_from_movement_rollup IN ('고객납품', '생산샘플')
    AND 출하확정일 BETWEEN today AND today+7
    AND 발송상태_TMS != '출하 완료'  # 미발송만
)
```

**제외 대상 (사용자 수동):** 재고이동·기타 (project NULL 또는 다른 이동목적).

**알고리즘 (의사코드):**
```python
def recommend_waves(auto_targets):
    # 1. 분할 배송 그룹화 (같은 project_code끼리)
    by_pna = group_by(auto_targets, 'project_code')
    
    # 2. CBM 추정 (Sub-Spec 2 호출)
    for sh in auto_targets:
        sh.estimated_cbm, sh.confidence = estimate_cbm(sh)
    
    # 3. 시즌 모드 (11~2월 = peak / 3~10월 = off-peak)
    mode = 'peak' if is_peak_season(today) else 'off-peak'
    
    # 4. 자체 기사 capacity 조회 (Sub-Spec 1 resource_loader)
    drivers = load_drivers()  # 이장훈/조희선/박종성
    
    # 5. Wave 배정 (priority order)
    wave_plan = {
        'W1_이장훈_AM': [],     # 09시 출발, 수도권 소형 ≤3건
        'W2_조희선_AM': [],     # 09시 출발, 콘솔 ≤6건
        'W3_박종성_flex': [],   # trigger 기반, 전국
        'spillover_고고엑스': [], # peak 시즌 capacity 초과
        'spillover_로젠': [],    # 지방·대형 CBM
    }
    
    for pna, ships in by_pna.items():
        for sh in ships:
            wave = assign_wave(sh, drivers, mode)
            wave_plan[wave].append(sh)
    
    # 6. Airtable Shipment.wave_recommendation 필드 업데이트
    # 7. Slack 알림 (다이제스트)
    return wave_plan
```

**신규 파일:**
- `harness/dispatch/wave_recommender.py` — 메인 추천 로직
- `harness/dispatch/split_detector.py` — 분할 배송 그룹화
- `harness/dispatch/seasonal_mode.py` — 시즌 분기

**Airtable 신규 필드 (Shipment):**
- `wave_recommendation` (singleSelect: W1·W2·W3·spillover_고고엑스·spillover_로젠·수동)
- `wave_confidence` (number 0~1)
- `wave_updated_at` (lastModifiedTime + formula)

**Validation Contract:**
- C1: 자동 대상 필터 정확 (project + 이동목적 조건 일치)
- C2: 분할 배송 케이스 (sample 5건) 정확 그룹화
- C3: 자체 기사 capacity 초과 없음 (이장훈 ≤3 / 조희선 ≤6 / 박종성 ≤8)
- C4: 시즌 모드 정확 분기 (테스트: 1월·5월·11월 케이스)
- C5: 7일 rolling 정확 (오늘 + 7영업일)

**Kill Criteria:** 사용자 추천 수락률 < 50% → 알고리즘 가중치 재조정 또는 추천만 *참고 표시*로 격하.

---

### Sub-Spec 4 — Change Detection + 가정 OTIF (1~2주)

**Goal:** Airtable polling 3회/일로 변경 감지 + 가정 기반 OTIF 자동 측정.

**Polling 스케줄:** 09:00 / 14:00 / 17:00 (영업일) — GitHub Actions cron

**Change Detection 로직:**
```python
def detect_changes():
    current = fetch_active_shipments()  # 자동 대상 필터
    previous = load_snapshot('last_run.json')
    
    changes = {
        'added': [s for s in current if s.id not in previous],
        'modified': [s for s in current if hash(s) != hash(previous[s.id])],
        'removed': [s for s in previous if s not in current],
    }
    
    # 변경 영향 분석
    for sh in changes['modified']:
        if sh.배송방식_changed:
            alert(f"🔔 {sh.SC_id} 배송방식 변경 → wave 재배치 추천")
        if sh.출하확정일_changed:
            alert(f"🔔 {sh.SC_id} 출하일 변경 → wave 그룹 변동")
    
    save_snapshot(current, 'last_run.json')
    return changes
```

**가정 기반 OTIF 모델:**
```python
def estimate_otif(shipment):
    if shipment.배송이슈_기록: return False
    
    if shipment.배송방식 in ['퀵', '자체기사', '바로고']:
        return shipment.출하확정일 <= shipment.약속납기일
    elif shipment.배송방식 == '택배':
        estimated_pod = shipment.출하확정일 + timedelta(days=3)
        return estimated_pod <= shipment.약속납기일
    else:
        return None  # 측정 불가
```

**신규 파일:**
- `harness/dispatch/change_detector.py` — polling + 변경 감지
- `harness/dispatch/otif_estimator.py` — 가정 OTIF
- `.github/workflows/dispatch_polling.yml` — cron (3회/일)

**Validation Contract:**
- C1: 3회/일 polling 안정 실행 (1주 운영 검증)
- C2: 변경 감지 정확 (테스트: shipment 1건 수동 변경 → 알림 도달)
- C3: 가정 OTIF 산출률 ≥ 90% (배송방식 NULL만 제외)

**Kill Criteria:** Polling 실패율 > 10% 또는 알림 fatigue → 빈도 축소 또는 Airtable webhook 검토.

---

### Sub-Spec 5 — Scorecard + KPI + ROI 대시보드 (2~3주)

**Goal:** 월간 carrier·자체 기사 Scorecard + KPI 5종 자동 산출 + 6개월 ROI 검증.

**5축 Scorecard (월 1회):**
- Cost 25% (운임/CBM)
- Reliability 30% (가정 OTIF)
- Capacity 15% (월간 처리 건수·CBM)
- Damage 15% (클레임 건수)
- Flexibility 15% (변경 응답 시간)

**KPI 5개:**
- K-LC-1 비수기 자체 기사 활용도 (Sub-Spec 1 baseline 대비 +20%p ↑)
- K-LC-2 Wave 비중 (70%+ 목표)
- K-LC-3 외주 spillover 비용 (baseline -20%)
- K-LC-4 자율 carrier 단가 추세 (분기 -3%)
- K-LC-5 Scorecard 모든 carrier ≥ 70/100

**신규 파일:**
- `harness/scorecard/calc.py` — 5축 점수 산출
- `harness/scorecard/kpi_dashboard.py` — KPI 5종 + 시계열
- `pages/dashboard.html` 위젯 추가 또는 `sincerely-scm-dashboard/` 신규 페이지

**Validation Contract:**
- C1: 월 1회 자동 산출 (cron)
- C2: 5개 KPI 모두 시계열 차트 표시
- C3: 분기 RFQ trigger 알림 (자율 carrier 단가 추세 기반)
- C4: 6개월 후 실측 ₩ 임팩트 vs 가설 0.3~0.7억 비교 보고서

**Kill Criteria:** 6개월 실측 < 가설 30% → 자동 시스템 ROI 미달, 수동 보조 모드로 격하 검토.

---

## 3. 자동화 한계 명시 (사용자 정직 인정)

### 100% 자동화 불가능한 이유

| 한계 | 사유 | 대응 |
|------|------|------|
| project NULL 케이스 | 재고이동·기타 출하는 의도적 비자동 | 수동 처리 (전체의 ~15%) |
| CBM 매칭 실패 | 신제품·키트 변형·임가공 잔여물 | 사용자 수동 입력 (전체의 ~20%) |
| 임가공 협력사 lock-in | 다영기획 택배·베스트원·로지비는 carrier 변경 불가 | 분류만 자동, 배차는 수동 |
| 변경 빈번한 SC | Day-1 직전 배송방식 변경 多 | Change Detection + 사용자 검토 |
| 신규 패턴 출현 | 시스템 학습 안 된 케이스 | 알고리즘 분기 추가 + 점진 개선 |

**목표 자동화율:** **70~80%** (SAP 글로벌 표준의 프로젝트 기반 운영과 동등)

### SAP vs 신시어리 비교 (사용자 질문 답)

| 측면 | SAP 표준 | 신시어리 v3 |
|------|---------|----------|
| Master Data | 100% 완비 (Product CBM·Customer·Carrier·Rate) | Product 80% / 자체 기사 100% / 외주 95% |
| 시스템 통합 | 한 시스템 (SAP S/4 + EWM + TM) | Airtable + Python + GitHub Actions + Slack |
| 출하 정형성 | 표준화 | 프로젝트별 비정형 (임가공·키트·분할 多) |
| Carrier API | 100% electronic | 로젠 추적만 (POD 자동화 X) |
| POD | electronic 100% | **가정 모델** (퀵=즉시 / 택배=+3일) |
| 도입 비용 | 수십억 + 1~2년 | **0원 + 6~10주** |
| 신시어리 적합도 | 과도한 over-engineering | **규모에 맞음** |

---

## 4. ROI 추정 (보수적)

**비용:**
- 개발 6~10주 (사용자 시간 가치 환산 ~2천만원)
- 운영 매일 15분 (월 5시간)
- 데이터 품질 점진 개선 (별도 비용 작음)

**기대 효과 (연간):**
- 비수기 자체 기사 idle 흡수 자동 감지 → 0.05~0.15억
- 분기 RFQ 단가 협상 (로젠·고고엑스) → 0.15~0.24억
- 통합 적재 차량이용률 ↑ → 0.05~0.10억
- *가시화·SAP 대체* 정성적 가치 = 데이터 자산 + 신규 입사자 가이드

**ROI:** 연 0.25~0.49억 (보수적) ~ 0.30~0.70억 (기대) / 2천만원 투자 → **회수 0.5~1년**

(Backtest 이전 추정 2~3년에서 단축된 이유: CBM 매칭 가능성 + 자동 대상 필터로 ROI 집중)

---

## 5. 진행 일정 (제안)

| Sub-Spec | 기간 | 시작 trigger |
|---------|------|----------|
| Sub-Spec 1 자원 매핑 | 1~2주 | **즉시** (Plan v2 ready) |
| Sub-Spec 2 CBM 엔진 | 2~3주 | Sub-Spec 1 완료 후 |
| Sub-Spec 3 Wave 추천 | 2~3주 | Sub-Spec 1+2 완료 후 |
| Sub-Spec 4 Change + OTIF | 1~2주 | Sub-Spec 3과 일부 병렬 |
| Sub-Spec 5 Scorecard | 2~3주 | Sub-Spec 3 완료 후 |

**총 6~10주** (병렬 진행 시 단축)

**중간중간 조율 포인트:**
- Sub-Spec 1 완료 후 → Sub-Spec 2 brainstorm (CBM 매칭률 실측 → 알고리즘 조정)
- Sub-Spec 3 완료 후 → 1주 라이브 운영 → 사용자 수락률 확인 → Sub-Spec 4 진입 결정
- Sub-Spec 5 완료 6개월 후 → ROI 실측 vs 가설 → 시스템 확장/축소 결정

---

## 6. Validation Contract 통합 (v3 전체)

| Sub-Spec | Contract | 핵심 통과 기준 |
|---------|---------|----------|
| 1 | C1~C6 | 배송파트너 SSOT + dispatch_advisor 정정 |
| 2 | C1~C4 | CBM 매칭률 ≥ 70% + 임가공 trigger 재계산 |
| 3 | C1~C5 | 자동 대상 필터 + 분할 그룹화 + capacity 초과 0건 |
| 4 | C1~C3 | Polling 안정 + 변경 감지 + 가정 OTIF 90% |
| 5 | C1~C4 | 월간 Scorecard + KPI 시계열 + 6개월 ROI 보고 |

**총 22개 Validation Contract** — 각 Sub-Spec 종료 시 자동 검증 스크립트로 PASS 확인.

---

## 7. Out of Scope (v3 범위 외 — 향후 결정)

- 실시간 Airtable webhook (현재는 polling 3회/일)
- 로젠 API 자동 POD 연동 (현재는 가정 모델)
- 신규 carrier 발굴 (현재 6개사로 충분)
- 통합 적재 차량 routing 최적화 (VRP 알고리즘 — H2~H3 후보)
- ML 기반 wave 추천 (단순 rule-based 우선)
- 모바일 앱 (운영자 데스크톱 + Slack DM으로 충분)

---

## 8. 관련 문서

- **Design doc:** `_AutoResearch/SCM/outputs/2026-05-27-driver-lane-consolidation-strategy.md`
- **Backtest:** `_AutoResearch/SCM/outputs/2026-05-27-lane-strategy-backtest-2026.md`
- **Sub-Spec 1 plan (v2):** `docs/superpowers/plans/2026-05-27-sub-spec-1-resource-mapping-ssot.md` (commit 0363050)
- **모체 전략:** `_AutoResearch/SCM/outputs/SCM-FinanceStrategy-2026-05-21.md` + `SCM-FinanceStrategy-16Cards-2026-05-22.md`

---

> **다음 즉시 액션:** 
> 1. Sub-Spec 1 plan v2 실행 (subagent-driven 또는 inline) 또는
> 2. Sub-Spec 2 brainstorming 진입 (CBM 엔진 — Product 매칭 알고리즘 깊이 설계)
> 사용자 선택 대기.
