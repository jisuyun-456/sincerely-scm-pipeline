# WMS Claude Code 새 컴퓨터 세팅 가이드 (v2)

> LightRAG + Obsidian AutoResearch + Graphify 포함 풀 스택 세팅

---

## 전체 레이어 구조

```
Layer 1  Claude Code CLI          기반 실행 환경
Layer 2  Superpowers 플러그인      워크플로우 스킬
Layer 3  글로벌 CLAUDE.md          전체 동작 방식 정의
Layer 4  프로젝트 CLAUDE.md        WMS 전용 규칙
Layer 5  WMS 전문가 에이전트 5종   도메인별 자동 위임
Layer 6  커맨드 + 훅 + settings    자동화 안전장치
Layer 7  Obsidian + LightRAG       지식/맥락 검색 (의미 기반)
Layer 8  Graphify                  코드 구조 그래프 (AST 기반)
```

---

## 수동으로 먼저 해야 할 것 (Claude Code 없는 상태)

### Step 1: Node.js 20+ 설치
https://nodejs.org 에서 다운로드 후 설치

### Step 2: Python 3.10+ 확인
```bash
python --version   # 3.10 이상 필요
```

### Step 3: Claude Code CLI 설치
```bash
npm install -g @anthropic-ai/claude-code
```

### Step 4: Claude Code 로그인
```bash
claude auth login
```

### Step 5: Superpowers 플러그인 설치
```bash
claude   # Claude Code 실행
# 채팅에서: /plugins → superpowers 검색 → install
```

### Step 6: Obsidian 설치
https://obsidian.md 에서 다운로드 후 설치
- Vault 열기: 이 컴퓨터의 ClaudeVault 폴더 지정 (또는 아래 폴더 생성)

---

## Claude Code 채팅에 붙여넣기 (자동 처리)

아래 텍스트를 **그대로 복사**해서 Claude Code 채팅에 붙여넣으세요.
`{WMS_PROJECT_PATH}` 와 `{SETUP_PACKAGE_PATH}` 만 실제 경로로 바꾸면 됩니다.

```
이 파일을 읽고 WMS Claude Code 환경을 세팅해줘:
{SETUP_PACKAGE_PATH}/SETUP_GUIDE.md

WMS 프로젝트 경로: {WMS_PROJECT_PATH}
setup-package 경로: {SETUP_PACKAGE_PATH}
ClaudeVault 경로: {VAULT_PATH}   (예: ~/Documents/ClaudeVault)

아래 순서대로 실행해줘:
1. {SETUP_PACKAGE_PATH}/global/CLAUDE.md → ~/.claude/CLAUDE.md 복사
2. {SETUP_PACKAGE_PATH}/global/settings.json → ~/.claude/settings.json 복사
3. {SETUP_PACKAGE_PATH}/project/CLAUDE.md → {WMS_PROJECT_PATH}/CLAUDE.md 복사
4. {SETUP_PACKAGE_PATH}/project/.claude/ → {WMS_PROJECT_PATH}/.claude/ 전체 복사
5. chmod +x {WMS_PROJECT_PATH}/.claude/hooks/*.sh
6. pip install graphifyy
7. graphify install claude
8. cd {WMS_PROJECT_PATH} && graphify update .
9. graphify hook install
10. Obsidian _AutoResearch 폴더 구조 생성 (아래 명세 참조)
11. 각 파일 존재 여부 확인 후 결과 보고
```

---

## 패키지 구조

```
wms-setup-package/
├── SETUP_GUIDE.md              ← 지금 읽는 이 파일
├── global/
│   ├── CLAUDE.md               ← 글로벌 설정 (~/.claude/CLAUDE.md)
│   └── settings.json           ← 글로벌 설정 (~/.claude/settings.json)
└── project/
    ├── CLAUDE.md               ← 프로젝트 루트에 복사
    └── .claude/
        ├── agents/             ← 전문가 에이전트 5종 + orchestrator
        │   ├── wms-master-data.md   (SK-01)
        │   ├── wms-inbound.md       (SK-02)
        │   ├── wms-inventory.md     (SK-03)
        │   ├── wms-outbound.md      (SK-04)
        │   ├── wms-return.md        (SK-07)
        │   └── orchestrator.md
        ├── commands/           ← 슬래시 커맨드 6종
        │   ├── wms-master-data.md
        │   ├── wms-inbound.md
        │   ├── wms-inventory.md
        │   ├── wms-outbound.md
        │   ├── wms-return.md
        │   └── start.md
        ├── hooks/              ← 자동화 훅 8종
        │   ├── check-sql-safety.sh
        │   ├── protect-branch.sh
        │   ├── protect-sensitive-files.sh
        │   ├── auto-format.sh
        │   ├── build-gate.sh
        │   ├── log-agent-usage.sh
        │   ├── typecheck.sh
        │   └── test-on-change.sh
        └── settings.json       ← 훅 연결 + 권한 설정
```

