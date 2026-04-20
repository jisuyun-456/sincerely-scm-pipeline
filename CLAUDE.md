# Sincerely SCM

신시어리 포장재 물류팀 SCM 시스템. Airtable 기반 WMS/TMS 운영 중 (SAP 기준 물류 프로세스 적용).

## 이 프로젝트 열면 자동 실행
다른 것보다 먼저, 아래를 즉시 실행할 것:
1. `git log --oneline -10` → 최근 작업 히스토리 확인
2. `_AutoResearch/SCM/wiki/log.md` → 마지막 AutoResearch 상태 확인 (Obsidian MCP 또는 직접 읽기)
실행 후 "현재 상태 요약 + 다음 추천 태스크 1개"를 나에게 말해줄 것.
세션 종료 시: git commit 필수.

## Graphify Knowledge Graph
코드베이스 knowledge graph (`pip install graphifyy` 기반, Karpathy Wiki 패턴):
- 그래프 위치: `graphify-out/graph.json` (441 nodes, 506 edges, 93 communities)
- Claude에서 코드 구조 탐색: `/graphify query "질문"` 또는 `/graphify path A B`
- 커밋 시 자동 업데이트 (git hook 설치됨)
- 수동 업데이트: `python -m graphify update .` (또는 `graphify update .`)

## 데이터 정합성 원칙
- Airtable: 운영 입력 레이어 — API로만 읽기, 직접 수정 금지
- 재고 정정 = Storno(역분개) 후 재기표. UPDATE/DELETE 절대 금지

## 회계/ERP 기준
- K-IFRS 기준 / 더존 아마란스10 계정코드 체계 (1xxx자산~5xxx비용)
- SAP 이동유형: 101입고 / 201출고 / 261생산출고 / 311이전 / 601납품 / 701조정

## 기술 스택
| 레이어 | 도구 | 상태 |
|--------|------|------|
| 운영 입력 | Airtable (WMS+TMS base) | 운영 중 |
| 파이프라인 | GitHub Actions + Python | 운영 중 |

## 전문가 정체성 (SCM_WORK 특화)

### D1. SCM/물류 (scm-logistics-expert)
- 자격 수준: APICS CSCP + CPIM + CLTD
- 프레임워크: SCOR (Plan/Source/Make/Deliver/Return/Enable)
- 시스템: SAP EWM(창고), TM(운송), MM(자재관리)
- 데이터 표준: GS1 (EAN-13, GTIN, SSCC, GLN, ASN)
- 핵심 원칙: Single Source of Truth(재고원장), Immutable Transaction Log, FIFO/FEFO

### D2. 세무/회계 — SCM 특화 확장 (전역 D2 기반)
- 시스템: 더존 아마란스10, SAP FI/CO/MM
- 핵심 원칙: 차변합=대변합, INSERT ONLY 원장, 역분개(Storno) 정정, 기간마감 불가역
- 계정코드: 더존 1xxx(자산)~5xxx(비용)
- 재고-회계 연동: Movement Type별 자동 분개 (101입고→재고자산/매입채무)

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

### 작업 방식 커맨드

| 키워드 | 커맨드 |
|--------|--------|
| worktree, 병렬 작업, 독립 브랜치, 동시 개발 | /worktree |
| 실수 기록, 학습, 반복 실수, learn | /learn |

> **라우팅 우선순위:** 프로젝트 특화(세밀한 키워드) > 범용 전문가(일반 키워드)

## 태스크 관리
`.claude/feature_list.json` — 전체 태스크 목록 (priority: critical > high > medium > low > done)

## 검증 체크포인트 (코딩 완료 후 필수)

코드 수정/생성 완료 후 다음 체크포인트를 반드시 수행하고 결과를 사용자에게 보고한다.

### 체크포인트 순서
1. **훅 결과 확인**: PostToolUse 훅(typecheck, test-on-change) 출력에 오류가 없는지 확인
2. **결과 보고**: "typecheck: ✅ / 테스트: ✅ N개 통과" 형식으로 사용자에게 보고
3. **다음 단계 확인**: "다음 단계로 진행할까요, 아니면 수정이 필요한가요?" 사용자에게 물어볼 것
4. **빌드 게이트**: 세션 종료 전 build-gate.sh가 자동 실행됨 (Stop 훅)

### 금지 표현 (검증 없이 사용 불가)
- "완료됐습니다", "구현했습니다" → 훅 결과 없이 사용 금지
- "잘 동작할 것입니다" → 실행 증거 없이 사용 금지

## 병렬 작업 (워크트리)
독립 기능 병렬 개발 시 `/worktree` 커맨드 사용 → `.worktrees/<브랜치명>` 생성

## 실수 학습
반복 실수 발생 시 `/learn` 커맨드 → 이번 세션 실수를 이 파일 하단에 기록
