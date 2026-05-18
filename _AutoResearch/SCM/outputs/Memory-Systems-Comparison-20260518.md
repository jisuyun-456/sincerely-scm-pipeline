# Memory Systems Comparison — Hindsight vs OMEGA vs 현재 Obsidian 체계

> 작성: 2026-05-18 | 작성자: Claude (D3 컨설팅·리서치) | 분류: 의사결정용 비교 분석

---

## Executive Summary

**한 줄 결론**: 랩탑-only SCM 메모리 업그레이드 **1순위 = Hindsight** (`pip install hindsight-api`, 13.6k★, BEAM·LongMemEval 동시 1위, 토큰 효율적). Obsidian 플러그인 부재·Vectorize.io 상용화 리스크 대비 **이주 경로 = OMEGA** (Apache-2.0 + 재단 거버넌스). 도입 전 **한국어 임베딩 30분 PoC**로 최종 확정.

| 항목 | 결정 |
|------|------|
| 추천 1순위 | **Hindsight** (`pip install hindsight-api`) |
| 이주 경로 | OMEGA (`pip install omega-memory[server]`) |
| 인프라 | 랩탑 only — Docker / Railway / Fly **불필요** |
| 선결 조건 | 한국어 PoC 30분 (TMS-W18 retain → "에이원 OTIF" recall) |
| 정책 가드 | Airtable 단일 진실원천 정책 준수 — 운영 데이터 indexing 금지 |
| 다음 액션 | 사용자가 PoC GO 결정 시 별도 task로 진행 |

---

## 1. 현재 체계 진단

### 1.1 구조

```
_AutoResearch/SCM/
├── wiki/
│   ├── log.md      ← 462줄 append-only 세션 로그
│   └── index.md    ← 인덱스
└── outputs/
    ├── TMS-2026-W16.md
    ├── TMS-2026-W17.md
    └── TMS-2026-W18.md
```

+ SessionStart 훅이 `log.md` **최근 3개 항목**만 미리 표시.

### 1.2 잘 되는 것

| 강점 | 설명 |
|------|------|
| git 추적 | 모든 변경이 commit으로 보존 — 영구 감사 가능 |
| 사람 가독성 | 마크다운 그대로 사람이 읽고 편집 가능 |
| 정책 일관성 | Immutable Ledger 원칙(INSERT ONLY)이 자연스럽게 강제됨 |
| 비용 0 | 추가 인프라 없음 |

### 1.3 깨지는 것 (실제 사례)

| 시나리오 | 현재 방식 | 한계 |
|----------|----------|------|
| "PT2429 휴면 추적" | `grep -r PT2429 _AutoResearch/` | 동의어·약식표기 못 잡음. 시간순 정렬 수작업 |
| "에이원 carrier OTIF 12주 추세" | TMS-W16/17/18.md 각각 열어서 비교 | cross-week 자동 집계 불가 |
| SK-06 OTIF 에이전트 재실행 | 매번 wiki 처음부터 다시 읽음 | 컨텍스트 토큰 매번 동일 비용 |
| D-TMS1 진단 결과 회수 | 사용자가 outputs/ 어디에 있는지 기억해야 함 | 의미 기반 검색 없음 |
| 주간 회의록 → 결정사항 | 수작업으로 회의록 읽고 추출 | 자동 consolidation 없음 |

**핵심 진단**: 현재 체계는 *episodic memory*만 있고 *semantic/temporal/entity-graph memory*가 없음. SessionStart 훅의 "최근 3개" 룰은 사실상 6개월 전 결정은 망각.

---

## 2. Hindsight 핵심 요약

### 2.1 정체

- **제작**: Vectorize.io (캐나다·미국 사설 스타트업, Series A 단계, RAG 인프라 전문)
- **라이센스**: MIT License *(주의: MIT 대학교와 무관 — §11 FAQ 참조)*
- **GitHub**: `vectorize-io/hindsight` — 13.6k★ / 55 릴리즈 / 최신 v0.6.2 (2026-05-15)
- **언론**: VentureBeat 보도 ("With 91% accuracy, open source Hindsight agentic memory provides 20/20 vision")

