"""
poc_memory_systems.py
─────────────────────────────────────────────────────────────────────────────
Hindsight vs OMEGA — 한국어 SCM 도메인 30분 PoC 스크립트

목적:
  Memory-Systems-Comparison-20260518.md §7 의 PoC 절차를 자동화.
  TMS-2026-W18.md 1개를 양쪽 시스템에 동일하게 retain → 5개 한국어 쿼리로
  recall → top-3 결과 적중률 채점.

전제 조건 (랩탑 실행 환경):
  - Python ≥ 3.11
  - 인터넷 접근 (PyPI + 임베딩 API)
  - 옵션 1) OPENAI_API_KEY 또는 ANTHROPIC_API_KEY 환경변수 (Hindsight 임베딩용)
  - 옵션 2) Ollama 로컬 모델 (`ollama pull nomic-embed-text`) — API 키 없이 완전 무료

사용법:
  ## macOS / Linux (bash)
  python3 -m venv .venv && source .venv/bin/activate
  pip install hindsight-all omega-memory[server]

  ## Windows PowerShell
  python -m venv .venv
  .venv\Scripts\Activate.ps1
  pip install hindsight-all omega-memory[server]

  # 양쪽 PoC 동시 실행
  python scripts/poc_memory_systems.py

  # Hindsight만
  python scripts/poc_memory_systems.py --only hindsight

  # OMEGA만
  python scripts/poc_memory_systems.py --only omega

  # 결과 JSON으로 저장
  python scripts/poc_memory_systems.py --json results.json

결과 해석 (Memory-Systems-Comparison §9.4 Go/No-Go 조건):
  - 적중률 ≥ 4/5  → 정식 도입 GO
  - 적중률 2~3/5 → 임베더 옵션 검토 후 재시도
  - 적중률 0~1/5 → 폴백 후보 검토 또는 현재 grep 체계 유지

이 스크립트는 *읽기 전용 평가*만 수행. 영구 메모리 DB는 임시 디렉토리에 생성
후 PoC 종료 시 사용자가 직접 삭제. CLAUDE.md 정책 (Airtable 운영 데이터
indexing 금지) 준수 — 본 PoC는 outputs/TMS-2026-W18.md 마크다운 1개만 사용.
"""

import argparse
import json
import os
import sys
import tempfile
import textwrap
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
TEST_DOC = REPO_ROOT / "_AutoResearch" / "SCM" / "outputs" / "TMS-2026-W18.md"

# 5개 한국어 PoC 쿼리 + 기대 키워드 (top-3 결과에 이 중 하나라도 포함되면 적중)
QUERIES = [
    {
        "q": "에이원 carrier OTIF 추세",
        "expect_any": ["에이원", "OTIF", "carrier", "택배사"],
        "label": "Q1-에이원_OTIF",
    },
    {
        "q": "수도권 직배송 리드타임",
        "expect_any": ["수도권", "리드타임", "직배송", "D+1", "당일"],
        "label": "Q2-수도권_직배송",
    },
    {
        "q": "내부 소화율 60%",
        "expect_any": ["소화율", "60%", "내부", "목표 80%"],
        "label": "Q3-내부_소화율",
    },
    {
        "q": "PT2429 휴면",
        "expect_any": ["PT2429", "휴면", "재고"],
        "label": "Q4-PT2429_휴면",
    },
    {
        "q": "다영기획 박종성 박스 없는 건",
        "expect_any": ["다영기획", "박종성", "박스", "CBM"],
        "label": "Q5-다영기획",
    },
]


def score_result(recalled_text: str, expect_any: list[str]) -> bool:
    """recalled_text 안에 expect_any 키워드가 하나라도 있으면 적중."""
    lowered = recalled_text.lower()
    return any(kw.lower() in lowered for kw in expect_any)


# ─────────────────────────────────────────────────────────────────────────────
# Hindsight 테스트
# ─────────────────────────────────────────────────────────────────────────────
def run_hindsight_poc(doc_text: str) -> dict:
    """Hindsight retain → recall × 5 → 적중률 채점."""
    print("\n" + "=" * 70)
    print("Hindsight PoC 실행")
    print("=" * 70)

    try:
        # hindsight-all (out-of-box 전체 패키지) 권장.
        # 대안: hindsight-api (서버) + hindsight-client (Python 클라이언트)
        from hindsight import Client  # type: ignore
    except ImportError:
        return {
            "system": "Hindsight",
            "status": "ERROR",
            "error": "hindsight 패키지 미설치. `pip install hindsight-all` 실행 필요.",
            "scores": [],
            "hit_rate": None,
        }

    with tempfile.TemporaryDirectory(prefix="hindsight_poc_") as tmpdir:
        os.environ.setdefault("HINDSIGHT_DATA_DIR", tmpdir)

        t0 = time.time()
        client = Client()  # 기본 임베더 + embedded pg0

        # retain
        client.retain(
            content=doc_text,
            metadata={"source": "TMS-2026-W18.md", "type": "wiki", "poc": True},
        )
        retain_secs = time.time() - t0
        print(f"  retain 완료 ({retain_secs:.2f}s)")

        # recall × 5
        scores = []
        for query in QUERIES:
            t0 = time.time()
            try:
                results = client.recall(query=query["q"], top_k=3)
            except Exception as e:
                scores.append(
                    {
                        "label": query["label"],
                        "q": query["q"],
                        "hit": False,
                        "error": str(e),
                        "latency_ms": int((time.time() - t0) * 1000),
                    }
                )
                continue

            recalled_text = "\n".join(
                getattr(r, "content", str(r)) for r in results[:3]
            )
            hit = score_result(recalled_text, query["expect_any"])
            scores.append(
                {
                    "label": query["label"],
                    "q": query["q"],
                    "hit": hit,
                    "latency_ms": int((time.time() - t0) * 1000),
                    "preview": recalled_text[:200] if recalled_text else None,
                }
            )
            print(f"  {query['label']}: {'✅' if hit else '❌'} ({query['q']})")

        hits = sum(1 for s in scores if s.get("hit"))
        return {
            "system": "Hindsight",
            "status": "OK",
            "retain_secs": round(retain_secs, 2),
            "scores": scores,
            "hits": hits,
            "total": len(QUERIES),
            "hit_rate": f"{hits}/{len(QUERIES)}",
        }


