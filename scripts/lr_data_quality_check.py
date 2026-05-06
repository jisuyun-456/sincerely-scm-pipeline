"""
lr_data_quality_check.py
────────────────────────────────────────────────────────────────────────────
logistics_release 외박스 포장 내역 → PDF 생성 가능 여부 점검

핵심 질문: 패킹리스트·외박스 라벨지 PDF 생성에 문제 있는 레코드가 있는가?

분류:
  OK          — 1개 이상 박스 파싱 성공
  EMPTY       — 외박스 포장 내역 없음 (미입력/해당 없음)
  PARSE_FAIL  — 텍스트 있으나 박스 0개 파싱 → PDF 생성 실패
  PARTIAL     — 일부 라인 파싱 실패 (나머지는 OK)

사용법:
  python scripts/lr_data_quality_check.py
  python scripts/lr_data_quality_check.py --start 2026-01-01 --end 2026-05-04
  python scripts/lr_data_quality_check.py --show-fail-text
"""

import argparse, os, re, sys, time
from collections import Counter, defaultdict

import requests
from dotenv import load_dotenv

sys.stdout.reconfigure(encoding="utf-8")
load_dotenv()

BASE_ID = os.getenv("SERPA_BASE_ID", "appkRWtF2j99XgBTq")
TBL_LR  = os.getenv("SERPA_LR_TABLE_ID", "tblj53ZBaJBpScNNI")
PAT = (os.getenv("AIRTABLE_SERPA_PAT")
       or os.getenv("AIRTABLE_WMS_PAT")
       or os.getenv("AIRTABLE_PAT")
       or os.getenv("AIRTABLE_API_KEY", ""))
HEADERS = {"Authorization": f"Bearer {PAT}"}

# ────────────────────────────────────────────────────────────────────────────
# 파싱 패턴 (운영 버전 v3 — COMPACT 포함)
# ────────────────────────────────────────────────────────────────────────────
_BOX_ROW         = re.compile(r"^(\d+)(\s*\+\s*[^\s*]+(?:\([^)]*\))*)?\s*\*\s*(\d+)\s*(.+?)\s*$")
_BOX_ROW_INLINE  = re.compile(r"^(.+?)\s+(\d+(?:[+][^\s*]+)?)\s*\*\s*(\d+)\s+([대중소]형?)\s*$")
_BOX_ROW_COMPACT = re.compile(r"^(.+?)(\d+)\s*\*\s*(\d+)\s+(\S+(?:\s*\([^)]*\))?)\s*$")


def parse_detail(text: str, use_compact: bool = True) -> dict:
    """
    Returns:
        parsed_count    : 총 파싱된 카톤 수
        patterns_used   : 사용된 패턴 집합
        unmatched_lines : 어느 패턴도 박스 행으로 처리 못한 라인
        total_lines     : 비어있지 않은 라인 수
    """
    parsed_count   = 0
    patterns_used  = set()
    unmatched      = []
    current_item   = None
    total_lines    = 0

    for raw in (text or "").strip().splitlines():
        line = re.sub(r'\s+', ' ', raw).strip().rstrip('`').strip()
        if not line:
            continue
        total_lines += 1

        m = _BOX_ROW.match(line)
        if m and current_item:
            patterns_used.add("BOX_ROW")
            parsed_count += int(m.group(3))
            continue

        mi = _BOX_ROW_INLINE.match(line)
        if mi:
            patterns_used.add("INLINE")
            current_item = mi.group(1).strip()
            parsed_count += int(mi.group(3))
            continue

        if use_compact:
            mc = _BOX_ROW_COMPACT.match(line)
            if mc:
                patterns_used.add("COMPACT")
                current_item = mc.group(1).strip()
                parsed_count += int(mc.group(3))
                continue

        # 아이템명 행 또는 파싱 불가
        # BOX_ROW인데 preceding item이 없는 경우 = 파싱 불가
        if _BOX_ROW.match(line) and not current_item:
            unmatched.append(line)
        else:
            current_item = line

    return {
        "parsed_count":  parsed_count,
        "patterns_used": patterns_used,
        "unmatched":     unmatched,
        "total_lines":   total_lines,
    }


