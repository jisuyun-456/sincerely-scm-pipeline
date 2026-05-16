# Sincerely SCM

신시어리 포장재 물류팀 SCM 시스템 — Airtable WMS+TMS 운영(SAP 기준 프로세스).

## 이 프로젝트 열면 자동 실행
1. `git log --oneline -10` 실행 → 최근 작업 히스토리 확인
2. **`obsidian-routing` 스킬 자동 호출** → `ClaudeVault/SCM/_AutoResearch/wiki/log.md` 마지막 항목 읽기 → 이전 세션 컨텍스트 복원 (SessionStart 훅이 최근 3개 미리 표시함, 자세한 내용 필요 시 직접 Read)
3. "현재 상태 요약 + 다음 추천 태스크 1개" 보고

## 세션/Task 종료 시 (누락 금지)
1. **Obsidian log.md 저장** — `obsidian-routing` 스킬 호출 → `ClaudeVault/SCM/_AutoResearch/wiki/log.md`에 `## [YYYY-MM-DD] {타입} | {제목}` 추가 (결정·완료·이슈·다음 할 일)
2. **outputs/ 산출물** — 분석 결과·리포트는 `SCM/_AutoResearch/outputs/`에 저장 + `index.md` 링크 갱신
3. **git commit 필수**
4. Stop 훅이 자동으로 git status / 미커밋 경고 표시

## 데이터 정합성 원칙 (Immutable Ledger)
- Airtable: 운영 입력 레이어 — API로만 읽기/쓰기, 직접 UI 수정 금지
- movement / mat_document: **INSERT ONLY** — UPDATE/DELETE 절대 금지
- 정정 = Storno(역분개) 또는 보정 레코드로만 처리
- (글로벌 CLAUDE.md "공통 데이터 원칙" 동일 준수)

## 회계/ERP 기준
- K-IFRS / 더존 아마란스10 계정코드 (1xxx자산~5xxx비용)
- SAP 이동유형: 101입고 / 201출고 / 261생산출고 / 311이전 / 601납품 / 701조정 / 122반품입고 / 551폐기

## 기술 스택 (현재 운영)
| 레이어 | 도구 |
|--------|------|
| 운영 입력 | Airtable (WMS base appLui4ZR5HWcQRri / TMS base app4x70a8mOrIKsMf) |
| 백엔드 (PDF 등) | FastAPI on Railway (`api/app.py`) |
| 파이프라인 | GitHub Actions + Python |
| 회의록 백업 | *(향후 구현 예정 — Phase 3+)* meeting-analysis SK-08 + Obsidian append. 현재 PostToolUse 훅은 `.py` syntax check만 수행. |
| 대시보드 (별도 레포) | `sincerely-scm-dashboard`: React on Vercel + Supabase + GitHub Actions cron |

