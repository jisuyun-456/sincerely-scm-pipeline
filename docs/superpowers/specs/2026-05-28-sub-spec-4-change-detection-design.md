# Sub-Spec 4 Design — Change Detection + 가정 OTIF

> Chain: lane-strategy-v3 | Phase: P4 | Date: 2026-05-28
> 의존: P3.5 (wave_recommender.py, wave_recommender.yml, audit_log.py)

---

## 1. Context

Sub-Spec 3(Wave 추천 엔진)은 Airtable Shipment를 3회/일 polling해서 wave 배정 결과를 PATCH하고 Slack 다이제스트를 발송한다. Sub-Spec 4는 이 파이프라인에 두 기능을 추가한다:

1. **Change Detection** — 직전 스캔 대비 신규 TO 생성·취소·Critical 필드 변경 감지 → Slack 알림
2. **가정 OTIF** — 아직 배송 완료되지 않은 auto-target shipment에 대해 배송방식별 가정으로 납기 준수 여부 예측 → Slack 다이제스트 + JSONL 로그

실제 OTIF는 기존 Airtable OTIF 테이블(formula 자동 계산)이 담당하므로 Airtable 스키마 변경 없음.

---

## 2. Architecture

```
wave_recommender.yml (KST 09/14/17 영업일)
  │
  Step 1. download artifact → dispatch_snapshot.json
           (직전 스캔 결과, 첫 실행 시 빈 dict)
  │
  Step 2. change_detector.detect(snapshot, current_shipments)
           → ChangeReport(added, removed, critical_modified, minor_modified)
  │
  Step 3. assign_waves(current_shipments)        ← P3.5 기존 그대로
           → WavePlan
  │
  Step 4. otif_estimator.estimate_all(current_shipments)   ← in-memory
           → list[OtifResult]
           → append → assumed_otif.jsonl
  │
  Step 5. Slack digest
           [변경] 🆕 N건 신규 | 🚫 M건 취소 | ⚠️ K건 변경
           [OTIF] W1 4건 중 3건 납기 준수 예상 ✅ / 1건 위험 ⚠️
           (변경 0건이면 변경 섹션 생략)
  │
  Step 6. upload artifact → dispatch_snapshot.json
           (이번 스캔 결과, 90일 TTL)
```

---

## 3. Change Detection

### 3.1 스냅샷 포맷

`dispatch_snapshot.json` — Airtable record ID를 키로 하는 dict.

```json
{
  "rec123": {
    "출하확정일": "2026-06-03",
    "배송방식": "택배",
    "수령인주소": "서울시 강남구",
    "발송상태": "배송준비"
  }
}
```

비교 대상 필드만 저장 (용량 최소화).

### 3.2 변경 분류

| 이벤트 | 분류 | Slack 표시 |
|---|---|---|
| record ID가 snapshot에 없음 | **added** (Critical) | 🆕 신규 |
| `발송상태_TMS` → 취소/반품/회수 | **removed** (Critical) | 🚫 취소 |
| `출하확정일` 변경 | **critical_modified** | ⚠️ 출하일 변경 |
| `배송 방식` 변경 | **critical_modified** | ⚠️ 배송방식 변경 |
| `수령인(주소)` 변경 | **critical_modified** | ⚠️ 주소 변경 |
| `estimated_cbm` 변동 | **minor_modified** | (다이제스트에만) |
| 기타 필드 변경 | 무시 | — |

### 3.3 인터페이스

```python
# harness/dispatch/change_detector.py

@dataclass
class ChangeReport:
    added: list[str]            # record IDs
    removed: list[str]          # record IDs
    critical_modified: list[dict]  # [{id, field, old, new}]
    minor_modified: list[dict]

def detect(
    snapshot: dict[str, dict],
    current: list[dict],
) -> tuple[ChangeReport, dict[str, dict]]:
    """
    Returns (ChangeReport, new_snapshot).
    new_snapshot은 caller가 artifact로 업로드.
    """
```

---

## 4. 가정 OTIF

### 4.1 계산 규칙

| 조건 | assumed_pod | on_time |
|---|---|---|
| POD_확인일시 있음 | skip (실제 OTIF 테이블이 처리) | None |
| 약속납기일 NULL | — | None (측정불가) |
| 배송방식 NULL | — | None (측정불가) |
| 배송방식 = 퀵 / 자체기사 / 바로고 | 출하확정일 당일 | 출하확정일 ≤ 약속납기일 |
| 배송방식 = 택배 / 로젠 | `add_logen_days(출하확정일, 3)` | assumed_pod ≤ 약속납기일 |

### 4.2 add_logen_days 규칙

로젠 SLA = 월~토 배송 (일요일 휴무). `add_logen_days(start, n)` — `start`로부터 일요일(weekday=6)만 건너뛰며 n일 진행.

예시:
- 금요일 출하 → 토(+1) → 일 skip → 월(+2) → 화(+3) = **화요일** 도착
- 토요일 출하 → 일 skip → 월(+1) → 화(+2) → 수(+3) = **수요일** 도착
- 일요일 출하 → 월(+1) → 화(+2) → 수(+3) = **수요일** 도착

