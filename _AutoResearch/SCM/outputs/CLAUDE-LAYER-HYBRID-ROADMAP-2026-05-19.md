# Claude Code 레이어 5축 통합 하이브리드화 로드맵

- **문서 ID**: CLAUDE-LAYER-HYBRID-ROADMAP-2026-05-19
- **작성일**: 2026-05-19
- **작성자**: D3 consulting-pm-expert (PMP/PgMP/PfMP/PMI-ACP/SAFe SPC)
- **대상 의사결정자**: yjisu (1인 PM)
- **참조 레포 (모두 MIT 라이선스 → 차용·인용 가능)**:
  - Addy Osmani `agent-skills`
  - Matt Pocock `skills`
  - Garry Tan `gstack`
  - Affaan Mustafa `Everything Claude Code` (ECC)

---

## 1. Executive Summary

> **결론 한 문장**: 우리 SCM 버티컬 깊이(S1~S6, 시그니처)는 **보존**하고, 일반 SDLC·페르소나·거버넌스·학습·포터빌리티 5축에서 **MIT 라이선스 4대 레포의 검증된 패턴을 차용·하이브리드화**하여 10개 갭(G1~G10)을 P0(2주)/P1(4주)/P2(8주) 단계로 닫는다.

3줄 요약:
1. **우리 강세 6**: 버티컬 SCM 깊이·모델 할당 최적화·Immutable Ledger·Harness FSM·외부 시스템 통합·세션 lifecycle 자동화. → 절대 훼손 금지.
2. **외부 갭 10**: 일반 SDLC, PRD/Issue 자동화, E2E QA, 페르소나, rules/, security hook, cross-tool, marketplace, /lesson 자동화, mcp-configs 모듈화.
3. **5축 MECE 보강**: SDLC·페르소나·거버넌스·학습·포터빌리티 → 합치면 갭 전체 커버, 상호 배타.

GO/NO-GO 판단 포인트: P0 3건(rules/, /qa+/browse, to-prd+to-issues) **모두 1주 PoC 가능** → 2주 내 가시 효과 확인 후 P1 진입 결정.

---

## 2. Current State Assessment

### 2.1 우리 레이어 강세 (S1~S6) — 보존 대상

| ID | 강세 | 핵심 자산 | 위협받으면 안 되는 이유 |
|----|------|-----------|------------------------|
| S1 | 버티컬 SCM 도메인 깊이 | 15개 전용 에이전트 (SK-01~09 + D1~D3 + D-TMS1/2), SAP 이동유형, K-IFRS, Airtable base ID 내재화 | 일반 스킬로는 대체 불가능한 핵심 경쟁력 |
| S2 | 모델 할당 최적화 | opus(전략) vs sonnet(운영) | 비용·품질 최적해 — 이미 검증됨 |
| S3 | Immutable Ledger 원칙 | movement/mat_document INSERT-ONLY, Storno 역분개 | 회계 정합성·감사 추적 무결성 |
| S4 | Harness FSM 미션 모드 | `/mission`, contract.yaml + events.jsonl SSOT, 8h+ 자율 | 장기 자율 작업의 단일 진실 원천 |
| S5 | 외부 시스템 통합 | Airtable / Obsidian / Notion / Railway / GH Actions / graphify | 운영 파이프라인 전체가 의존 |
| S6 | 세션 lifecycle 자동화 | SessionStart/Stop 훅, /lesson | 컨텍스트 연속성 보장 |

### 2.2 갭 (G1~G10) — 5축으로 매핑