> **ClaudeVault 경로:** `C:\Users\yjisu\Documents\ClaudeVault\` (obsidian-routing 스킬 + SessionStart 훅이 자동 참조). SCM 작업 로그: `ClaudeVault/SCM/_AutoResearch/wiki/log.md`

> **Supabase 정책 (2026-05-08 갱신):** SCM 운영 데이터(WMS/TMS movement·inventory)는 Airtable이 단일 진실 원천 — 절대 Supabase로 이중화 금지. 대시보드 전용 스냅샷·집계 데이터에 한해 `sincerely-scm-dashboard` 서브프로젝트에서만 Supabase free tier 허용.
> NocoDB / Metabase / Retool 은 계속 미사용 (메모리 `project_scm_redesign` 참조).

## 언어 설정

L1 `~/.claude/CLAUDE.md` "Always respond in English" 정책을 **상속**. 예외:
- 회의록·운영 보고서·도메인 한정 산출물(SK-08 meeting-analysis 산출 등): 한국어 허용
- 사용자가 명시적으로 "한국어로" 요청한 즉시 응답: 한국어 허용

## 전문가 정체성
> D1~D5 글로벌 정체성은 `~/.claude/CLAUDE.md` 참조. 본 프로젝트는 SCM 도메인 특화 에이전트로 위임.

## Harness Engineering
글로벌 Universal Project Harness(`~/.claude/harness/`) 사용. 8h+ 자율 미션은 `/mission <template> --duration <h>` · 재개는 `/mission resume <id>` · 나열 `/mission list` · 중단 `/mission abort <id>` (Phase 1 FSM, 2026-05-16). 본 프로젝트 도메인 라우팅(SK-01~09, D-TMS1/2, D1~D3)은 그대로 유지 — Harness Orchestrator가 *Worker로 위임*. 단발 작업은 기존 키워드 라우팅(Harness 이벤트 로깅 미개입). 모든 미션 전이는 `~/.claude/harness/logs/<mission-id>/events.jsonl` 에 SSOT 기록.

> **Routing 분기 충돌 정의 (Phase 2 audit X7 보완):**
> - **OTIF/KPI 집계 분석** → SK-06 tms-otif-kpi (운영 집계) / **TMS 개선·로드맵 설계** → D-TMS1 tms-improvement
> - **TMS 한정 전략 프레임워크** (5 Forces·SWOT·BCG·3 Horizons·MECE·Issue Tree·Pyramid) → D-TMS1 / **범 프로젝트 PM 프레임워크** → D3 consulting-pm-expert
> - **Lane·CBM·노선 비용** → SK-09 tms-cost-lane (전술) / **거점·소싱·네트워크 재설계** → D1 scm-logistics-expert (전략)
> - **회의 메모·텍스트·PDF 입력 → 마크다운 회의록** → SK-08 meeting-analysis / **미션 Sprint 결과 합성** → harness meeting-coordinator (미션 모드 한정)
>
> **모델 할당 (L1 기본 sonnet override):** 세밀한 운영 SK-01~05/07~09는 sonnet 준수. SK-06 + 모든 D-* (D-TMS1/2, D1~D3)는 깊은 추론·전략 산출이므로 opus 정당화됨.

## 에이전트 팀 라우팅

### SCM 운영 특화 (세밀한 키워드 우선)

| 키워드 | 에이전트 | 모델 |
|--------|---------|------|
| 품목코드, 로케이션, 공급사, 바코드, ROP, BIN | wms-master-data (SK-01) | sonnet |
| 입하, 검수, GR, ASN, AQL, 납품, Dock-to-Stock | wms-inbound (SK-02) | sonnet |
| 재고불일치, 사이클카운팅, 음수재고, ADJUST, 실사, 재고 정정 | wms-inventory (SK-03) | sonnet |
| 피킹, 패킹, Wave, SSCC, 출고지시, 박스라벨, Packing List, Shipping Mark | wms-outbound (SK-04) | sonnet |
| 운송장, 택배, 로젠, POD, 배차, 드라이버 | tms-shipment (SK-05) | sonnet |
| OTIF, KPI, Dock-to-Stock 분석, 소화율, 약속납기, 차량이용률, AutoResearch | tms-otif-kpi (SK-06) | **opus** |
| 운임 비용, lane, 노선, CBM당 비용, 발송 모드, 통합 ROI, 비용 이상, 물류비, lane 수익성, 배송비 분석 | tms-cost-lane (SK-09) | sonnet |
| 반품, 역물류, RESTOCK, DISPOSE, NCR, 불량 | wms-return (SK-07) | sonnet |
| 회의록, 미팅노트, 주간 운영 회의, 회의 분석 | meeting-analysis (SK-08) | sonnet |

### SCM 도메인 전문가 (전략·진단·설계)

| 키워드 | 에이전트 | 모델 |
|--------|---------|------|
| TMS 개선, 프로젝트 착수, 로드맵, Gap 분석, AS-IS, TO-BE, 요구사항, 개선계획, TMS 설계, TMS 고도화, TMS 5 Forces, TMS SWOT, TMS PESTEL, TMS 7S, TMS Issue Tree, TMS MECE, TMS Pyramid, BCG Matrix, 3 Horizons, carrier market 분석, lane 포트폴리오 | tms-improvement (D-TMS1) | **opus** |
| carrier 평가, 3PL, 운임 재협상, RFQ, 외주, 계약, SLA, scorecard, 파트너사, carrier 전략, 택배사 변경 | tms-carrier (D-TMS2) | **opus** |
| 재고전략, 물류컨설팅, SCM개선, 공급망, SCOR, ABC분석, XYZ, 거점, 소싱, 리드타임, Bullwhip | scm-logistics-expert (D1) | **opus** |
| 분개, 전표, 세금, 기간마감, K-IFRS, 더존, 계정코드, 역분개, 재고자산, 이전가격, 부가세 | tax-accounting-expert (D2) | **opus** |
| 프로젝트계획, 로드맵, 리스크, MECE, Issue Tree, PMP, OKR, 스프린트, WBS, Pyramid, 7S, Porter, SWOT | consulting-pm-expert (D3) | **opus** |

### 기타 작업

| 키워드 | 도구 |
|--------|------|
| 코드 구현, 아키텍처, DB, API | 빌트인 `Plan` / `feature-dev:code-architect` / `general-purpose` |
| UI/디자인 | `frontend-design` 플러그인 + Stitch MCP |
| worktree, 병렬 작업 | `/worktree` |
| 실수 기록, lesson | `/lesson` |

> **라우팅 우선순위:** 세밀한 운영(SK-01~09) > TMS 전략(D-TMS1/D-TMS2) > 도메인 전문가(D1/D2/D3) > 빌트인.
> **분기 충돌 시:** "운영 집계" → SK / "TMS 개선·착수" → D-TMS1 / "carrier 평가·계약" → D-TMS2 / "전략 진단·로드맵" → D / "코드 구현" → 빌트인.
> **복합 요청:** 메인 Claude가 Agent 툴 병렬 호출 (예: D1+SK-03 = 음수재고 패턴+전략).

## 태스크 관리
`.claude/feature_list.json` — 전체 태스크 목록 (priority: critical > high > medium > low > done)

## 검증 체크포인트 (코드 수정/생성 후 필수)
1. **Validation Contract 확인** (기능 수정/확장·새 기능 시): Phase 2에서 선언한 통과 조건 N개 각각에 대해 증거 수집
2. **훅 결과 확인**: PostToolUse 훅(typecheck, test-on-change) 출력에 오류가 없는지 확인
3. **harness-validator 호출**: Contract 레벨 검증 (Karpathy 원칙·시크릿·파괴적 작업 점검). `feature-dev:code-reviewer`(코드 레벨)와 *병행*. 직교 스코프이므로 중복 없음.
4. **결과 보고**: "Contract: ✅ N/M 통과 / typecheck: ✅ / 테스트: ✅ K개 통과 / harness-validator: PASS" 형식으로 보고
5. **다음 단계 확인**: 사용자에게 "진행 or 수정" 질문
6. **세션 종료 전**: Stop 훅이 자동으로 git status / 빌드게이트 검증

### 금지 표현 (검증 없이 사용 불가)
- "완료됐습니다", "구현했습니다" → 훅 결과 없이 사용 금지
- "잘 동작할 것입니다" → 실행 증거 없이 사용 금지

## 병렬 작업 (워크트리)
독립 기능 병렬 개발 시 `/worktree` → `.worktrees/<브랜치명>` 생성

## 실수 학습
반복 실수 발생 시 `/lesson <text>` → Retro-Learning System에 직접 추가. 미션·태스크 진행 중 발견한 반복 오류·개선 후보를 다음 미션에 자동 반영.
