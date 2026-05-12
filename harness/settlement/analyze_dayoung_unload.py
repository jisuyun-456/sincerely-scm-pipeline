"""
다영기획 출발 박종성 하차비 분석 (2026-01-01 ~ 2026-05-12)
"""
import os, re, time, sys
import requests
from dotenv import load_dotenv

load_dotenv()
PAT = os.environ.get("AIRTABLE_PAT", "")
TMS_BASE = "app4x70a8mOrIKsMf"
TBL = "tbllg1JoHclGYer7m"
DRIVER_PARK = "recXCfwVTqaoeQ9SS"

F_SC_ID        = "fldBUwhBlhOMsJZdv"
F_DATE         = "fldQvmEwwzvQW95h9"
F_PARTNER      = "fldM2u6RwLRrO7ymW"
F_FARE         = "fldRT95SC88KSBATT"
F_ORIGIN       = "fldb24I9EQ2KPXv6S"
F_DEST         = "fldyJHUh9gN44Ggnh"
F_BOX_TEXT     = "fldTjLDmw5sNGszeD"
F_BOX_DIRECT   = "fldRjMaXa5TdSsGDL"
F_BOX_QTY      = "fldGXhlBwI6toXSJC"
F_PROJECT_CODE = "fldTs3FzaSdGYEiKX"
F_BOX_DETAIL   = "fld3mM9dsztAP3IBH"  # 외박스 포장 내역 (rollup from 배송요청)


def _str(raw):
    if isinstance(raw, list):
        return str(raw[0] or "").strip() if raw else ""
    return str(raw or "").strip()


def parse_unload(box_text) -> int:
    if not box_text:
        return 0
    s = str(box_text)
    try:
        heavy  = int(re.search(r"중대(\d+)", s).group(1)) if re.search(r"중대(\d+)", s) else 0
        large  = int(re.search(r"(?<!중)(?<!특)대(\d+)", s).group(1)) if re.search(r"(?<!중)(?<!특)대(\d+)", s) else 0
        xlarge = int(re.search(r"특대(\d+)", s).group(1)) if re.search(r"특대(\d+)", s) else 0
        return min((heavy // 5) * 5000 + (large // 3) * 5000 + (xlarge // 3) * 5000, 50000)
    except Exception:
        return 0


def fetch_records():
    headers = {"Authorization": f"Bearer {PAT}"}
    url = f"https://api.airtable.com/v0/{TMS_BASE}/{TBL}"
    formula = (
        "AND({출하확정일}>='2026-01-01',{출하확정일}<'2026-05-13',"
        "NOT({배송파트너}=''))"
    )
    recs, cursor = [], None
    while True:
        params = {
            "filterByFormula": formula,
            "returnFieldsByFieldId": "true",
            "fields[]": [
                F_SC_ID, F_DATE, F_PARTNER, F_FARE,
                F_ORIGIN, F_DEST,
                F_BOX_TEXT, F_BOX_DIRECT, F_BOX_QTY, F_PROJECT_CODE, F_BOX_DETAIL,
            ],
            "pageSize": 100,
        }
        if cursor:
            params["offset"] = cursor
        r = requests.get(url, headers=headers, params=params, timeout=30)
        if not r.ok:
            raise RuntimeError(f"Airtable {r.status_code}: {r.text[:200]}")
        data = r.json()
        recs.extend(data.get("records", []))
        cursor = data.get("offset")
        if not cursor:
            break
        time.sleep(0.2)
    return recs


def main():
    out = sys.stdout.buffer

    all_recs = fetch_records()

    results = []
    for rec in all_recs:
        f = rec["fields"]
        if DRIVER_PARK not in (f.get(F_PARTNER) or []):
            continue
        origin = _str(f.get(F_ORIGIN))
        if "다영" not in origin and "성남시 중원구" not in origin:
            continue

        date    = (f.get(F_DATE) or "")[:10]
        sc_id   = _str(f.get(F_SC_ID))
        fare    = f.get(F_FARE) or 0
        dest    = _str(f.get(F_DEST))
        proj    = _str(f.get(F_PROJECT_CODE))
        is_pna  = "PNA" in proj.upper()

        box = _str(f.get(F_BOX_TEXT))
        box_src = "formula"
        if not box and is_pna:
            box = _str(f.get(F_BOX_DIRECT)) or _str(f.get(F_BOX_QTY)) or ""
            if not box:
                box = _str(f.get(F_BOX_DETAIL))
                box_src = "detail" if box else "-"
            else:
                box_src = "fallback"
        elif not box:
            box_src = "-"

        detail_raw = _str(f.get(F_BOX_DETAIL))  # 원본 보존 (표시용)
        unload = parse_unload(box)
        results.append({
            "sc_id": sc_id, "date": date, "fare": fare,
            "pna": is_pna, "proj": proj[:14],
            "box": box, "box_src": box_src, "detail_raw": detail_raw,
            "unload": unload, "dest": dest,
        })

    results.sort(key=lambda x: x["date"])

    out.write(f"다영기획 출발 박종성 (2026-01~05-12): {len(results)}건\n".encode("utf-8"))
    out.write("\n".encode())
    header = f"{'SC ID':<13} {'날짜':<11} {'fare':>9} {'하차비':>7}  {'src':<8}  포장내역 (원본)\n"
    out.write(header.encode("utf-8"))
    out.write(("-" * 90 + "\n").encode())

    total_unload = 0
    nonzero = 0
    for r in results:
        total_unload += r["unload"]
        if r["unload"] > 0:
            nonzero += 1
        detail_disp = r["detail_raw"][:50] if r["detail_raw"] else "(없음)"
        line = (
            f"{r['sc_id']:<13} {r['date']:<11} {r['fare']:>9,} {r['unload']:>7,}"
            f"  {r['box_src']:<8}  {detail_disp}\n"
        )
        out.write(line.encode("utf-8"))

    out.write(("-" * 90 + "\n").encode())

    pna_count  = sum(1 for r in results if r["pna"])
    npna_count = len(results) - pna_count
    unload_pna  = sum(r["unload"] for r in results if r["pna"])
    unload_npna = sum(r["unload"] for r in results if not r["pna"])

    summary = (
        f"합계: {len(results)}건  하차비 합계: {total_unload:,}원"
        f"  (>0: {nonzero}건 / =0: {len(results)-nonzero}건)\n"
        f"PNA건: {pna_count}건  하차비합계: {unload_pna:,}원\n"
        f"非PNA건: {npna_count}건  하차비합계: {unload_npna:,}원\n"
    )
    out.write(summary.encode("utf-8"))


if __name__ == "__main__":
    main()