| ID | 갭 | 영향 | 매핑 축 |
|----|----|------|---------|
| G1 | 일반 SDLC 스킬 부재 (TDD/debug/perf/security) | 비SCM 코드 작업 시 품질 일관성 ↓ | 축1 SDLC |
| G2 | PRD/Issue 자동화 부재 | 대화 → 작업 전환 마찰 | 축1 SDLC |
| G3 | Browser/E2E QA 부재 | 대시보드 UI 회귀 미검출 | 축1 SDLC |
| G4 | 비SCM 페르소나 공백 (CEO/Designer/CSO) | 다관점 review 부족 | 축2 페르소나 |
| G5 | rules/ 디렉토리 없음 | INSERT-ONLY/Storno 규칙이 CLAUDE.md에만 산재 | 축3 거버넌스 |
| G6 | Security scan hook 없음 | 시크릿 누수 위험 | 축3 거버넌스 |
| G7 | Cross-tool 이식성 0 (Cursor/Codex 공유 불가) | 협업자 합류 시 재학습 비용 | 축5 포터빌리티 |
| G8 | Plugin marketplace 미등록 | 외부 가시성·재사용성 0 | 축5 포터빌리티 |
| G9 | /lesson 수동 트리거 | 반복 실수 캡처 누락 | 축4 학습 |
| G10 | mcp-configs 단일파일 | 부분 활성/비활성 불가, 디버깅 난이도 ↑ | 축3 거버넌스 |

---

## 3. 5-Axis 하이브리드 전략 (MECE 트리)

### 3.1 MECE 자가 검증 (cross-product)

| 행 | 축 A | 축 B | 중복 가능성 | 판단 근거 |
|----|------|------|-----------|----------|
| 1 | 축1 SDLC | 축2 페르소나 | 낮음 | SDLC=공정 단계, 페르소나=관점 — 직교 |
| 2 | 축1 SDLC | 축3 거버넌스 | 낮음 | SDLC=실행, 거버넌스=정책/제약 — 직교 |
| 3 | 축2 페르소나 | 축3 거버넌스 | 낮음 | 페르소나=역할, 거버넌스=규칙 — 직교 |
| 4 | 축3 거버넌스 | 축4 학습 | 낮음 | 거버넌스=정적, 학습=동적 피드백 — 직교 |
| 5 | 축4 학습 | 축5 포터빌리티 | 낮음 | 학습=내부 메모리, 포터빌리티=외부 공유 — 직교 |
| 6 | 축1 SDLC | 축5 포터빌리티 | 중간 | setup-* skill이 양쪽 걸침 → 축5에만 귀속(설계 결정) |

→ **MECE 충족**: 6쌍 검증 완료, 경계 모호 1건은 명시적 귀속 결정.

### 3.2 트리 다이어그램

```
Claude Code 레이어 하이브리드화
│
├── 축1. SDLC 보강 (G1, G2, G3) — Addy + Pocock
│   ├── 6단계 워크플로우: Define → Plan → Build → Verify → Review → Ship  [Addy]
│   ├── to-prd / to-issues  (대화 → PRD → GH Issues 자동)  [Pocock]
│   ├── zoom-out / prototype  (탐색·러프 모드)  [Pocock]
│   ├── code-simplification / performance-opt / deprecation  [Addy]
│   └── /qa + /browse  (E2E + Playwright 회귀)  [gstack]
│
├── 축2. 페르소나 롤플레이 (G4) — gstack (비SCM 영역만)
│   ├── /office-hours  (CEO 관점 비즈니스 review)
│   ├── /design-review  (Designer/UX)
│   ├── /cso  (CSO: OWASP Top10 + STRIDE)
│   └── /retro  (회고 페르소나 = 축4와 연동)
│   ※ SCM 도메인은 SK-01~09 / D1~D3 / D-TMS1/2가 담당 — 페르소나는 비SCM만
│
├── 축3. 거버넌스 / 정책 (G5, G6, G10) — ECC + gstack
│   ├── rules/ 디렉토리 (ECC 패턴)
│   │   ├── rules/common.md      (공통)
│   │   ├── rules/python.md      (PEP8 + type hint)
│   │   ├── rules/airtable.md    (INSERT-ONLY + Storno 역분개 — S3 시그니처 명문화)
│   │   └── rules/sql.md         (Supabase 스냅샷 한정)
│   ├── mcp-configs/ 14개 분리  (ECC 패턴)
│   └── /freeze /unfreeze /guard  (gstack — 핵심 파일 보호)
│
├── 축4. 학습 / 메모리 (G9) — ECC + gstack + SK-08
│   ├── continuous-learning 훅  (/lesson 자동 트리거)  [ECC]
│   ├── memory persistence → ClaudeVault log.md 강화  [ECC]
│   ├── /retro 페르소나  [gstack]
│   └── SK-08 meeting-analysis 결합 sprint 회고  [우리 자산 + ECC]
│
└── 축5. 포터빌리티 / 배포 (G7, G8) — Addy + Pocock + ECC
    ├── plugin marketplace 등록: sincerely-scm-skills  [Addy/ECC]
    ├── AGENTS.md 작성 (Cursor/Codex/OpenCode 공유)  [Pocock/ECC]
    │   ※ 대시보드 레포(sincerely-scm-dashboard)부터 PoC
    └── setup-sincerely-scm skill (worktree/서브프로젝트 부트스트랩)  [Pocock]
```

