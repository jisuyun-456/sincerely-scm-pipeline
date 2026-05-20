# M/H Backfill 셋업 가이드 (입하검수입고 베이스)

본 문서는 `mh_backfill_to_ibsa.py` + `mh-backfill.yml` 활성화 절차.

**현재 상태 (2026-05-20)**: 필드 10개 생성 완료, 스크립트·workflow 작성 완료, **백필 미실행**. 사용자 승인 후 절차대로 진행.

---

## 1. GitHub Secrets 등록 (1회)

Repo Settings → Secrets and variables → Actions → New repository secret

| Secret name | 값 |
|---|---|
| `AIRTABLE_IBSA_PAT` | 입하검수입고 베이스 PAT (data.records:read+write 필수, schema.bases:read+write는 backfill엔 불필요) |
| `AIRTABLE_WMS_PAT` | WMS 베이스 PAT (sync_parts fallback 용, data.records:read만 있으면 됨) |

> **PAT 보안**: 현재 사용 중인 `patAZJZgQcvxAsdRB...` 는 분석 중 채팅에 노출됐음 → 백필 활성화 전 Airtable에서 **재발급 또는 rotate** 후 새 값으로 secret 등록 권장.

---

## 2. 로컬 dry-run (선택, 권장)

`.env` 파일에 추가:
```bash
AIRTABLE_IBSA_PAT=pat...
AIRTABLE_WMS_PAT=pat...
```

```bash
# 1) 최근 10건만 dry-run
python scripts/mh_backfill_to_ibsa.py --limit 10

# 2) 정상이면 W18~현재 전체 dry-run
python scripts/mh_backfill_to_ibsa.py --since 2026-04-18

# 결과 점검: CBM·MH 값이 reasonable한지 콘솔 preview에서 확인
```

---

## 3. 초기 1회 Full Backfill

GitHub Actions → "M/H Backfill" workflow → Run workflow:
- `execute`: **true**
- `full`: **true**
- `since`: `2026-04-18` (또는 비워서 전체)

→ 1회 실행으로 모든 미버전 record가 `v2026-05-cal1` 로 채워짐.

확인:
- Action 로그에서 `patched: N  errors: 0` 확인
- Airtable UI에서 sample 5건 정도 열어서 `CBM`, `MH_*_표준`, `MH_상수버전` 채워짐 확인

---

## 4. Daily Cron 활성화

`.github/workflows/mh-backfill.yml` 편집:
```yaml
on:
  schedule:
    - cron: '0 19 * * *'   # ← 주석 해제
  workflow_dispatch:
    ...
```

commit → push. 매일 04:00 KST 에 신규/누락 record만 자동 채움.

---

## 5. 상수 변경 (calibration 갱신) 시 절차

예: `RECEIVING_MIN_PER_CBM` 4.0 → 5.2 로 변경.

1. `scripts/mh_backfill_to_ibsa.py` 의 `VERSION` 변경 (예: `v2026-05-cal1` → `v2026-06-cal2`)
2. 해당 상수 값 변경
3. `scripts/mh_calculator.py` 동일 상수도 동기 변경 (주간 보고서 정합 유지)
4. workflow_dispatch + `execute=true` + `full=true` 1회 실행 → 전체 덮어쓰기
5. 이후 daily cron이 신규 record를 신규 VERSION으로 자동 채움

> **주의**: VERSION 변경은 immutable ledger 예외 (M/H std는 ledger 데이터 아님). movement 자체는 수정 금지 원칙 유지.

---

## 6. 트러블슈팅

| 증상 | 원인 / 조치 |
|---|---|
| `AIRTABLE_IBSA_PAT secret missing` | GitHub Secrets 미등록 → §1 |
| `403 INVALID_PERMISSIONS_OR_MODEL_NOT_FOUND` | PAT scope 부족 → data.records:read+write 모두 활성화 |
| CBM = 0 record 다수 | `제품 규격` 비어있고 sync_parts lookup도 실패 → `AIRTABLE_WMS_PAT` 미설정 or PT 코드 부재 |
| PATCH error 422 | field type 불일치 → 스크립트 `F[]` 매핑 확인 |
| 동일 record 매일 재패치 | VERSION mismatch — `MH_상수버전` 값 확인 |

---

## 관련 파일

- 필드 스키마: [`docs/airtable_schemas/ibsa_mh_fields.md`](./ibsa_mh_fields.md)
- 백필 스크립트: [`scripts/mh_backfill_to_ibsa.py`](../../scripts/mh_backfill_to_ibsa.py)
- Workflow: [`.github/workflows/mh-backfill.yml`](../../.github/workflows/mh-backfill.yml)
- M/H 계산 로직 원본: [`scripts/mh_calculator.py`](../../scripts/mh_calculator.py)
- Calibration 비교 보고서: [`outputs/MH_calibration_2026-05.md`](../../outputs/MH_calibration_2026-05.md)