---

## Layer 1 — Claude Code CLI

```bash
npm install -g @anthropic-ai/claude-code
claude auth login
```

---

## Layer 2 — Superpowers 플러그인

Claude Code 실행 후:
```
/plugins → superpowers → install
```

| 스킬 | 용도 |
|------|------|
| `superpowers:brainstorming` | 새 기능 설계 전 아이디어 탐색 |
| `superpowers:writing-plans` | 구현 계획 작성 (코드 전 필수) |
| `superpowers:executing-plans` | 계획 단계별 실행 |
| `superpowers:systematic-debugging` | 버그 원인 분석 |
| `superpowers:requesting-code-review` | 구현 완료 후 코드 리뷰 |
| `superpowers:verification-before-completion` | 완료 선언 전 검증 |

---

## Layer 3 — 글로벌 CLAUDE.md + settings.json

```bash
cp wms-setup-package/global/CLAUDE.md ~/.claude/CLAUDE.md
cp wms-setup-package/global/settings.json ~/.claude/settings.json
```

**settings.json 포함 내용:**
- `effortLevel: max` — 최대 사고 품질
- `autoMemoryEnabled: true` — 자동 메모리 저장
- `model: sonnet` — 기본 모델 Sonnet 4.6
- `enabledPlugins` — 아래 10개 플러그인 자동 활성화
- `extraKnownMarketplaces` — 서드파티 마켓플레이스 3개 등록

| 플러그인 | 용도 |
|---------|------|
| `superpowers` | 핵심 워크플로우 스킬 번들 |
| `feature-dev` | 기능 개발 가이드 |
| `frontend-design` | UI/UX 디자인 전문 |
| `code-review` | 코드 리뷰 |
| `playground` | 인터랙티브 HTML 플레이그라운드 |
| `playwright` | 브라우저 자동화 |
| `typescript-lsp` | TS 타입 검사 |
| `security-guidance` | 보안 가이드 |
| `ui-ux-pro-max` | 50+ 스타일, 161 팔레트 |
| `bencium-controlled-ux-designer` | 접근성 UI/UX 전문 |

> settings.json 복사 후 플러그인은 Claude Code 첫 실행 시 자동 다운로드됨

포함 내용:
- D1~D5 전문가 정체성 (D1 SCM/WMS 핵심)
- 자동 라우팅 규칙 (키워드 → 에이전트)
- 메인 워크플로우 사이클
- Immutable Ledger 원칙
- Obsidian 메모리 규칙 + AutoResearch 세션 연속성
- LightRAG 스코프 라우팅 (wms/tms/stock/common)
- Graphify 참조

---

## Layer 4 — 프로젝트 CLAUDE.md

```bash
cp wms-setup-package/project/CLAUDE.md {WMS_PROJECT_PATH}/CLAUDE.md
```

포함 내용:
- Stock Type 5종 (UNRESTRICTED/QUALITY_INSPECTION/BLOCKED/IN_TRANSIT/RESERVED)
- Movement Type 8종 (101/122/201/261/311/601/701/702)
- 로케이션 ID 체계: `WH01-STORAGE-A03-R02-L2-B04`
- 품목 코드 체계: `PKG-001`, `PRD-001`, `ASM-001`, `RAW-001`
- 에이전트 팀 라우팅
- Graphify 그래프 위치 + 사용법
- AutoResearch 세션 시작 시 log.md 읽기

---

## Layer 5 — WMS 전문가 에이전트

```bash
cp -r wms-setup-package/project/.claude/agents/ {WMS_PROJECT_PATH}/.claude/agents/
```

| 에이전트 | 코드 | 담당 영역 | 자동 위임 트리거 |
|---------|------|---------|----------------|
| wms-master-data | SK-01 | 품목·로케이션·공급사 마스터 | "품목코드", "로케이션", "공급사", "ROP", "안전재고" |
| wms-inbound | SK-02 | 입하·검수·입고확정 | "입하", "검수", "GR", "ASN", "AQL", "Dock-to-Stock" |
| wms-inventory | SK-03 | 재고 원장·사이클카운팅 | "재고 불일치", "사이클카운팅", "음수재고", "ADJUST" |
| wms-outbound | SK-04 | Wave·피킹·패킹·출고 | "피킹", "패킹", "Wave", "SSCC", "출고지시" |
| wms-return | SK-07 | 반품·역물류 | "반품", "RESTOCK", "DISPOSE", "RTN번호" |
| orchestrator | - | 복합 도메인 조율 | "종합 분석", "전체 리뷰", "대시보드" |

