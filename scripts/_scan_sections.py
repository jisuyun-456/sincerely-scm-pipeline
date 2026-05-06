"""Scan logistics_release for section-style packing texts."""
import os, re, sys, time, requests
from dotenv import load_dotenv

load_dotenv()
sys.stdout.reconfigure(encoding="utf-8")

BASE_ID = os.getenv("SERPA_BASE_ID", "appkRWtF2j99XgBTq")
TBL_LR  = os.getenv("SERPA_LR_TABLE_ID", "tblj53ZBaJBpScNNI")
PAT     = (os.getenv("AIRTABLE_SERPA_PAT") or os.getenv("AIRTABLE_WMS_PAT")
           or os.getenv("AIRTABLE_PAT") or "")
HEADERS = {"Authorization": f"Bearer {PAT}"}

# (사업실), (개발실), (SKEL재직)79, (KEVIT재직)79 등 — 섹션 구분자 라인
_SECTION_LINE = re.compile(r"^\(([^)]+)\)\s*\d*\s*$")


def detect_sections(text: str) -> list[str]:
    sections = []
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        m = _SECTION_LINE.match(line)
        if m:
            sections.append(m.group(1))
    return sections


def fetch_all():
    url = f"https://api.airtable.com/v0/{BASE_ID}/{TBL_LR}"
    records, offset = [], None
    while True:
        p = {
            "fields[]": ["프로젝트명 (출고)", "출고 요청일", "외박스 포장 내역"],
            "filterByFormula": (
                'AND(IS_AFTER({출고 요청일}, DATEADD("2025-12-31", 0, "days")),'
                'NOT({외박스 포장 내역} = ""))'
            ),
            "pageSize": 100,
            "sort[0][field]": "출고 요청일",
            "sort[0][direction]": "asc",
        }
        if offset:
            p["offset"] = offset
        r = requests.get(url, headers=HEADERS, params=p, timeout=60)
        r.raise_for_status()
        d = r.json()
        records.extend(d.get("records", []))
        offset = d.get("offset")
        if not offset:
            break
        time.sleep(0.2)
    return records


def main():
    print("조회 중...")
    records = fetch_all()
    print(f"포장 내역 있는 건: {len(records)}건\n")

    hits = []
    for rec in records:
        f = rec["fields"]
        text = f.get("외박스 포장 내역", "")
        secs = detect_sections(text)
        if secs:
            hits.append({
                "to":       f.get("프로젝트명 (출고)", ""),
                "date":     (f.get("출고 요청일") or "")[:10],
                "sections": secs,
                "text":     text,
            })

    print(f"섹션 패턴 감지: {len(hits)}건\n")
    print(f"{'프로젝트명':<24} {'날짜':<12} 섹션")
    print("-" * 70)
    for h in hits:
        print(f"  {h['to']:<22} {h['date']}  {h['sections']}")
        for line in h["text"].strip().splitlines()[:8]:
            print(f"    | {line[:70]}")
        print()


if __name__ == "__main__":
    main()