def classify(text: str) -> tuple[str, dict, dict]:
    """(status, v3_result, v2_result)"""
    if not (text or "").strip():
        return "EMPTY", {}, {}

    v3 = parse_detail(text, use_compact=True)
    v2 = parse_detail(text, use_compact=False)

    if v3["parsed_count"] == 0:
        status = "PARSE_FAIL"
    elif v3["unmatched"]:
        status = "PARTIAL"
    else:
        status = "OK"

    return status, v3, v2


# ────────────────────────────────────────────────────────────────────────────
# Airtable 조회
# ────────────────────────────────────────────────────────────────────────────
def airtable_get(table_id: str, params: dict) -> list:
    url = f"https://api.airtable.com/v0/{BASE_ID}/{table_id}"
    records, offset = [], None
    while True:
        p = dict(params)
        if offset:
            p["offset"] = offset
        r = requests.get(url, headers=HEADERS, params=p, timeout=30)
        r.raise_for_status()
        data = r.json()
        records.extend(data.get("records", []))
        offset = data.get("offset")
        if not offset:
            break
        time.sleep(0.2)
    return records


def fetch_lr(start: str, end: str) -> list:
    formula = (
        f'AND('
        f'IS_AFTER({{출고 요청일}}, DATEADD("{start}", -1, "days")), '
        f'IS_BEFORE({{출고 요청일}}, DATEADD("{end}", 1, "days")))'
    )
    return airtable_get(TBL_LR, {
        "fields[]": ["프로젝트명 (출고)", "출고 요청일", "외박스 포장 내역"],
        "filterByFormula": formula,
        "pageSize": 100,
        "sort[0][field]": "출고 요청일",
        "sort[0][direction]": "asc",
    })


# ────────────────────────────────────────────────────────────────────────────
# 분석
# ────────────────────────────────────────────────────────────────────────────
def analyze(records: list) -> dict:
    by_status = defaultdict(list)
    compact_gain = []   # COMPACT 패턴이 카톤 수를 추가로 파악한 레코드

    for rec in records:
        f    = rec.get("fields", {})
        to   = f.get("프로젝트명 (출고)", "")
        date = f.get("출고 요청일", "")
        text = f.get("외박스 포장 내역", "")

        status, v3, v2 = classify(text)

        row = {
            "record_id": rec["id"],
            "to":        to,
            "date":      date,
            "text":      text,
            "status":    status,
            "v3":        v3,
            "v2":        v2,
        }
        by_status[status].append(row)

        # COMPACT 기여 확인
        if v3 and v2 and v3.get("parsed_count", 0) > v2.get("parsed_count", 0):
            compact_gain.append(row)

    return {"by_status": dict(by_status), "compact_gain": compact_gain}


