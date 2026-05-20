# 입하검수입고 베이스 — M/H 필드 스키마

**Base**: `app6DGHCPI3Yh3IFS` (입하검수입고 베이스, sERPA 3.0 → Airtable sync)
**Table**: `tblhzYiltSBm6vxBz` (sync_movement)
**생성일**: 2026-05-20
**관련 보고서**: `outputs/MH_calibration_2026-05.md` (CBM-driven 채택 결정)

---

## CBM-driven 표준 M/H 필드 (Python 백필)

| # | 필드명 | fieldId | 타입 | 산식/입력 |
|---|---|---|---|---|
| 1 | `CBM` | `fldTHmNEPNhcIX5AQ` | number(6) | 제품 규격(W×H×D mm) × 입하수량 → m³ |
| 2 | `MH_입하_표준` | `fld5ZybpbcpEaDkEt` | number(2) | CBM × 4.0 × 1.15 |
| 3 | `MH_검수_표준` | `fldue4gsBUJIEbGTP` | number(2) | 2.5 × 1.15 = 2.875 |
| 4 | `MH_입고_표준` | `fldy6Z6durcP0CWFx` | number(2) | (3.0 + min(7, CBM×7)) × 1.15 |
| 5 | `MH_합계_표준` | `fldmhIVSe5lSkfZhn` | number(2) | 2 + 3 + 4 |
| 6 | `MH_상수버전` | `fld1UjVS3uM7ii7Cy` | text | calibration 버전 (예: `v2026-05-cal1`) |

> 전부 `scripts/mh_backfill_to_ibsa.py` 가 매일 cron으로 채움. Airtable formula 미사용 — sync_parts cross-base lookup이 Python에서만 가능.

## 프리패키징 측정 필드 (현장 직접 입력 + 자동 계산)

| # | 필드명 | fieldId | 타입 | 입력 |
|---|---|---|---|---|
| 7 | `프리패키징_시작시간` | `fldhdaMnswcVJJx35` | dateTime (KST) | 현장 작업자 |
| 8 | `프리패키징_완료시간` | `fldzKdT7keCSSfOQE` | dateTime (KST) | 현장 작업자 |
| 9 | `프리패키징_인원수` | `fldKGjltx98XCUgIp` | number(0) | 현장 작업자 |
| 10 | `MH_프리패키징_실측` | `fldbqG1AG9dsuPFUa` | formula | `(완료-시작 분) × 인원수` |

### 10번 formula
```
IF(
  AND({프리패키징_시작시간}, {프리패키징_완료시간}, {프리패키징_인원수}),
  DATETIME_DIFF({프리패키징_완료시간}, {프리패키징_시작시간}, 'minutes') * {프리패키징_인원수},
  BLANK()
)
```

---

## 백필 정책

- **Idempotency**: Python 스크립트는 `MH_상수버전 ≠ 현재 버전` 또는 BLANK인 record만 PATCH
- **빈도**: GitHub Actions daily cron (04:00 KST)
- **초기 백필**: 1회 full pass (W18~현재 ~752 records), `--full` 플래그 사용
- **상수 변경 시**: `MH_상수버전` 갱신 → 다음 cron이 자동으로 모든 record 덮어쓰기
- **Immutable Ledger 예외**: M/H 표준값은 ledger 데이터가 아니므로 UPDATE 허용 (movement 자체는 수정 X)

## 관련 파일

- 백필 스크립트: `scripts/mh_backfill_to_ibsa.py`
- Cron config: `.github/workflows/mh-backfill.yml`
- M/H 계산 로직 (원본): `scripts/mh_calculator.py`
- 비교 분석 보고서: `outputs/MH_calibration_2026-05.md`
- 주간 보고서 (CBM-driven 집계): `outputs/MH-YYYY-Wxx.md`
