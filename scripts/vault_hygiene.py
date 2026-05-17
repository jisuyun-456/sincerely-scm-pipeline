"""
SCM Vault Hygiene Check (BenAI os-optimizer 경량 버전)
실행: python scripts/vault_hygiene.py
주기: 월 1회 또는 이슈 발생 시
"""

import re
from pathlib import Path
from datetime import date

ROOT = Path(__file__).parent.parent
LOG_PATH = ROOT / "_AutoResearch/SCM/wiki/log.md"
INDEX_PATH = ROOT / "_AutoResearch/SCM/wiki/index.md"
OUTPUTS_DIR = ROOT / "_AutoResearch/SCM/outputs"

issues = []
warnings = []

today = date.today().isoformat()


def check_log_duplicates():
    if not LOG_PATH.exists():
        issues.append("log.md 없음")
        return
    content = LOG_PATH.read_text(encoding="utf-8")
    pattern = r"## \[\d{4}-\d{2}-\d{2}\][^\n]+"
    headers = re.findall(pattern, content)
    dupes = [h for h in headers if headers.count(h) > 1]
    if dupes:
        unique_dupes = list(set(dupes))
        issues.append(f"log.md 중복 항목 {len(unique_dupes)}개: {unique_dupes[:3]}")
    else:
        print("  ✅ log.md 중복 없음")


def check_index_vs_outputs():
    if not INDEX_PATH.exists():
        warnings.append("index.md 없음")
        return
    index_content = INDEX_PATH.read_text(encoding="utf-8")
    actual_files = {f.name for f in OUTPUTS_DIR.glob("*.md")} if OUTPUTS_DIR.exists() else set()
    # index에서 참조된 파일명 추출 (standard links only, not wikilinks)
    # Standard: [filename.md](path) — match [filename.md] not preceded by [
    referenced = set(re.findall(r'(?<!\[)\[([^\[\]]+\.md)\]\(', index_content))
    # 실제 있는데 index에 없는 파일
    missing_in_index = actual_files - referenced - {"README.md"}
    if missing_in_index:
        warnings.append(f"index.md 누락 파일 {len(missing_in_index)}개: {list(missing_in_index)[:3]}")
    else:
        print("  ✅ index.md ↔ outputs/ 일치")
    # index에 있는데 실제 없는 파일
    dangling = referenced - actual_files
    if dangling:
        issues.append(f"index.md 깨진 링크 {len(dangling)}개: {list(dangling)[:3]}")
    else:
        print("  ✅ index.md 깨진 링크 없음")


def check_wikilinks():
    md_files = list(ROOT.rglob("*.md"))
    wikilink_files = []
    for f in md_files:
        if ".git" in str(f) or ".worktrees" in str(f):
            continue
        try:
            if "[[" in f.read_text(encoding="utf-8"):
                wikilink_files.append(f.name)
        except Exception:
            pass
    if wikilink_files:
        print(f"  ✅ Wikilink 있는 파일: {len(wikilink_files)}개 ({', '.join(wikilink_files[:4])})")
    else:
        warnings.append("wikilink([[...]])이 있는 파일 0개 — 지식 그래프 연결 없음")


def check_context_files():
    required = ["Context/org.md", "Context/infrastructure.md", "Context/kpi-targets.md"]
    for path in required:
        full = ROOT / path
        if full.exists():
            size = full.stat().st_size
            if size > 10_000:
                warnings.append(f"{path}: {size}바이트 — 10KB 초과, 분리 검토")
            else:
                print(f"  ✅ {path} ({size}바이트)")
        else:
            issues.append(f"{path} 없음")


def check_log_recency():
    if not LOG_PATH.exists():
        return
    content = LOG_PATH.read_text(encoding="utf-8")
    dates = re.findall(r"## \[(\d{4}-\d{2}-\d{2})\]", content)
    if not dates:
        warnings.append("log.md에 날짜 항목 없음")
        return
    latest = max(dates)
    from datetime import date as d
    delta = (d.fromisoformat(today) - d.fromisoformat(latest)).days
    if delta > 14:
        warnings.append(f"log.md 마지막 항목이 {delta}일 전 ({latest}) — 업데이트 필요")
    else:
        print(f"  ✅ log.md 최신: {latest} ({delta}일 전)")


def main():
    print(f"\n{'='*50}")
    print(f"  SCM Vault Hygiene Check — {today}")
    print(f"{'='*50}\n")

    print("[1] log.md 중복 체크")
    check_log_duplicates()

    print("[2] index.md ↔ outputs/ 일치 체크")
    check_index_vs_outputs()

    print("[3] Wikilink 현황")
    check_wikilinks()

    print("[4] Context 파일 체크")
    check_context_files()

    print("[5] log.md 최신성")
    check_log_recency()

    print(f"\n{'='*50}")
    if issues:
        print(f"  🔴 ISSUES ({len(issues)}개):")
        for i in issues:
            print(f"    - {i}")
    if warnings:
        print(f"  🟡 WARNINGS ({len(warnings)}개):")
        for w in warnings:
            print(f"    - {w}")
    if not issues and not warnings:
        print("  🟢 ALL CLEAR — 볼트 상태 양호")
    print(f"{'='*50}\n")

    return len(issues)


if __name__ == "__main__":
    exit(main())