### 3.3 축별 기대효과 (정량)

| 축 | 차용 출처 | 닫는 갭 | 기대효과 (정량) |
|----|----------|---------|----------------|
| 1 | Addy / Pocock | G1, G2, G3 | 코드 리뷰 시간 -40%, PRD→Issue 전환율 +70% |
| 2 | gstack | G4 | 다관점 review 커버리지 0 → 3관점 (CEO/Designer/CSO) |
| 3 | ECC / gstack | G5, G6, G10 | 시크릿 누수 사고 0건 유지, rules 위반 자동 차단 |
| 4 | ECC / gstack / SK-08 | G9 | /lesson 자동 캡처율 0% → 70% |
| 5 | Addy / Pocock / ECC | G7, G8 | Cursor/Codex 공유 레포 0 → 2, marketplace 등록 1건 |

---

## 4. WBS — Phase 0 / 1 / 2

### 4.1 Gantt-style 표 (1인 PM 기준 시간 투입)

```
주차:           W1   W2   W3   W4   W5   W6   W7   W8   W9   W10  W11  W12  W13  W14
─────────────────────────────────────────────────────────────────────────────────────
P0 (2주) ████████
  rules/        ██
  /qa /browse   ████
  to-prd/issues   ██████
P1 (4주)         ████████████████
  /cso security          ████
  Addy V-R-S                ████████
  /retro+CL hook                    ████
P2 (8주)                                  ████████████████████████████████
  mcp-configs/                            ████
  AGENTS.md+MP                              ████████
  setup-sincerely                                  ████████████
```

### 4.2 Phase 상세 WBS

#### Phase 0 (P0) — 1~2주차 / 총 투입 ~16h

| ID | 태스크 | 출처 | 투입(h) | PoC 1주 가능? |
|----|--------|------|---------|--------------|
| P0.1 | `rules/airtable.md` 작성 (INSERT-ONLY/Storno 명문화) | ECC | 2 | ✅ |
| P0.2 | `rules/common.md` + `rules/python.md` | ECC | 2 | ✅ |
| P0.3 | `/qa` 명령 (Playwright 통합) | gstack | 4 | ✅ (대시보드 레포 PoC) |
| P0.4 | `/browse` 명령 (브라우저 자동화) | gstack | 2 | ✅ |
| P0.5 | `to-prd` skill (대화 → PRD .md) | Pocock | 3 | ✅ |
| P0.6 | `to-issues` skill (PRD → `gh issue create`) | Pocock | 3 | ✅ |

→ **P0 3건 모두 1주 PoC 가능** ✅. P0 완료 시 GO/NO-GO 결정 게이트.

#### Phase 1 (P1) — 3~6주차 / 총 투입 ~32h

| ID | 태스크 | 출처 | 투입(h) |
|----|--------|------|---------|
| P1.1 | `/cso` security 페르소나 (OWASP+STRIDE) | gstack | 6 |
| P1.2 | Addy Verify skill (코드 + 테스트 검증) | Addy | 4 |
| P1.3 | Addy Review skill (PR review 자동) | Addy | 4 |
| P1.4 | Addy Ship skill (배포 체크리스트) | Addy | 4 |
| P1.5 | `/retro` 페르소나 + SK-08 결합 | gstack + 자산 | 6 |
| P1.6 | continuous-learning 훅 (/lesson 자동) | ECC | 8 |

#### Phase 2 (P2) — 7~14주차 / 총 투입 ~48h

