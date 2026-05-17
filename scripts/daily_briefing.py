"""
SCM Daily Briefing Generator
매일 아침 실행 → _AutoResearch/SCM/outputs/daily-YYYY-MM-DD.md 생성
실행: python scripts/daily_briefing.py
"""

import json
import re
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).parent.parent
LOG_PATH = ROOT / "_AutoResearch/SCM/wiki/log.md"
FEATURE_PATH = ROOT / ".claude/feature_list.json"
KPI_PATH = ROOT / "Context/kpi-targets.md"
OUTPUT_DIR = ROOT / "_AutoResearch/SCM/outputs"
INDEX_PATH = ROOT / "_AutoResearch/SCM/wiki/index.md"

today = date.today().isoformat()


def get_recent_log_entries(n=3):
    if not LOG_PATH.exists():
        return []
    content = LOG_PATH.read_text(encoding="utf-8")
    pattern = r"(## \[\d{4}-\d{2}-\d{2}\][^\n]+)(.*?)(?=## \[|\Z)"
    matches = list(re.finditer(pattern, content, re.DOTALL))
    return matches[-n:] if matches else []


def get_pending_tasks():
    if not FEATURE_PATH.exists():
        return []
    data = json.loads(FEATURE_PATH.read_text(encoding="utf-8"))
    priority_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    pending = [t for t in data.get("tasks", []) if t.get("status") == "pending"]
    return sorted(pending, key=lambda x: priority_order.get(x.get("priority", "low"), 99))


def get_kpi_trend():
    if not KPI_PATH.exists():
        return "KPI 파일 없음"
    content = KPI_PATH.read_text(encoding="utf-8")
    # 주간 추세 테이블 추출
    match = re.search(r"## 주간 추세.*?\n(.*?)(?=\n##|\Z)", content, re.DOTALL)
    if match:
        return match.group(0).strip()
    return ""


def get_open_issues():
    if not KPI_PATH.exists():
        return []
    content = KPI_PATH.read_text(encoding="utf-8")
    match = re.search(r"## 이슈 트래킹.*?\n(.*?)(?=\n##|\Z)", content, re.DOTALL)
    if not match:
        return []
    lines = [l.strip() for l in match.group(1).strip().split("\n") if l.strip() and "|" in l and "---" not in l and "이슈" not in l]
    return lines


def build_briefing():
    sections = []

    sections.append(f"# SCM 일일 브리핑 — {today}\n")
    sections.append(f"> 자동 생성: {datetime.now().strftime('%Y-%m-%d %H:%M')} KST\n")
    sections.append("---\n")

    # 미완료 태스크
    pending = get_pending_tasks()
    sections.append("## 오늘의 우선 태스크\n")
    if pending:
        for t in pending[:3]:
            badge = t.get("priority", "low").upper()
            sections.append(f"- **[{badge}]** {t['title']}")
            if t.get("notes"):
                note = t["notes"][:80] + ("..." if len(t["notes"]) > 80 else "")
                sections.append(f"  > {note}")
    else:
        sections.append("- (없음)")
    sections.append("")

    # 이슈 트래킹
    issues = get_open_issues()
    sections.append("## 오픈 이슈\n")
    if issues:
        for issue in issues:
            sections.append(f"{issue}")
    else:
        sections.append("- (없음)")
    sections.append("")

    # KPI 추세
    trend = get_kpi_trend()
    if trend:
        sections.append(f"## KPI 추세\n\n{trend}\n")

    # 최근 세션 로그
    log_entries = get_recent_log_entries(2)
    sections.append("## 최근 세션 요약\n")
    if log_entries:
        for m in reversed(log_entries):
            header = m.group(1).strip()
            body = m.group(2).strip()
            status = re.search(r"\*\*상태:\*\* (.+)", body)
            focus = re.search(r"### 다음 포커스\n(.*?)(?=###|\Z)", body, re.DOTALL)
            sections.append(f"\n**{header}**")
            if status:
                sections.append(f"상태: {status.group(1)}")
            if focus:
                lines = [l.strip() for l in focus.group(1).strip().split("\n") if l.strip()]
                for line in lines[:2]:
                    sections.append(f"→ {line.lstrip('- ')}")
    else:
        sections.append("- (로그 없음)")
    sections.append("")

    # 연관 파일
    sections.append("## 연관 파일\n")
    sections.append("- [[Context/kpi-targets.md|KPI 목표 및 추세]]")
    sections.append("- [[Context/org.md|조직/팀 정보]]")
    sections.append("- [[_AutoResearch/SCM/wiki/log.md|세션 로그]]")
    sections.append("- [[_AutoResearch/SCM/wiki/index.md|산출물 인덱스]]")

    return "\n".join(sections)


def update_index(filename):
    if not INDEX_PATH.exists():
        return
    content = INDEX_PATH.read_text(encoding="utf-8")
    link = f"| [{filename}](../outputs/{filename}) | 일일 브리핑 | {today} | 완료 |"
    if filename not in content:
        content = content.rstrip() + "\n" + link + "\n"
        INDEX_PATH.write_text(content, encoding="utf-8")


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"daily-{today}.md"
    output_path = OUTPUT_DIR / filename

    briefing = build_briefing()
    output_path.write_text(briefing, encoding="utf-8")
    update_index(filename)

    print(f"[Daily Briefing] {output_path} 생성 완료")
    print(f"  - 미완료 태스크: {len(get_pending_tasks())}개")
    print(f"  - 세션 로그 최근: {len(get_recent_log_entries())}개")


if __name__ == "__main__":
    main()