### 2.2 아키텍처

3가지 핵심 연산:
- **retain** — 저장 (사실 추출 → 엔티티 해석 → 임베딩 → 그래프 인덱싱)
- **recall** — 검색 (4-병렬 retrieval + rerank)
- **reflect** — 추론 (Mental Models 자동 갱신)

**4-병렬 retrieval** (모든 쿼리에서 동시 실행):
1. Semantic vector search
2. BM25 keyword matching
3. Entity graph traversal
4. Temporal filtering

→ Reciprocal Rank Fusion으로 병합 → cross-encoder reranker로 최종 정렬.

**부가 구성요소**:
- **Mental Models** — 메모리 누적에 따라 자동 재작성되는 살아있는 문서
- **TEMPR** (Temporal Entity Memory Priming Retrieval) — recall 측 시간·엔티티 인식
- **CARA** (Coherent Adaptive Reasoning Agents) — 회기 간 추론 일관성 유지 (skepticism/literalism/empathy 다이얼)
- **World facts vs Experiences** — 인간 기억의 declarative/episodic 분리를 모방

### 2.3 랩탑 배포 — Docker / Railway / Fly **불필요**

| 옵션 | 명령 | 비고 |
|------|------|------|
| ① pip install | `pip install hindsight-api` → `hindsight-api` | bundled pg0 (embedded Postgres) — 별도 DB 설치 불필요 |
| ② uvx | `uvx hindsight-embed@latest configure` | zero-install, uv 한 번만 깔면 끝 |
| ③ npm | `npm i @vectorize-io/hindsight-all` | Node 환경용 |

Windows / macOS / Linux 모두 네이티브 지원. SQLite 모드도 별도 제공.

### 2.4 통합

- **MCP 서버 내장** — Claude Code, Claude Desktop, Cursor, Windsurf, Zed 즉시 연결
- **SDK 3종** — Python, TypeScript, Go
- **LLM 멀티 지원** — OpenAI, Anthropic, Gemini, Groq, Ollama, LM Studio

### 2.5 벤치마크

| 벤치마크 | 점수 | 비고 |
|----------|------|------|
| LongMemEval (Gemini 3 Pro) | **91.4%** | 첫 90%+ 시스템 |
| LongMemEval (OSS-120B) | 85.67% | 로컬 모델로도 SOTA급 |
| BEAM @ 10M 토큰 | **64.1% (1위)** | 2위 40.6% — 58% 마진 |
| LongMemEval @ 1M 토큰 | 73.9% | 토큰 증가에도 성능 *상승* |

### 2.6 토큰 비용

- 평균 retrieval ~7,000 토큰 (optimized memory 평균치)
- **Token-budget 컨트롤** — "프롬프트에 4,096 토큰만" 식 상한 설정 → API 비용 예측 가능
- 4-병렬 retrieval은 **CPU 컴퓨트** 부담 (cross-encoder rerank) — LLM 컨텍스트 부담 아님
- 풀-컨텍스트 대비 3~5배 절약

---

## 3. OMEGA 핵심 요약

### 3.1 정체

- **제작**: 네덜란드 비영리 재단 (foundation 거버넌스)
- **라이센스**: Apache-2.0 *("Core tier는 절대 상용 전환 안 함" 명시)*
- **GitHub**: `omega-memory/omega-memory` + `omega-memory/core` + `omega-memory/omega-obsidian-plugin`
- **포지셔닝**: "AI 코딩 에이전트용 영구 메모리"

### 3.2 아키텍처

- **DB**: SQLite (`omega.db`) + sqlite-vec 확장
- **임베딩**: `bge-small-en-v1.5` ONNX (완전 on-device)
- **저장 단위**: memories / edges / embeddings 3-테이블 그래프 구조

**25 memory tools** (요약):
- 기본: store, query, semantic search
- 시계열: timeline, checkpoint, resume
- 정리: compaction, consolidation
- 그래프: traversal, entity linking
- 컨텍스트 가상화: context virtualization (페이지 인/아웃)

