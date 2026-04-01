# Sincerely SCM

신시어리 포장재 물류팀 SCM 시스템.
Airtable 운영 데이터를 Supabase PostgreSQL 불변 원장으로 전환 중.

## 프로젝트 개요

Airtable(AS-IS) → Supabase 6스키마 51테이블 + NocoDB/Metabase UI + NestJS 백엔드 + 더존 아마란스10 연계(TO-BE)

**현재 위치:** Shadow Ledger 운영 중 (Airtable webhook → NestJS → Supabase sap 스키마)

## 기술 스택

| 레이어 | 도구 | 상태 |
|--------|------|------|
| 운영 입력 | Airtable (WMS+TMS base) | 운영 중 |
| 불변 원장 | Supabase PostgreSQL (sap 스키마) | 운영 중 |
| 백엔드 | NestJS (PM2, Railway 전환 예정) | 운영 중 |
| 파이프라인 | GitHub Actions + Python | 운영 중 |
| TO-BE DB | Supabase 6스키마 51테이블 | 설계 완료 |
| 테이블 탐색 | NocoDB | 미적용 |
| 대시보드 | Metabase / Retool | 운영 중 (Retool 10페이지) |

## 핵심 설계 원칙

- **INSERT ONLY 원장** — mat_document, stock_balance, inventory_transaction은 수정/삭제 금지
- **Storno(역분개) 정정** — 재고 정정은 역분개 후 재기표
- **K-IFRS 기준** — 더존 아마란스10 계정코드 체계 (1xxx자산~5xxx비용)
- **SAP 이동유형** — 101입고 / 201출고 / 261생산출고 / 311이전 / 601납품 / 701조정

## 디렉토리 구조

```
SCM_WORK/
├── .claude/                      # Claude Code 설정
│   ├── agents/                   # 전문가 에이전트 (14개)
│   │   ├── scm-logistics-expert.md    # D1 SCM/물류 (APICS/SCOR/SAP/GS1)
│   │   ├── tax-accounting-expert.md   # D2 세무/회계 (K-IFRS/더존/CPA)
│   │   ├── tech-architect.md          # D3 기술 아키텍트 (SOLID/DDD)
│   │   ├── frontend-design-expert.md  # D4 프론트엔드 (WCAG/Atomic)
│   │   ├── project-manager.md         # D5 PM (BCG/McKinsey/PMBOK)
│   │   ├── orchestrator.md            # 전문가 조합 오케스트레이터
│   │   └── wms-*.md / tms-*.md        # 프로젝트 특화 에이전트 (SK-01~SK-08)
│   ├── commands/                 # 슬래시 커맨드 (13개)
│   ├── skills/                   # 도메인별 스킬
│   │   ├── scm/                  # SAP 이동유형, SCOR, PDF
│   │   ├── accounting/           # K-IFRS 분개, 기간마감, 3-Way Match
│   │   ├── tech/                 # DB 정합성, 쿼리 최적화
│   │   ├── design/               # WCAG 접근성 감사
│   │   └── pm/                   # MECE 분해, 리스크 레지스터
│   ├── hooks/                    # 자동화 훅 (SQL 안전 검사)
│   └── settings.json             # 프로젝트 권한/훅 설정
├── nestjs-backend/               # NestJS 백엔드 (Shadow Ledger)
├── supabase/                     # Supabase 스키마/마이그레이션
├── airtable-pipeline/            # Airtable → Supabase 동기화 파이프라인
├── retool/                       # Retool UI 설정/쿼리 문서
├── wms/                          # WMS 도메인 문서
├── tms/                          # TMS 도메인 문서
├── docs/                         # 프로젝트 문서
│   ├── claude-code-layers.md     # Claude Code 레이어 구조 가이드
│   ├── deployment_guide.md       # 배포 가이드
│   └── data_dictionary.md        # 데이터 사전
└── CLAUDE.md                     # 프로젝트 규칙서
```

## Claude Code 레이어 구조

이 프로젝트는 6개 레이어로 Claude Code를 체계적으로 설정:

| 레이어 | 역할 | 설정 위치 |
|--------|------|-----------|
| 1. CLAUDE.md | 프로젝트 규칙/컨텍스트 | `CLAUDE.md` |
| 2. Harness | 자동화 (hooks) | `.claude/settings.json` |
| 3. Skills & Commands | 도메인별 워크플로우 | `.claude/skills/`, `.claude/commands/` |
| 4. Subagent | 독립 작업 위임 | `Agent tool` |
| 5. Team Agent | 전문가 에이전트 14개 | `.claude/agents/` |
| 6. Orchestration | 다수 에이전트 병렬 조율 | `orchestrator.md` |

상세 가이드: [docs/claude-code-layers.md](docs/claude-code-layers.md)

## 태스크 관리

`.claude/feature_list.json` — 전체 태스크 목록 (priority: critical > high > medium > low > done)

## 참고

- 회계 기준: K-IFRS / 더존 아마란스10
- 물류 표준: APICS CSCP+CPIM+CLTD / SCOR / GS1
- SAP: EWM(창고) / TM(운송) / MM(자재) / FI(재무) / CO(관리회계)