### 에이전트별 핵심 알고리즘

**SK-01 wms-master-data**
- GS1 GTIN/EAN-13/GLN 표준
- ABC 분류: A=상위20%/월2회, B=다음30%/월1회, C=나머지50%/분기1회
- 안전재고: `SS = Z × σ × √LT` (Z=1.645, 95% 서비스 수준)
- ROP: `(평균 일 수요 × LT) + SS`

**SK-02 wms-inbound**
- AQL 샘플: `ceil(√total_qty × 10)`, 최소 5개, 합격 불량률 ≤ 1.0%
- 상태: PENDING → INSPECTING → CONFIRMED/REJECTED/PARTIAL
- Dock-to-Stock KPI: 목표 ≤ 8시간

**SK-03 wms-inventory**
- 불일치 분류: Type A(입력오류) / Type B(실물차이) / Type C(복합)
- Zap 오류 탐지: +N→-N 반복, 중복 실행, 음수재고
- SSOT: `item_id + location_id + stock_type` 3중 유니크

**SK-04 wms-outbound**
- FIFO/FEFO 자동 선택 (is_fefo=false→fifo_date)
- GS1 SSCC Mod-10 알고리즘 (18자리)
- Wave → PickingTask 경로 필수 (단건 직접 피킹 금지)

**SK-07 wms-return**
- Resolution: RESTOCK(701) / DISPOSE(702) / REPROCESS(311)
- 공급사 반품: RETURN_TO_SUPPLIER(122) → defect_rate 자동 갱신
- 반품율 KPI: ≤ 0.5%

---

## Layer 6 — 커맨드 + 훅 + settings.json

```bash
cp -r wms-setup-package/project/.claude/commands/ {WMS_PROJECT_PATH}/.claude/commands/
cp -r wms-setup-package/project/.claude/hooks/    {WMS_PROJECT_PATH}/.claude/hooks/
cp    wms-setup-package/project/.claude/settings.json {WMS_PROJECT_PATH}/.claude/settings.json
chmod +x {WMS_PROJECT_PATH}/.claude/hooks/*.sh
```

| 커맨드 | 동작 |
|--------|------|
| `/start` | git log -10 + 다음 태스크 제안 |
| `/wms-master-data` | SK-01 직접 호출 |
| `/wms-inbound` | SK-02 직접 호출 |
| `/wms-inventory` | SK-03 직접 호출 |
| `/wms-outbound` | SK-04 직접 호출 |
| `/wms-return` | SK-07 직접 호출 |

| 훅 | 실행 시점 | 역할 |
|----|---------|------|
| `check-sql-safety.sh` | Bash 실행 전 | UPDATE/DELETE 원장 차단 |
| `protect-branch.sh` | Bash 실행 전 | force push 차단 |
| `protect-sensitive-files.sh` | Edit/Write 전 | .env 수정 차단 |
| `auto-format.sh` | Edit/Write 후 | Prettier 자동 포맷 |
| `typecheck.sh` | Edit/Write 후 | tsc --noEmit |
| `test-on-change.sh` | Edit/Write 후 | Jest 자동 실행 |
| `build-gate.sh` | 세션 종료 시 | npm run build 검증 |
| `log-agent-usage.sh` | 서브에이전트 종료 | 에이전트 사용 로그 |

---

## Layer 7 — Obsidian + LightRAG

**역할**: 세션 간 메모리 + 문서/결정 의미 검색

### 7-A. Obsidian Vault 세팅

Obsidian 설치 후 Vault 경로 지정 (예: `~/Documents/ClaudeVault`)

**필수 폴더 구조 생성** (Claude Code에게 지시):
```
_AutoResearch/
└── WMS/
    ├── program.md          ← AutoResearch 목표 + Variant 정의
    ├── wiki/
    │   ├── index.md        ← 분석 결과 인덱스
    │   └── log.md          ← 세션 기억 (## [날짜] | 이벤트)
    └── outputs/            ← 분석 결과 파일 저장
```

