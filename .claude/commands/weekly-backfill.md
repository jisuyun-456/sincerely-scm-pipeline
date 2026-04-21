# 주간 TMS/WMS 데이터 정합성 체크 & 백필

매주 **월~화요일** 전주(Mon~Sun) 기준으로 실행하는 루틴.

---

## 실행 순서

### 1. 배송요청 → Shipment 미연결 체크 (TMS)
```bash
python scripts/check_배송요청_미연결.py                    # 2026-04-01 이후 기본
python scripts/check_배송요청_미연결.py --from 2026-03-01   # 시작일 직접 지정
python scripts/check_배송요청_미연결.py --all               # 전체 (느림)
```
결과: `reports/배송요청_미연결_YYYY-MM-DD.csv`
→ 출력된 logistics_PK 목록을 Airtable에서 열어 Shipment 수동 연결 여부 결정.

---

### 2. TMS 테이블 백필 (배차일지 / OTIF / 배송이벤트 / 택배추적로그)
```bash
# dry-run 먼저 (실제 쓰기 없이 대상 확인)
python scripts/tms_weekly_backfill.py --dry-run

# 이상 없으면 실제 실행
python scripts/tms_weekly_backfill.py

# 특정 항목만
python scripts/tms_weekly_backfill.py --mode dispatch,otif

# 날짜 직접 지정
python scripts/tms_weekly_backfill.py --start 2026-04-14 --end 2026-04-20
```
결과: `reports/backfill_YYYY-MM-DD.log`

백필 항목별 트리거 조건:
| 항목 | 트리거 |
|------|--------|
| 배차일지 | 내부기사 배정됐으나 배차일지 미생성 |
| OTIF | 출하완료인데 OTIF 레코드 없음 |
| 배송이벤트 | 배송이벤트 레코드 없음 |
| 택배추적로그 | 운송장 있는데 추적로그 없음 |

---

### 3. 고객납품 ↔ TO 정합성 체크 (WMS/SERPA)
```bash
python scripts/check_고객납품_TO정합성.py           # 전주 기준
python scripts/check_고객납품_TO정합성.py --weeks 2  # 최근 2주
python scripts/check_고객납품_TO정합성.py --start 2026-04-07 --end 2026-04-13
```
결과: `reports/고객납품_TO정합성_YYYY-MM-DD.md`

3가지 체크:
1. **TO 미연결** — logistics_release 비어 있는 고객납품 MM
2. **프로젝트별 TO 부분 누락** — 같은 PNA 프로젝트 내 일부 MM만 TO 연결
3. **단일 MM에 복수 TO** — logistics_release에 TO 번호가 여러 개

---

## 스크립트 위치

| 스크립트 | 용도 |
|---------|------|
| `scripts/check_배송요청_미연결.py` | Task 1 — TMS 배송요청 미연결 조회 |
| `scripts/tms_weekly_backfill.py` | Task 2 — TMS 백필 통합 실행기 |
| `scripts/backfill/backfill_배차일지.py` | Task 2 모듈 |
| `scripts/backfill/backfill_otif.py` | Task 2 모듈 |
| `scripts/backfill/backfill_배송이벤트.py` | Task 2 모듈 |
| `scripts/backfill/backfill_택배추적로그.py` | Task 2 모듈 |
| `scripts/check_고객납품_TO정합성.py` | Task 3 — WMS TO 정합성 체크 |

## 환경변수

```
AIRTABLE_PAT=patU9ew1rwbJbEpOn...
```
`.env` 파일에 설정하거나 환경변수로 제공.
