# WMS AutoResearch — Program

> 시작: 2026-04-21 | 기반: Airtable WMS 베이스 (`appLui4ZR5HWcQRri`) 읽기 전용  
> 목표: 스키마 변경 없이 현황 가시화 → Phase 0 착수 근거 확보

---

## 분석 범위 (AS-IS, 3 KPI)

| KPI | 테이블 | 핵심 필드 | 실제 결과물 |
|-----|--------|----------|-----------|
| QC 불량 proxy | order | 표본 검수 결과 (singleSelect) | 주간 불합격률 (코드 분류 불가) |
| 입출고 볼륨 트렌드 | movement | 이동목적, 생성일자 | 입고/출고 건수 주간 트렌드 |
| 공급사 납기 proxy | order | 입고예정일, 실제 입고일 | 공급사별 평균 납기 편차 |

**한계:** 개선 도구가 아닌 현황판. Phase 0 (SAP_이동유형 1개 필드) 완료 시 정확도 대폭 향상.

---

## 테이블/필드 ID 레퍼런스

### WMS Base: `appLui4ZR5HWcQRri`

| 테이블 | ID |
|--------|-----|
| movement | `tblwq7Kj5Y9nVjlOw` |
| order | `tblJslWg8sYEdCkXw` |
| sync_partner | `tblXx85u5gNzK7zTf` |
| material(parts-stock) | `tblaRpZstW10EwDlo` |
| sync_parts | `tblzJh0V4hdo4Xbvx` |

### movement 핵심 필드

| 필드명 | ID | 타입 |
|--------|-----|------|
| 이동목적 | `fldFRNxG1pNooEOC7` | singleSelect |
| 생성일자 | `fldDXUAF4JOORLJ2v` | dateTime |
| 실제입하일 | `flduN8khmYwdn7uVD` | date |
| 검수 status | `fldLpIDZBmq9jKYCh` | multilineText |
| 입고자재_검수 status | `fldwIZKLqVgYFq0M0` | multilineText |
| 이동수량(변경) | `fld8i5WLz1UNmzvvB` | number |

### order 핵심 필드

| 필드명 | ID | 타입 |
|--------|-----|------|
| 입고예정일 | `fldjhWR2fGbp8hOn5` | date |
| 실제 입고일 (발주팀 작성) | `fld7NwzcwyjoCldle` | date |
| 협력사 | `fldsofqeebz4UnCRN` | singleLineText |
| 표본 검수 결과 | `fldDlQdAT6L25QxEb` | singleSelect |
| 발주단계 | `fldBlcddggQhkp7dm` | singleSelect |

---

## Iteration 계획

| Iter | 주제 | 상태 |
|------|------|------|
| Iter 1 | 재고·입출고 baseline (볼륨 트렌드) | 예정 |
| Iter 2 | QC 불량 패턴 분석 (표본 검수 결과 + 검수 status 텍스트) | 예정 |
| Iter 3 | 공급사 납기 편차 분석 (입고예정일 vs 실제 입고일) | 예정 |
| Iter 4 | 종합 현황판 + Phase 0 착수 권고 | 예정 |

---

## 성공 기준

- 4주 연속 GitHub Actions 자동 실행
- 주간 리포트 3 KPI 수치 자동 생성
- Iter 3 완료 후 납기 지연 공급사 Top 3 파악