**program.md 초기 내용:**
```markdown
---
tags: [autoresearch, wms, program]
type: program
project: WMS
status: setup
---

# WMS AutoResearch Program

## Goal (TBD)
WMS 재고 정확도 개선 — 세부 결정 후 업데이트

## Candidates
- 사이클카운팅 최적 주기 (ABC 분류별)
- 음수재고 발생 패턴 분석
- Dock-to-Stock 병목 구간 탐지

## Metric (TBD)
primary_metric: 재고 정확도 % (목표 99.9%)

## Next
목표 확정 후 Variant A/B/C 정의
```

**log.md 초기 내용:**
```markdown
---
tags: [autoresearch, wms, log]
type: log
project: WMS
---

# WMS AutoResearch Log

## [YYYY-MM-DD] setup | 초기 구조 생성
- 새 컴퓨터 WMS 환경 세팅 완료
- program.md 플레이스홀더 작성
- Next: 세부 목표 확정 → Variant 정의
```

### 7-B. Obsidian Local REST API 플러그인 설치

Obsidian → Settings → Community Plugins → Browse → `obsidian-local-rest-api` → Install → Enable

### 7-C. LightRAG MCP 설정

LightRAG는 의미 검색(semantic search)용 MCP 서버.
Claude Code에서 `mcp__lightrag__lightrag_query` 툴로 사용.

```bash
# LightRAG 서버 설치 (Python)
pip install lightrag-hku

# Claude Code MCP 등록 (서버 주소는 환경에 맞게)
claude mcp add lightrag --url http://localhost:8020
```

**스코프 설정** (`~/.claude/CLAUDE.md`에 이미 포함):
- `wms` — WMS 노트 + `_AutoResearch/WMS/`
- `tms` — TMS 노트 + `_AutoResearch/SCM/`
- `common` — 공통 결정사항/SOP

**사용법:**
```
# 의미 검색 (LightRAG)
mcp__lightrag__lightrag_query("WMS 재고 불일치 원인 패턴", project="wms")

# 파일 직접 읽기 (Obsidian MCP)
mcp__obsidian__obsidian_get_file_contents("_AutoResearch/WMS/wiki/log.md")
```

---

## Layer 8 — Graphify

**역할**: 코드베이스 knowledge graph — 함수·모듈·의존성 구조 탐색

### 설치 및 빌드

```bash
# 설치
pip install graphifyy

# Claude skill 등록
graphify install claude

# WMS 프로젝트 그래프 빌드
cd {WMS_PROJECT_PATH}
graphify update .

# git hook 설치 (커밋 시 자동 rebuild)
graphify hook install
```

### 빌드 결과

- `graphify-out/graph.json` — 노드/엣지 데이터
- `graphify-out/GRAPH_REPORT.md` — 커뮤니티 요약
- `.git/hooks/post-commit` — 자동 rebuild hook

### 사용법

```bash
# 코드 구조 탐색 (BFS)
graphify query "입고 확정 처리 흐름"

# 두 개념 사이 최단 경로
graphify path "GoodsReceipt" "InventoryLedger"

# 특정 클래스/함수 설명
graphify explain "WmsInboundService"

# Claude Code에서
/graphify query "WMS 재고 원장 흐름"
```

### LightRAG vs Graphify 비교

| | LightRAG | Graphify |
|---|---|---|
| 대상 | 문서·노트 (Obsidian) | 코드베이스 (.py/.ts/.sql) |
| 방식 | 의미 검색 (semantic) | 구조 탐색 (AST 그래프) |
| 질문 유형 | "왜 이렇게 설계됐지?" | "이 함수가 뭘 호출하지?" |

---

## MCP 서버 설정

```bash
# Airtable MCP
# Claude Code → Settings → MCP → Add
# 환경 변수:
AIRTABLE_PAT=patXXXXXXXXXXXXXX

# Obsidian Local REST API
# Obsidian 실행 중일 때 자동 연결 (port 27124)

# LightRAG
claude mcp add lightrag --url http://localhost:8020
```

---

## 전체 설치 체크리스트

