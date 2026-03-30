# Sincerely SCM

신시어리 포장재 물류팀 SCM 시스템. Airtable 운영 데이터를 Supabase PostgreSQL 불변 원장으로 마이그레이션 중.

## 이 프로젝트 열면 자동 실행
다른 것보다 먼저, 아래 3개를 즉시 실행할 것:
1. `cat .claude/claude-progress.txt` → 이전 세션 파악
2. `cat .claude/feature_list.json` → 미완료 태스크 파악
3. `git log --oneline -5` → 최근 작업 히스토리 확인
실행 후 "현재 상태 요약 + 다음 추천 태스크 1개"를 나에게 말해줄 것.
세션 종료 시: git commit + claude-progress.txt 업데이트 필수.

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

## 전환 로드맵
Airtable(AS-IS) → Supabase 51테이블 + NestJS 백엔드 + 더존 아마란스10 연계(TO-BE)
현재 위치: Shadow Ledger 운영 중 (Airtable webhook → NestJS → Supabase sap 스키마)

## 태스크 관리
`.claude/feature_list.json` — 전체 태스크 목록 (priority: critical > high > medium > low > done)