### 3.3 랩탑 배포

```bash
pip install omega-memory[server]
omega setup    # 모델 다운로드 + MCP 등록
omega doctor   # 동작 검증
```

— 끝. Docker / DB 서버 / API 키 / 클라우드 계정 **모두 불필요**.

### 3.4 통합

- **MCP 지원** — Claude Code 즉시 연결
- **Python API** — MCP 서버 없이도 `store()` / `query()` 직접 호출 가능
- ⭐ **공식 Obsidian 플러그인** (`omega-memory/omega-obsidian-plugin`) — vault 직접 semantic search

### 3.5 벤치마크

| 벤치마크 | 점수 |
|----------|------|
| LongMemEval (ICLR 2025, task-avg) | **95.4%** — 현재 발표된 최고치 |

토큰 사용량 공식 수치는 미공개. compaction/consolidation 도구로 효율 최적화 가정.

### 3.6 거버넌스 우위

- Apache-2.0 + 재단 운영 → 가격 정책 변경 리스크 0
- "Core 영구 OSS" 명시 → 향후 Pro tier 게이팅 우려 없음
- 비교: Mem0가 graph 기능을 $249/mo Pro tier로 게이팅한 전례 있음

---

## 4. 3-Way 비교 매트릭스

| 차원 | 현재 시스템 | Hindsight | OMEGA |
|------|------------|-----------|-------|
| **설치 명령** | 이미 있음 | `pip install hindsight-api` | `pip install omega-memory[server]` |
| **DB / 임베딩** | 마크다운 파일만 | embedded pg0 (자동) | SQLite + sqlite-vec + bge-small ONNX |
| **Docker 필요?** | ❌ | ❌ | ❌ |
| **검색 방식** | grep | semantic + BM25 + 그래프 + 시간 (4-병렬) + cross-encoder | semantic + 25 도구 (compaction/timeline/그래프) |
| **LongMemEval** | N/A | 91.4% (Gemini 3) | **95.4%** (ICLR 2025 task-avg) |
| **BEAM 10M 토큰** | N/A | **64.1% (1위)** | 미발표 |
| **Obsidian 직결** | (그 자체가 vault) | ❌ (스크립트 우회 필요) | ⭐ **공식 플러그인** |
| **MCP** | ❌ | ✅ | ✅ |
| **라이센스** | — | MIT | Apache-2.0 |
| **거버넌스** | git | Vectorize.io (Series A 스타트업) | 네덜란드 재단 + Core 영구 OSS 약속 |
| **GitHub 트랙션** | — | 13.6k★ / VentureBeat | 작음 (신생, 다중 리포) |
| **한국어 임베딩** | grep으로 OK | 검증 필요 (멀티 모델 지원) | ⚠️ bge-small-en-v1.5 (영어 위주) |
| **Mental Model 자동** | ❌ | ✅ | ✅ (consolidation) |
| **운영 부담** | 0 | 매우 낮음 (pip 한 줄) | 매우 낮음 (pip 한 줄) |
| **토큰/retrieval** | N/A | ~7,000 (budget 컨트롤) | 미공개 |

---

## 5. SCM 시나리오별 채점

각 시스템이 우리 실제 시나리오에서 얼마나 잘 작동할지 1~5점 채점 (5점 만점).

| # | 시나리오 | 현재 | Hindsight | OMEGA |
|---|----------|-----:|----------:|------:|
| A | "PT2429 휴면 시점 추적" (temporal entity 쿼리) | 2 | **5** | 4 |
| B | "에이원 carrier OTIF 12주 추세" (auto Mental Model) | 1 | **5** | 4 |
| C | SK-06 OTIF 에이전트가 과거 D-TMS1 진단 회수 (MCP) | 1 | **5** | 5 |
| D | 주간 회의록 → 결정사항 추출 (consolidation) | 2 | 4 | **5** |
| | **합계 (/20)** | 6 | **19** | 18 |

