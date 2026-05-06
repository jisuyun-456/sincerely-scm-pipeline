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
| 백엔드 | NestJS (PM2) — 일부 자동화만 |
| 파이프라인 | GitHub Actions + Python |
| 회의록 백업 | PostToolUse 훅 → Obsidian Vault + Slack 공유폴더 |

> Supabase / NocoDB / Metabase / Retool 미사용 확정 (메모리 `project_scm_redesign` 참조). 도입 제안 금지.

## 언어 설정

**Always respond in English**, regardless of the language the user writes in.

## 전문가 정체성
> D1~D5 글로벌 정체성은 `~/.claude/CLAUDE.md` 참조. 본 프로젝트는 SCM 도메인 특화 에이전트로 위임.

## 에이전트 팀 라우팅

### SCM 운영 특화 (세밀한 키워드 우선)

| 키워드 | 에이전트 | 모델 |
|--------|---------|------|
| 품목코드, 로케이션, 공급사, 바코드, ROP, BIN | wms-master-data (SK-01) | sonnet |
| 입하, 검수, GR, ASN, AQL, 납품, Dock-to-Stock | wms-inbound (SK-02) | sonnet |
| 재고불일치, 사이클카운팅, 음수재고, ADJUST, 실사, 정정 | wms-inventory (SK-03) | sonnet |
| 피킹, 패킹, Wave, SSCC, 출고지시, 박스라벨, Packing List, Shipping Mark | wms-outbound (SK-04) | sonnet |
| 운송장, 택배, 로젠, POD, 배차, 드라이버 | tms-shipment (SK-05) | sonnet |
| OTIF, KPI, Dock-to-Stock 분석, 소화율, 약속납기, 차량이용률, AutoResearch | tms-otif-kpi (SK-06) | **opus** |
| 반품, 역물류, RESTOCK, DISPOSE, NCR, 불량 | wms-return (SK-07) | sonnet |
| 회의록, 미팅노트, 주간 운영 회의, 회의 분석 | meeting-analysis (SK-08) | sonnet |

### SCM 도메인 전문가 (전략·진단·설계)

| 키워드 | 에이전트 | 모델 |
|--------|---------|------|
| 재고전략, 물류컨설팅, SCM개선, 공급망, SCOR, ABC분석, XYZ, 거점, 소싱, 리드타임, Bullwhip | scm-logistics-expert (D1) | **opus** |
| 분개, 전표, 세금, 기간마감, K-IFRS, 더존, 계정코드, 역분개, 재고자산, 이전가격, 부가세 | tax-accounting-expert (D2) | **opus** |
| 프로젝트계획, 로드맵, 리스크, MECE, Issue Tree, PMP, OKR, 스프린트, WBS, Pyramid, 7S, Porter, SWOT | consulting-pm-expert (D3) | **opus** |

### 기타 작업

| 키워드 | 도구 |
|--------|------|
| 코드 구현, 아키텍처, DB, API | 빌트인 `Plan` / `feature-dev:code-architect` / `general-purpose` |
| UI/디자인 | `frontend-design` 플러그인 + Stitch MCP |
| worktree, 병렬 작업 | `/worktree` |
| 실수 기록, learn | `/learn` |

> **라우팅 우선순위:** 세밀한 운영(SK-01~07) > 도메인 전문가(D1/D2/D3) > 빌트인.
> **분기 충돌 시:** "운영 집계" → SK / "전략 진단·로드맵" → D / "코드 구현" → 빌트인.
> **복합 요청:** 메인 Claude가 Agent 툴 병렬 호출 (예: D1+SK-03 = 음수재고 패턴+전략).

## 태스크 관리
`.claude/feature_list.json` — 전체 태스크 목록 (priority: critical > high > medium > low > done)

## 검증 체크포인트 (코드 수정/생성 후 필수)
1. **훅 결과 확인**: PostToolUse 훅(typecheck, test-on-change) 출력에 오류가 없는지 확인
2. **결과 보고**: "typecheck: ✅ / 테스트: ✅ N개 통과" 형식으로 보고
3. **다음 단계 확인**: 사용자에게 "진행 or 수정" 질문
4. **세션 종료 전**: Stop 훅이 자동으로 git status / 빌드게이트 검증

### 금지 표현 (검증 없이 사용 불가)
- "완료됐습니다", "구현했습니다" → 훅 결과 없이 사용 금지
- "잘 동작할 것입니다" → 실행 증거 없이 사용 금지

## 병렬 작업 (워크트리)
독립 기능 병렬 개발 시 `/worktree` → `.worktrees/<브랜치명>` 생성

## 실수 학습
반복 실수 발생 시 `/learn` → 이번 세션 실수를 이 파일 하단에 기록