| ID | 태스크 | 출처 | 투입(h) |
|----|--------|------|---------|
| P2.1 | mcp-configs/ 14개 모듈 분리 | ECC | 8 |
| P2.2 | AGENTS.md 작성 (대시보드 레포부터) | Pocock/ECC | 8 |
| P2.3 | plugin marketplace `sincerely-scm-skills` 등록 | Addy/ECC | 12 |
| P2.4 | `setup-sincerely-scm` skill (부트스트랩) | Pocock | 12 |
| P2.5 | Cursor/Codex 호환 테스트 | - | 8 |

**총 투입**: 약 96h (P0 16 + P1 32 + P2 48) = **1인 PM 기준 12 working days** 분산 14주.

---

## 5. RACI 매트릭스

| 태스크군 | 메인 Claude | SK 에이전트 | D 에이전트 | yjisu (PM) |
|---------|-------------|-------------|------------|-----------|
| P0.1 rules/airtable | C | I (SK-01~07) | A (D2 회계 검토) | R |
| P0.3 /qa+/browse | R | - | C (D3 PM) | A |
| P0.5~6 PRD/Issues | R | - | C (D3) | A |
| P1.1 /cso | R | - | C (D3) | A |
| P1.6 CL 훅 | R | I | C (D3) | A |
| P2.2 AGENTS.md | R | - | C (D3) | A |
| P2.3 marketplace | R | - | C (D3) | A |
| 전체 거버넌스 | C | I | R (D3) | A |

R=Responsible, A=Accountable, C=Consulted, I=Informed

---

## 6. Risk Register (TOP 5)

| # | 리스크 | P | I | P×I | Mitigation | Contingency |
|---|--------|---|---|-----|-----------|------------|
| R1 | 페르소나/스킬 폭증으로 라우팅 충돌 → SCM 시그니처 침식 | 中 | 高 | 9 | 페르소나는 비SCM 전용 명시, CLAUDE.md 라우팅 우선순위 명문화 | 충돌 시 페르소나 disable, SK/D 우선 |
| R2 | rules/ 문서화 vs 실제 enforce 갭 (선언만 되고 검사 안 됨) | 高 | 中 | 9 | rules/ + PreToolUse 훅 동시 도입, lint 자동화 | 위반 시 Stop 훅 차단 |
| R3 | /qa Playwright 도입 후 CI 시간 +50% | 中 | 中 | 6 | 대시보드 레포 한정 PoC, 야간 cron만 실행 | PR 차단 해제, 경고만 |
| R4 | marketplace 공개 시 base ID/시크릿 노출 | 低 | 高 | 6 | publish 전 secret scan 훅 필수, .gitignore 강화 | 노출 시 Airtable API key rotation |
| R5 | 1인 PM 14주 96h 투입 불가 (다른 우선순위 충돌) | 高 | 中 | 9 | P0 2주만 우선 commit, P1/P2는 결과 보고 후 재결정 | P1 이후는 미션 모드(/mission)로 자율 위임 |

---

## 7. OKR — 1Q (2026 Q2)

**Objective**: Claude Code 레이어를 SCM 버티컬 강점 보존 + 일반 SDLC·거버넌스·포터빌리티에서 업계 표준 수준으로 끌어올린다.

| KR | 측정 지표 | Baseline | Target | 마감 |
|----|----------|----------|--------|------|
| KR1 | rules/ 디렉토리 4개 파일 + INSERT-ONLY 위반 자동 차단 | 0건 차단 | 100% 차단 | 2026-06-02 |
| KR2 | PRD→GitHub Issue 전환율 (대화 종료 → issue 자동 생성) | 0% | 70% | 2026-06-16 |
| KR3 | /lesson 자동 캡처율 (반복 실수 패턴 감지 → 자동 기록) | 0% (수동) | 70% (자동) | 2026-07-14 |

---

## 8. Success Metrics (정량 KPI 5개)