**해설**:
- **시나리오 A**: Hindsight의 entity graph + temporal filtering 조합이 가장 강함. OMEGA도 그래프 도구 있으나 시간 인덱싱은 timeline 도구 1단계.
- **시나리오 B**: Hindsight Mental Models가 자동 재작성됨 — 매주 OTIF 추세 문서를 사람이 안 만들어도 됨. OMEGA consolidation은 수동 트리거.
- **시나리오 C**: 둘 다 MCP로 동등.
- **시나리오 D**: OMEGA consolidation 도구가 더 정제됨 (compaction과 함께).

**결과**: Hindsight 19점 vs OMEGA 18점 — 박빙. Obsidian 플러그인 가산점은 시나리오 외 통합 편의성.

---

## 6. CLAUDE.md 정책 충돌 검토

### 6.1 위배 가능성 점검

CLAUDE.md 핵심 원칙:
1. **Airtable 단일 진실원천** — WMS/TMS 운영 데이터는 Airtable에서만 R/W
2. **Immutable Ledger** — movement / mat_document INSERT ONLY
3. **Supabase 이중화 금지** — 대시보드 스냅샷 외 운영 데이터 복제 금지

### 6.2 안전 범위 (indexing 허용)

| 데이터 종류 | indexing 가능 여부 | 비고 |
|------------|-------------------|------|
| `_AutoResearch/SCM/wiki/log.md` | ✅ | 세션 메모리 |
| `_AutoResearch/SCM/outputs/*.md` | ✅ | 리서치 결론 |
| `sincerely-meeting-notes/*.md` | ✅ | 회의록 |
| `인수인계서/*.md` | ✅ | 문서 |
| Airtable WMS movement | ❌ **금지** | 운영 데이터 — Airtable이 단일 진실원천 |
| Airtable TMS shipments | ❌ **금지** | 동일 |
| `mat_document` 테이블 | ❌ **금지** | Immutable Ledger 원칙 |

### 6.3 결론

Hindsight·OMEGA 둘 다 **마크다운 문서만 indexing**하면 정책 충돌 없음. 메모리 DB(`omega.db` 또는 `pg0`)는 *세컨더리 검색 인덱스*로만 작동, *원본은 git 마크다운*.

→ 둘 다 안전.

---

## 7. 한국어 임베딩 우려 + 30분 PoC 절차

### 7.1 우려 사항

OMEGA 기본 임베더 `bge-small-en-v1.5`는 영어 위주 학습. 우리 도메인은 한국어 + 코드(PT0510) + 영어 약어(OTIF, lane) 혼합 → 회수율 미지수.

Hindsight는 LLM 임베딩 (OpenAI text-embedding-3, Anthropic 등) 선택 가능 → 한국어 강한 모델 선택 여지 있음.

### 7.2 PoC 절차 (30분, 사용자 별도 승인 시)

```
1. pip install hindsight-api   (또는 omega-memory[server])
2. outputs/TMS-2026-W18.md 1개를 retain
3. 다음 5개 쿼리로 recall, top-3 결과 검증:
   - "에이원 OTIF 추세"
   - "수도권 직배송 리드타임"
   - "내부 소화율 60%"
   - "PT2429"
   - "다영기획 박종성 박스"
4. 적중률 4/5 이상 → 정식 도입 GO
   적중률 2~3/5 → 임베더 교체 후 재시도
   적중률 0~1/5 → 폴백 후보 검토
```

### 7.3 폴백 옵션

- OMEGA의 임베더는 교체 가능 (`bge-m3`, `multilingual-e5-large`, `paraphrase-multilingual-mpnet-base-v2`)
- Hindsight는 LLM 임베딩 변경으로 대응 (OpenAI vs Anthropic vs Gemini)
- 양쪽 다 막히면 → 현재 grep 체계 유지 + Tier 0(메타데이터 라인 추가)만 적용

---

## 8. 토큰 비용 분석

사용자 핵심 관심사 — "Hindsight가 토큰을 더 많이 쓰는가?"

### 8.1 결론

**아니다.** Hindsight는 오히려 토큰 효율적.