```
[ ] 1.  Node.js 20+ 설치
[ ] 2.  Python 3.10+ 확인
[ ] 3.  Claude Code CLI 설치: npm install -g @anthropic-ai/claude-code
[ ] 4.  Claude Code 로그인: claude auth login
[ ] 5.  Superpowers 플러그인: claude → /plugins → superpowers → install
         (나머지 플러그인은 settings.json 복사 후 첫 실행 시 자동 설치됨)
[ ] 6.  글로벌 CLAUDE.md 복사: cp global/CLAUDE.md ~/.claude/CLAUDE.md
[ ] 7.  글로벌 settings.json 복사: cp global/settings.json ~/.claude/settings.json
[ ] 8.  프로젝트 폴더 이동: cd {WMS_PROJECT_PATH}
[ ] 9.  프로젝트 CLAUDE.md 복사: cp project/CLAUDE.md ./CLAUDE.md
[ ] 10. .claude 폴더 복사: cp -r project/.claude/ ./.claude/
[ ] 11. 훅 권한 부여: chmod +x .claude/hooks/*.sh
[ ] 12. Graphify 설치: pip install graphifyy
[ ] 13. Graphify Claude skill 등록: graphify install claude
[ ] 14. 코드 그래프 빌드: graphify update .
[ ] 15. Git hook 설치: graphify hook install
[ ] 16. Obsidian 설치 + Vault 지정
[ ] 17. obsidian-local-rest-api 플러그인 설치 + Enable
[ ] 18. _AutoResearch/WMS/ 폴더 구조 생성 (program.md + wiki/log.md)
[ ] 19. LightRAG MCP 설정: claude mcp add lightrag --url http://localhost:8020
[ ] 19. Airtable MCP 설정 (PAT 필요)
[ ] 20. 세션 시작 확인: claude → /start
```

---

## 자주 쓰는 커맨드

```bash
# 세션 시작
/start

# WMS 도메인 직접 호출
/wms-master-data   # 품목/로케이션/공급사
/wms-inbound       # 입하/검수/입고확정
/wms-inventory     # 재고 조회/불일치/사이클카운팅
/wms-outbound      # Wave/피킹/패킹/출고
/wms-return        # 반품/역물류

# 자동 위임 (키워드만 말하면 됨)
"PKG-005 품목 등록해줘"           → wms-master-data 자동
"오늘 입하된 GR 검수 처리해줘"     → wms-inbound 자동
"재고 불일치 리포트 뽑아줘"        → wms-inventory 자동
"오늘 Wave 생성해줘"              → wms-outbound 자동
"반품 RTN-001 처리해줘"           → wms-return 자동

# Graphify 코드 탐색
/graphify query "입고 확정 처리 흐름"
/graphify path "GoodsReceipt" "InventoryLedger"
/graphify explain "WmsInboundService"

# LightRAG 의미 검색 (Obsidian 실행 중일 때)
# 직접 Claude에게: "WMS 재고 불일치 원인 LightRAG로 조회해줘"
```

---

## 핵심 비즈니스 규칙

### 절대 금지
- `InventoryTransaction` UPDATE/DELETE → REVERSAL tx로만 처리
- 마스터 데이터 DELETE → `is_active = false`로 비활성화
- QcRecord 없이 입고 확정 → AQL 샘플링 필수
- Wave 없이 직접 피킹 → Wave → PickingTask 경로 필수

### Stock Type 전환
```
입하:    없음 → IN_TRANSIT
검수:    IN_TRANSIT → QUALITY_INSPECTION
합격:    QUALITY_INSPECTION → UNRESTRICTED   (Movement 101)
불합격:  QUALITY_INSPECTION → BLOCKED        (격리)
피킹예약: UNRESTRICTED → RESERVED
출고:    RESERVED → 삭제, qty 감소           (Movement 601)
반품:    없음 → BLOCKED (QC_HOLD)
재입고:  BLOCKED → UNRESTRICTED             (Movement 701)
폐기:    BLOCKED → 삭제                     (Movement 702)
```

### KPI 목표
| KPI | 목표 |
|-----|------|
| Dock-to-Stock | ≤ 8시간 |
| 피킹 정확도 | ≥ 99.5% |
| 재고 정확도 | ≥ 99% |
| 반품율 | ≤ 0.5% |
| AQL 합격 기준 | 불량률 ≤ 1.0% |

---

## 트러블슈팅

### 에이전트 자동 위임 안 될 때
```bash
ls .claude/agents/   # 파일 존재 확인
```

### 훅 실행 안 될 때
```bash
chmod +x .claude/hooks/*.sh
```

### Graphify 명령어 없을 때 (PATH 문제)
```bash
python -m graphify update .
# 또는 전체 경로로:
~/.local/bin/graphify update .
```

### Obsidian MCP 연결 안 될 때
- Obsidian이 실행 중인지 확인 (port 27124)
- obsidian-local-rest-api 플러그인 Enable 상태 확인

### Airtable 연결 오류
```bash
claude mcp list   # MCP 상태 확인
```

### `check-sql-safety.sh` 가 정상 SQL 차단 시
보호 테이블 패턴 확인:
```
PROTECTED="mat_document|stock_balance|inventory_transaction|accounting_entries|period_close"
```
