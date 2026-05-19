# graphify + Obsidian 연동 설정 가이드

> 설정일: 2026-05-19 | 브랜치: `claude/check-graphify-obsidian-zYqjl`

---

## 개요

sincerely-scm-pipeline 코드베이스를 graphify로 지식 그래프화하고, Obsidian vault(ClaudeVault)와 연동하는 설정.

```
코드베이스 (.claude/agents, scripts, api 등)
    └─ graphify 실행
         ├─ graphify-out/graph.json       → MCP 서버가 읽는 쿼리 대상
         ├─ graphify-out/graph.html       → 시각화 (브라우저에서 열기)
         ├─ graphify-out/GRAPH_REPORT.md  → god nodes + 커뮤니티 요약
         ├─ graphify-out/obsidian/        → Obsidian vault 마크다운
         └─ graphify-out/wiki/            → agent-crawlable 마크다운 wiki
              └─ Windows 배치 스크립트 → ClaudeVault\SCM\graphify\ 복사
```

---

## 설치된 패키지

```
graphifyy[mcp]  # 패키지명 graphifyy (y 두 개), CLI명 graphify
```

`requirements-autoresearch.txt`에 추가됨.

---

## 추가/수정된 파일 목록

| 파일 | 변경 | 설명 |
|------|------|------|
| `requirements-autoresearch.txt` | 수정 | `graphifyy[mcp]>=0.1.0` 추가 |
| `scripts/run_graphify.sh` | **신규** | 로컬 수동 실행 스크립트 |
| `.mcp.json` | **신규** | graphify MCP 서버 설정 |
| `.claude/hooks/session-start.sh` | **신규** | 웹 세션 자동 설치·실행 훅 |
| `.claude/settings.json` | **신규** | SessionStart 훅 등록 |
| `.github/workflows/weekly-full-pipeline.yml` | 수정 | Step 5 graphify 추가 |
| `scripts/obsidian_sync_weekly.bat` | 수정 | graphify→ClaudeVault 복사 추가 |
| `.gitignore` | 수정 | graphify 캐시 파일만 제외, graph.json 등은 커밋 |

---

## MCP 두 개의 차이

| | graphify MCP | Obsidian MCP |
|---|---|---|
| 설정 위치 | `.mcp.json` | meeting-analysis 에이전트 |
| 역할 | 코드베이스 그래프 쿼리 | ClaudeVault 파일 직접 쓰기 |
| 툴 | `query_graph`, `get_neighbors`, `shortest_path` | `obsidian_append_content` |
| 서버 | `python -m graphify.serve graphify-out/graph.json` | Obsidian 앱 내장 MCP 서버 |

---

## 로컬 Claude Code에서 사용하기

### 1. 최초 설치 (한 번만)

```bash
pip install "graphifyy[mcp]"
```

### 2. 최초 그래프 빌드 (한 번만)

```bash
bash scripts/run_graphify.sh
```

> 처음엔 코드베이스 전체 처리 — 2~5분 소요. 이후엔 증분 업데이트.

### 3. MCP 서버 활성화

`.mcp.json`이 이미 있으므로 **Claude Code 재시작**만 하면 됩니다.
재시작 후 Claude가 `query_graph` 툴을 자동으로 사용할 수 있습니다.

### 4. 이후 업데이트 (코드 변경 시)

```bash
bash scripts/run_graphify.sh   # --update 자동 적용
```

또는 직접:

```bash
graphify . --obsidian-dir graphify-out/obsidian --wiki --update
```

---

## 웹 세션 (Claude Code on the web)

`SessionStart` 훅이 자동으로 처리합니다. 아무것도 안 해도 됩니다.

```
세션 시작
  └─ .claude/hooks/session-start.sh 자동 실행
       ├─ pip install graphifyy[mcp]
       ├─ graphify . --update  (graph.json 있으면 증분, 없으면 풀 빌드)
       └─ MCP 서버 준비 완료
```

> **네트워크 필요**: 웹 세션의 네트워크 정책이 PyPI 허용이어야 합니다.

---

## Obsidian 동기화 (Windows)

`scripts/obsidian_sync_weekly.bat`을 Windows 작업 스케줄러로 실행하면:

1. `git pull` — GitHub Actions가 커밋한 최신 `graphify-out/` 수신
2. TMS/WMS Obsidian 동기화
3. `graphify-out\obsidian\` → `C:\Users\yjisu\Documents\ClaudeVault\SCM\graphify\` 복사

---

## GitHub Actions 자동화

`weekly-full-pipeline.yml`에 포함됨 — **별도 트리거 없음**, 기존 워크플로우에 Step 5로 추가.

```
매주 월요일 12:00 UTC (+ 수동 workflow_dispatch)
  Step 1~4: TMS/WMS AutoResearch
  Step 5:   graphify --update → graph.json 생성
  Step 6:   graph.json, obsidian/, wiki/ 포함해서 git commit & push
```

GitHub Actions의 역할: `graph.json`을 repo에 미리 커밋 → 새 컨테이너가 클론할 때 풀 빌드 불필요(증분만 실행해서 빠름).

> SessionStart 훅만으로도 동작하므로 GitHub Actions는 **"속도 최적화"** 목적.

---

## gitignore 정책

```gitignore
# graphify: transient 파일만 제외
graphify-out/manifest.json   # git clone 시 타임스탬프 무효화
graphify-out/cost.json
graphify-out/needs_update
graphify-out/cache/

# 커밋 대상 (팀 공유)
# graphify-out/graph.json
# graphify-out/graph.html
# graphify-out/GRAPH_REPORT.md
# graphify-out/obsidian/
# graphify-out/wiki/
```

---

## 쿼리 예시 (MCP 활성화 후)

Claude Code 세션에서 자연어로 쿼리:

- "wms-inventory 에이전트와 연결된 스크립트는?"
- "tms-shipment와 tms-cost-lane 사이 공통 의존성은?"
- "OTIF 관련 코드가 어디 있지?"

Claude가 `query_graph` MCP 툴로 파일 전체를 읽지 않고 그래프에서 바로 답합니다.