# ────────────────────────────────────────────────────────────────────────────
# 리포트
# ────────────────────────────────────────────────────────────────────────────
def print_report(total: int, result: dict, show_fail_text: bool) -> None:
    by_status     = result["by_status"]
    compact_gain  = result["compact_gain"]

    ok_n     = len(by_status.get("OK", []))
    empty_n  = len(by_status.get("EMPTY", []))
    fail_n   = len(by_status.get("PARSE_FAIL", []))
    partial_n= len(by_status.get("PARTIAL", []))

    print(f"\n{'='*65}")
    print(f"  logistics_release PDF 생성 가능성 점검")
    print(f"  기간 내 전체: {total}건")
    print(f"{'='*65}")

    print(f"\n  ✅ OK (박스 파싱 성공)     : {ok_n:>4}건  ({ok_n/total*100:.1f}%)")
    print(f"  ⬜ EMPTY (포장 내역 미입력) : {empty_n:>4}건  ({empty_n/total*100:.1f}%)")
    print(f"  ❌ PARSE_FAIL (텍스트 있으나 박스 0개) : {fail_n:>4}건  ({fail_n/total*100:.1f}%)")
    print(f"  ⚠️  PARTIAL (일부 라인 파싱 불가)       : {partial_n:>4}건  ({partial_n/total*100:.1f}%)")

    # 포장 내역 있는 레코드 기준 성공률
    with_text = ok_n + fail_n + partial_n
    if with_text:
        ok_rate = ok_n / with_text * 100
        print(f"\n  [포장 내역 있는 {with_text}건 기준 파싱 성공률: {ok_rate:.1f}%]")

    # COMPACT 기여
    print(f"\n── _BOX_ROW_COMPACT 패턴 기여 ──────────────────────────────")
    print(f"  COMPACT로 추가 카톤 파싱된 레코드: {len(compact_gain)}건")
    if compact_gain:
        for r in compact_gain:
            v3c = r['v3']['parsed_count']
            v2c = r['v2']['parsed_count']
            print(f"    {r['to']:<20} {r['date']}  v2={v2c} → v3={v3c}  (+{v3c-v2c}박스)")

    # PARSE_FAIL 상세
    fail_list = by_status.get("PARSE_FAIL", [])
    if fail_list:
        print(f"\n── PARSE_FAIL 상세 ({fail_n}건) ────────────────────────────────")
        for r in fail_list:
            print(f"  {r['to']:<20} {r['date']}")
            if show_fail_text and r['text']:
                for line in r['text'].strip().splitlines()[:5]:
                    print(f"    | {line[:70]}")
                if len(r['text'].strip().splitlines()) > 5:
                    print(f"    | ... (+{len(r['text'].strip().splitlines())-5}줄)")

    # PARTIAL 상세
    partial_list = by_status.get("PARTIAL", [])
    if partial_list:
        print(f"\n── PARTIAL 상세 ({partial_n}건) ─────────────────────────────────")
        for r in partial_list:
            unmatched = r['v3'].get('unmatched', [])
            print(f"  {r['to']:<20} {r['date']}  파싱됨={r['v3']['parsed_count']}박스  미처리라인={len(unmatched)}개")
            if show_fail_text:
                for line in unmatched[:3]:
                    print(f"    미처리: {line[:70]}")

    # 패턴 분포 (OK+PARTIAL 기준)
    print(f"\n── 파싱 성공 레코드 패턴 분포 ──────────────────────────────")
    pt_counter: Counter = Counter()
    for r in by_status.get("OK", []) + by_status.get("PARTIAL", []):
        key = "+".join(sorted(r['v3']['patterns_used'])) or "NONE"
        pt_counter[key] += 1
    for k, v in pt_counter.most_common():
        print(f"  {k:<25} {v:>4}건")

    print(f"\n{'='*65}\n")


# ────────────────────────────────────────────────────────────────────────────
# 메인
# ────────────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default="2026-01-01")
    parser.add_argument("--end",   default="2026-05-04")
    parser.add_argument("--show-fail-text", action="store_true",
                        help="PARSE_FAIL/PARTIAL 레코드 포장 내역 텍스트 출력")
    args = parser.parse_args()

    if not PAT:
        print("❌ PAT 없음. .env에 AIRTABLE_SERPA_PAT 설정 필요.")
        sys.exit(1)

    print(f"\n📋 logistics_release PDF 생성 가능성 점검")
    print(f"   기간: {args.start} ~ {args.end}")
    print(f"\n[1/2] Airtable 조회 중...")
    records = fetch_lr(args.start, args.end)
    print(f"  → {len(records)}건")

    if not records:
        print("조회 결과 없음.")
        return

    print(f"[2/2] 분석 중...")
    result = analyze(records)
    print_report(len(records), result, args.show_fail_text)


if __name__ == "__main__":
    main()
