# Sincerely SCM

신시어리 포장재 물류팀 SCM 시스템. Airtable 운영 데이터를 Supabase PostgreSQL 불변 원장으로 마이그레이션 중.

## 데이터 정합성 원칙
- Airtable: 운영 입력 레이어 — API로만 읽기, 직접 수정 금지
- Supabase: 불변 원장 — mat_document INSERT ONLY, 수정/삭제 금지
- 재고 정정 = Storno(역분개) 후 재기표. UPDATE/DELETE 절대 금지

## 회계/ERP 기준
- K-IFRS 기준 / 더존 아마란스10 계정코드 체계 (1xxx자산~5xxx비용)
- SAP 이동유형: 101입고 / 201출고 / 261생산출고 / 311이전 / 601납품 / 701조정

## 기술 스택
| 레이어 | 도구 | 상태 |
|--------|------|------|
| 운영 입력 | Airtable (WMS+TMS base) | 운영 중 |
| 불변 원장 | Supabase PostgreSQL (sap 스키마) | 운영 중 |
| 백엔드 | NestJS (PM2, ngrok→Railway 전환 예정) | 운영 중 |
| 파이프라인 | GitHub Actions + Python | 운영 중 |
| TO-BE DB | Supabase 6스키마 51테이블 (설계 완료) | 미적용 |
| 프론트엔드 | Retool (쿼리 설계 완료) | 미적용 |

## 세션 시작
매 세션 시작 시 `/start` 실행 — 진행 상황 확인 후 태스크 1개 선택

## 태스크 관리
`.claude/feature_list.json` — 전체 태스크 목록 (priority: critical > high > medium > low > done)