### 4.3 JSONL 로그 포맷

`_AutoResearch/SCM/outputs/audit_log/assumed_otif.jsonl` — append-only.

```json
{"ts": "2026-05-28T09:00:00", "sc_id": "SC-2026-001", "출하확정일": "2026-05-28", "약속납기일": "2026-05-30", "assumed_pod": "2026-05-30", "on_time": true, "method": "로젠+3일"}
```

P5 Scorecard가 이 파일을 읽어 월간 가정 OTIF 집계.

### 4.4 인터페이스

```python
# harness/dispatch/otif_estimator.py

@dataclass
class OtifResult:
    sc_id: str
    on_time: bool | None
    assumed_pod: date | None
    method: str  # "당일" | "로젠+3일" | "측정불가"

def estimate_all(shipments: list[dict]) -> list[OtifResult]:
    """in-memory 계산. 결과를 JSONL에 append하고 list 반환."""

def otif_summary_by_wave(
    results: list[OtifResult],
    wave_plan: WavePlan,
) -> dict[str, dict]:
    """
    {"W1": {"total": 4, "on_time": 3, "at_risk": 1},
     "W2": ..., "수동": ...}
    wave_recommender.py Slack digest에서 사용.
    """
```

---

## 5. Scheduling 변경

`harness/dispatch/scheduling.py`에 추가:

```python
def add_logen_days(start: date, days: int) -> date:
    """출하확정일 + N일 (일요일 skip). 로젠 SLA 기준."""
    d, remaining = start, days
    while remaining > 0:
        d += timedelta(days=1)
        if d.weekday() != 6:  # 6 = Sunday
            remaining -= 1
    return d
```

---

## 6. wave_recommender.py 변경

`__main__` 블록 orchestration 순서 변경 (~30 LOC 추가):

```python
# 기존: fetch → assign → patch → notify
# 변경: download_snapshot → fetch → detect → assign → estimate_otif → patch → notify → upload_snapshot
```

artifact 다운로드/업로드는 GitHub Actions 스텝에서 처리 (파이썬 코드 외부). `wave_recommender.py`는 `SNAPSHOT_PATH` 환경변수로 파일 경로를 받아 읽고 쓰기만 함.

---

## 7. GitHub Actions 변경

`wave_recommender.yml`에 스텝 2개 추가:

```yaml
- name: Download snapshot
  uses: actions/download-artifact@v4
  with:
    name: dispatch-snapshot
    path: /tmp/snapshot
  continue-on-error: true  # 첫 실행 시 artifact 없어도 OK

- name: Run wave recommender
  run: python -m harness.dispatch.wave_recommender
  env:
    SNAPSHOT_PATH: /tmp/snapshot/dispatch_snapshot.json
    # ... 기존 env 그대로

- name: Upload snapshot
  uses: actions/upload-artifact@v4
  with:
    name: dispatch-snapshot
    path: /tmp/snapshot/dispatch_snapshot.json
    retention-days: 90
```

---

## 8. Validation Contract

| ID | 계약 | 검증 방법 | 기준 |
|---|---|---|---|
| C1 | 신규 TO 감지 정확 | pytest — snapshot에 없던 ID 추가 → `added` 포함 | 100% |
| C2 | 취소·Critical 변경 감지 | pytest — 발송상태/출하확정일/배송방식/주소 변경 케이스 4개 | 4/4 PASS |
| C3 | `add_logen_days` 일요일 skip | pytest — 금요일→화요일, 토요일→수요일, 일요일 출하→수요일 | 3/3 PASS |
| C4 | OTIF 계산 4케이스 | pytest — 퀵/택배/NULL납기/이미POD | 4/4 PASS |
| C5 | JSONL append-only | pytest — 동일 sc_id 2회 estimate → 2줄 기록 | 중복 없음 |

---

## 9. Out of Scope (P4.5 이후)

- 실제 1주 운영 검증 (C1 GitHub Actions 연동 실행)
- Airtable 실 PATCH 통합 테스트 (AIRTABLE_PAT 필요)
- P5 Scorecard assumed_otif.jsonl 집계 스크립트

---

## 10. Dependencies

| 선행 | 설명 |
|---|---|
| P3.5 `wave_recommender.py` | `fetch_auto_targets`, `assign_waves`, `WavePlan` 타입 재사용 |
| P3.5 `audit_log.py` | JSONL 패턴 참조 |
| P2.5 `scheduling.py` | `add_logen_days` 추가 위치 |
| Airtable schema_pin | 필드 ID 참조 (변경 없음) |

## 11. Risks

| 리스크 | 대응 |
|---|---|
| artifact 첫 실행 시 없음 | `continue-on-error: true` + 빈 snapshot dict fallback |
| artifact 90일 만료 후 갭 | 만료 → 첫 실행처럼 전체 현재 shipment를 신규로 처리 (false positive 1회) — 운영 허용 범위 |
| 배송방식 rollup 값이 예상치 못한 문자열 | `method = "측정불가"` fallback |
