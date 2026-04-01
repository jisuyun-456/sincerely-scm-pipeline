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
| 테이블 탐색 | NocoDB (localhost:8080) | 미적용 |
| 대시보드 | Metabase (localhost:3000) | 미적용 |

## 전환 로드맵
Airtable(AS-IS) → Supabase 51테이블 + NocoDB/Metabase UI + NestJS 백엔드 + 더존 아마란스10 연계(TO-BE)
현재 위치: Shadow Ledger 운영 중 (Airtable webhook → NestJS → Supabase sap 스키마)

## 에이전트 팀 라우팅

### 프로젝트 특화 에이전트 (세밀한 키워드 우선)

| 키워드 | 에이전트 |
|--------|---------|
| 품목코드, 로케이션, 공급사, 바코드, ROP | wms-master-data (SK-01) |
| 입하, 검수, GR, ASN, AQL, Dock-to-Stock | wms-inbound (SK-02) |
| 재고 불일치, 사이클카운팅, 음수재고, ADJUST | wms-inventory (SK-03) |
| 피킹, 패킹, Wave, SSCC, 출고지시 | wms-outbound (SK-04) |
| 운송장, 택배, 배송추적, POD | tms-shipment (SK-05) |
| OTIF, KPI 달성률, Dock-to-Stock 시간 | tms-otif-kpi (SK-06) |
| 반품, 역물류, RESTOCK, DISPOSE | wms-return (SK-07) |
| 회의록, 회의 분석, 액션아이템 | meeting-analysis (SK-08) |

### 범용 전문가 에이전트 (일반 키워드)

| 키워드 | 에이전트 |
|--------|---------|
| 재고 전략, 물류 컨설팅, SCM 개선, 공급망 | scm-logistics-expert (D1) |
| 분개, 전표, 세금, 기간마감, K-IFRS, 더존 | tax-accounting-expert (D2) |
| 코드, API, DB, 배포, 아키텍처, 성능 | tech-architect (D3) |
| UI, 디자인, CSS, 접근성, 컴포넌트 | frontend-design-expert (D4) |
| 프로젝트 계획, 리스크, KPI, MECE, 일정 | project-manager (D5) |
| 복합 요청, 종합 분석, 제안서, 전체 리뷰 | orchestrator |

> **라우팅 우선순위:** 프로젝트 특화(세밀한 키워드) > 범용 전문가(일반 키워드)

## 태스크 관리
`.claude/feature_list.json` — 전체 태스크 목록 (priority: critical > high > medium > low > done)