| # | KPI | Baseline (2026-05) | Target (2026-08) | 측정 방법 |
|---|-----|-------------------|-----------------|----------|
| K1 | 코드 리뷰 시간 (PR 1건당) | 45분 | 27분 (-40%) | GH PR review_requested → merged timestamp |
| K2 | PRD → Issue 전환율 | 0% | 70% | 대화 종료 시점 vs `gh issue list` 생성 비교 |
| K3 | E2E 테스트 커버리지 (대시보드) | 0% | 60% | Playwright spec 수 / 페이지 수 |
| K4 | /lesson 자동 캡처율 | 0% (수동만) | 70% | 훅 트리거 lesson 수 / 전체 lesson 수 |
| K5 | Cross-tool 호환 레포 수 (AGENTS.md 보유) | 0 | 2 (파이프라인+대시보드) | repo grep AGENTS.md |

---

## 9. Validation Contract (P0 통과 조건)

P0 종료 시 다음 5건 모두 PASS 시 P1 진입:

| # | Contract | 측정 | 증거 위치 |
|---|----------|------|----------|
| C1 | rules/airtable.md 작성 + INSERT-ONLY 위반 케이스 1건 차단 | manual test 1회 | `rules/airtable.md` + 훅 로그 |
| C2 | /qa 명령 대시보드 레포에서 1개 spec 통과 | Playwright run | CI artifact |
| C3 | /browse 명령 1개 URL 캡처 성공 | 스크린샷 1장 | `.tmp/browse/` |
| C4 | to-prd: 대화 1건 → PRD .md 생성 | 파일 1개 | `_AutoResearch/SCM/outputs/PRD-*.md` |
| C5 | to-issues: PRD 1건 → GH Issue ≥1개 생성 | `gh issue list` | GH Issue URL |

---

## 10. Next Actions (즉시 착수 3건)

| # | 액션 | 담당 | 마감 | 산출물 경로 |
|---|------|------|------|------------|
| N1 | `rules/airtable.md` 초안 (INSERT-ONLY/Storno 명문화 + 위반 예시) | yjisu + D2 회계 검토 | 2026-05-22 | `/home/user/sincerely-scm-pipeline/rules/airtable.md` |
| N2 | `to-prd` skill PoC (대시보드 레포에서 1건 대화 → PRD) | yjisu | 2026-05-24 | `~/.claude/skills/to-prd/SKILL.md` |
| N3 | `/qa` 명령 Playwright PoC (대시보드 1개 페이지 회귀) | yjisu | 2026-05-26 | `sincerely-scm-dashboard/tests/e2e/` |

---

## 11. 부록 — 시그니처 보존 원칙

다음 4건은 어떤 하이브리드 차용에도 **변경 금지**:

1. **Immutable Ledger** (S3) — movement/mat_document INSERT-ONLY, Storno만 허용. rules/airtable.md에 재명문화하되 의미 변경 없음.
2. **Harness FSM SSOT** (S4) — `~/.claude/harness/logs/<id>/contract.yaml` + `events.jsonl` 외부 SSOT 없음. ECC memory와 *병행*하되 중복 아님.
3. **버티컬 라우팅 우선순위** (S1) — 세밀한 SK-01~09 > D-TMS1/2 > D1~D3 > 빌트인. 페르소나(/cso 등)는 이 우선순위 *밖*에 위치(비SCM 한정).
4. **모델 할당** (S2) — opus(전략) vs sonnet(운영). 신규 스킬도 이 원칙 준수.

---

## 12. 라이선스 / 인용 명세

4대 레포 모두 **MIT 라이선스** → 차용·수정·재배포 가능. 차용 시 다음 표기 의무:

| 차용 항목 | 출처 | 표기 위치 |
|----------|------|----------|
| 6단계 SDLC, code-simplification | Addy Osmani `agent-skills` | skill SKILL.md 헤더 |
| to-prd, to-issues, setup-*, AGENTS.md | Matt Pocock `skills` | skill SKILL.md 헤더 |
| /office-hours, /design-review, /cso, /qa, /browse, /retro, /freeze | Garry Tan `gstack` | command 파일 헤더 |
| rules/, mcp-configs/, continuous-learning, marketplace | Affaan Mustafa `Everything Claude Code` | rules/ README + plugin manifest |

---

**문서 끝.** GO/NO-GO 결정: P0 3건(N1/N2/N3) **2026-05-26까지** 완료 → P1 착수 여부 yjisu 재확인.