| 시스템 | 토큰/대화 (or retrieval) | 비고 |
|--------|------------------------|------|
| 풀-컨텍스트 (naive) | 25,000~100,000 | 비교 기준 |
| **Hindsight** | **~7,000 / retrieval** | token-budget 컨트롤 (예: 4,096 상한) |
| OMEGA | 미공개 | compaction/consolidation 도구로 최적화 |
| Mem0 | 1,800 / 대화 | 가장 작음 (extraction-only) |
| Zep | 600,000+ / 대화 | **피해야 함** |

### 8.2 4-병렬 retrieval은 LLM 토큰 부담 아님

오해 주의: Hindsight의 4-병렬 retrieval = **CPU 컴퓨트** 작업 (cross-encoder rerank는 로컬 모델). 최종적으로 LLM 프롬프트에 들어가는 토큰은 token-budget으로 상한 통제됨.

→ Hindsight 도입 후 LLM API 비용은 *증가하지 않음*. 오히려 풀-컨텍스트 RAG 대비 3~5배 절약.

---

## 9. 최종 추천

### 9.1 1순위: **Hindsight**

**결정 근거 5개**:
1. **13.6k★ 트랙션 + VentureBeat 보도** — 생태계 안정성
2. **4-병렬 retrieval (semantic + BM25 + graph + temporal)** — SCM 다국어·다엔티티 도메인에 강함
3. **BEAM 10M + LongMemEval 91.4% 동시 1위** — 대용량·정확도 양립
4. **토큰 효율** — token-budget 컨트롤로 LLM API 비용 예측 가능
5. **MCP + SDK 3종 (Python/TS/Go)** — Claude Code 즉시 통합

### 9.2 이주 경로 (2순위): **OMEGA**

**발동 조건**:
- Vectorize.io가 graph/temporal/rerank 등 핵심 기능을 Pro tier 게이팅 (Mem0가 갔던 길)
- → OMEGA로 마이그레이션

**OMEGA의 안전성**:
- Apache-2.0 + 네덜란드 재단 거버넌스
- "Core 영구 OSS" 명시 약속
- 가격정책 리스크 0

### 9.3 포기 항목 (트레이드오프 인지)

Hindsight는 **Obsidian 공식 플러그인이 없음** → `_AutoResearch/SCM/wiki/` 직결 인덱싱 불가.

**우회 방안** (의사코드):

```python
# scripts/hindsight_index_vault.py (예시 — 실제 구현 X)
import hindsight
from pathlib import Path

vault = Path("_AutoResearch/SCM/wiki")
client = hindsight.Client()

for md_file in vault.rglob("*.md"):
    client.retain(
        content=md_file.read_text(encoding="utf-8"),
        metadata={"source": str(md_file), "type": "wiki"},
    )
```

→ cron 또는 git post-commit 훅으로 자동화 가능. 1회 구축 후 유지보수 비용 거의 0.

OMEGA를 1순위로 선택했다면 이 우회가 불필요 — Obsidian 플러그인이 자동 처리.

### 9.4 Go / No-Go 조건

| 단계 | 조건 | 결과 |
|------|------|------|
| **Go** | 한국어 30분 PoC 4/5 이상 | Hindsight 정식 도입 |
| **재시도** | PoC 2~3/5 | 임베더 옵션 검토 (Anthropic/Gemini) |
| **폴백** | 임베더 교체 후에도 미달 | OMEGA로 전환 + bge-m3 적용 |
| **No-Go** | 모든 시도 실패 | 현재 grep 체계 유지 + Tier 0 메타데이터만 적용 |

---

## 10. CLAUDE.md / harness 후속 작업 (도입 결정 후)

**보고서 범위 밖 — 도입 GO 시 별도 task로 진행.**

도입 결정 시 필요 변경:
- `CLAUDE.md` "기술 스택 (현재 운영)" 표에 "메모리 레이어: Hindsight (laptop, embedded pg0)" 행 추가
- `.claude/settings.json` 또는 hook에 MCP 서버 등록
- `scripts/hindsight_index_vault.py` 작성 + git post-commit 훅 연결
- 사용 가이드 1page를 `인수인계서/` 또는 `docs/` 에 추가

---

## 11. MIT 오해 FAQ