# ─────────────────────────────────────────────────────────────────────────────
# OMEGA 테스트
# ─────────────────────────────────────────────────────────────────────────────
def run_omega_poc(doc_text: str) -> dict:
    """OMEGA store → query × 5 → 적중률 채점."""
    print("\n" + "=" * 70)
    print("OMEGA PoC 실행")
    print("=" * 70)

    try:
        from omega_memory import OmegaMemory  # type: ignore
    except ImportError:
        return {
            "system": "OMEGA",
            "status": "ERROR",
            "error": "omega-memory 패키지 미설치. `pip install omega-memory[server]` + `omega setup` 실행 필요.",
            "scores": [],
            "hit_rate": None,
        }

    with tempfile.TemporaryDirectory(prefix="omega_poc_") as tmpdir:
        db_path = Path(tmpdir) / "omega_poc.db"

        t0 = time.time()
        mem = OmegaMemory(db_path=str(db_path))

        # store (OMEGA 용어)
        mem.store(
            content=doc_text,
            metadata={"source": "TMS-2026-W18.md", "type": "wiki", "poc": True},
        )
        retain_secs = time.time() - t0
        print(f"  store 완료 ({retain_secs:.2f}s)")

        # query × 5
        scores = []
        for query in QUERIES:
            t0 = time.time()
            try:
                results = mem.query(text=query["q"], limit=3)
            except Exception as e:
                scores.append(
                    {
                        "label": query["label"],
                        "q": query["q"],
                        "hit": False,
                        "error": str(e),
                        "latency_ms": int((time.time() - t0) * 1000),
                    }
                )
                continue

            recalled_text = "\n".join(
                getattr(r, "content", str(r)) for r in results[:3]
            )
            hit = score_result(recalled_text, query["expect_any"])
            scores.append(
                {
                    "label": query["label"],
                    "q": query["q"],
                    "hit": hit,
                    "latency_ms": int((time.time() - t0) * 1000),
                    "preview": recalled_text[:200] if recalled_text else None,
                }
            )
            print(f"  {query['label']}: {'✅' if hit else '❌'} ({query['q']})")

        hits = sum(1 for s in scores if s.get("hit"))
        return {
            "system": "OMEGA",
            "status": "OK",
            "retain_secs": round(retain_secs, 2),
            "scores": scores,
            "hits": hits,
            "total": len(QUERIES),
            "hit_rate": f"{hits}/{len(QUERIES)}",
        }


# ─────────────────────────────────────────────────────────────────────────────
# 결과 리포트
# ─────────────────────────────────────────────────────────────────────────────
def print_summary(results: list[dict]) -> None:
    """side-by-side 채점 표 출력."""
    print("\n" + "=" * 70)
    print("PoC 결과 요약 — Go/No-Go 판정")
    print("=" * 70)

    for r in results:
        print(f"\n[{r['system']}] status={r['status']}")
        if r["status"] == "ERROR":
            print(f"  오류: {r['error']}")
            continue
        print(f"  적중률: {r['hit_rate']} (retain {r['retain_secs']}s)")
        for s in r["scores"]:
            mark = "✅" if s["hit"] else "❌"
            err = f" ERROR:{s['error']}" if s.get("error") else ""
            print(f"  {mark} {s['label']:<25} {s['latency_ms']:>5}ms{err}")

    # Go/No-Go 판정
    print("\n" + "-" * 70)
    print("판정 (Memory-Systems-Comparison-20260518.md §9.4):")
    for r in results:
        if r["status"] != "OK":
            print(f"  {r['system']}: 실행 실패 — 별도 진단 필요")
            continue
        rate = r["hits"] / r["total"]
        if rate >= 0.8:
            verdict = "✅ GO — 정식 도입 권장"
        elif rate >= 0.4:
            verdict = "⚠️  재시도 — 임베더 옵션 검토 (bge-m3 / multilingual-e5)"
        else:
            verdict = "❌ NO-GO — 폴백 또는 현재 grep 체계 유지"
        print(f"  {r['system']:<10} → {verdict}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--only",
        choices=["hindsight", "omega"],
        help="한쪽만 실행 (기본: 양쪽 다)",
    )
    parser.add_argument("--json", help="결과를 JSON 파일로 저장")
    args = parser.parse_args()

    if not TEST_DOC.exists():
        print(f"[ERROR] 테스트 문서 없음: {TEST_DOC}")
        return 1

    doc_text = TEST_DOC.read_text(encoding="utf-8")
    print(f"테스트 문서: {TEST_DOC.relative_to(REPO_ROOT)} ({len(doc_text)} chars)")

    results = []
    if args.only in (None, "hindsight"):
        results.append(run_hindsight_poc(doc_text))
    if args.only in (None, "omega"):
        results.append(run_omega_poc(doc_text))

    print_summary(results)

    if args.json:
        Path(args.json).write_text(
            json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"\n결과 저장: {args.json}")

    # 종료 코드 = 더 높은 hit_rate가 0.8 미만이면 1
    best_rate = max(
        (r["hits"] / r["total"] for r in results if r["status"] == "OK"),
        default=0,
    )
    return 0 if best_rate >= 0.8 else 1


if __name__ == "__main__":
    sys.exit(main())