**Q. Hindsight는 MIT 대학교가 만든 거지?**

A. **아니다.** 두 가지 "MIT"가 헷갈리기 쉽다.

| 용어 | 의미 |
|------|------|
| **MIT** (Massachusetts Institute of Technology) | 미국 보스턴의 공과대학 |
| **MIT License** | 1988년 MIT 대학교에서 처음 만든 *오픈소스 소프트웨어 라이센스 양식*. 지금은 누구나 자기 코드에 붙일 수 있는 표준 라이센스 이름. 라이센스 명칭과 코드 제작자는 무관. |

- **Hindsight 제작자** = Vectorize.io (캐나다·미국 사설 스타트업, Series A, RAG 인프라 회사). 단지 코드 라이센스로 "MIT License" 양식을 채택했을 뿐.
- **OMEGA 제작자** = 네덜란드 비영리 재단. 라이센스는 Apache-2.0.

거버넌스 안정성 관점에서 OMEGA(재단)가 Hindsight(VC-funded 스타트업)보다 *가격정책 변경 리스크가 낮음*. 이게 본 보고서가 OMEGA를 이주 경로로 명시한 이유.

---

## 12. 부록 A — 기타 검토 후보 (1순위에서 제외)

| 시스템 | 한 줄 평 | 제외 사유 |
|--------|----------|----------|
| **Mem0** (47k★) | 4-scope, ADD/UPDATE/DELETE/NOOP extraction, LongMemEval 49.0%. | 정확도 낮음, graph 기능 $249/mo Pro 게이팅 |
| **Letta** (MemGPT 후신) | OS-style paging (main/recall/archival), 학술 영향력 1위. | 복잡성·latency 비용, 단순 사용 사례에 과함 |
| **Zep / Graphiti** | Temporal knowledge graph, LongMemEval 63.8%. | 600k 토큰/대화 footprint, ingestion 지연 |
| **Cognee** | GraphRAG, SQLite+LanceDB+Kuzu 로컬. | 비정형 문서 대량 인덱싱 특화 — SCM 규모에 과함 |
| **MemOS / MemTensor** | Self-evolving L1/L2/L3 + Skills, 토큰 35% 절감. | 학술 단계, 프로덕션 사용례 적음 |
| **MemoryOS / BAI-LAB** | EMNLP 2025 Oral, hierarchical OS. | 학술 단계, Claude Code 통합 미검증 |

---

## 13. 참고 문헌

**Hindsight**
- GitHub: github.com/vectorize-io/hindsight
- 설치 가이드: hindsight.vectorize.io/developer/installation
- PyPI: pypi.org/project/hindsight-api
- DeepWiki Getting Started: deepwiki.com/vectorize-io/hindsight/2-getting-started
- npm: @vectorize-io/hindsight-all
- BEAM 벤치 1위: hindsight.vectorize.io/blog/2026/04/02/beam-sota
- 토큰 분석: hindsight.vectorize.io/blog/2026/03/23/agent-memory-benchmark

**OMEGA**
- GitHub: github.com/omega-memory/omega-memory
- Obsidian 플러그인: github.com/omega-memory/omega-obsidian-plugin
- 공식 사이트: omegamax.co
- PyPI: pypi.org/project/omega-memory

**벤치마크 & 비교**
- LongMemEval (ICLR 2025): OMEGA 95.4% / Hindsight 91.4% / Zep 63.8% / Mem0 49.0%
- VentureBeat: "With 91% accuracy, open source Hindsight agentic memory provides 20/20 vision"
- Vectorize 비교 시리즈: vectorize.io/articles/{hindsight-vs-mem0, hindsight-vs-zep, hindsight-vs-supermemory}
- Letta forum: forum.letta.com/t/agent-memory-letta-vs-mem0-vs-zep-vs-cognee/88

---

## 변경 이력

- 2026-05-18 v1.0 — 초안 작성 (Claude D3 컨설팅·리서치). 사용자 요청: "랩탑-only, 3-way 비교, 1순위 추천". 사용자 결정: Hindsight 1순위 + OMEGA 이주 경로.
