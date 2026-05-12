"""
품목 매칭 기반 하차비 추정 — 다영기획 출발 박종성 (2026-01~05-12)

전략:
  1. 2024-01-01~현재 전체 Shipment 중 최종 외박스 수량 값이 있는 레코드로
     품목 → 박스구성 룩업 테이블 빌드
  2. 다영기획 출발 박종성 건 중 박스 데이터 없는 건에서 최종 출하 품목 조회
  3. 품목 텍스트 매칭 (exact → Jaccard 토큰 유사도)으로 박스구성 추정
  4. parse_unload_fee 적용해 하차비 계산
"""
import os, re, time, sys
from collections import defaultdict, Counter
import requests
from dotenv import load_dotenv

load_dotenv()
PAT = os.environ.get("AIRTABLE_PAT", "")
TMS_BASE = "app4x70a8mOrIKsMf"
TBL = "tbllg1JoHclGYer7m"
DRIVER_PARK = "recXCfwVTqaoeQ9SS"

# Field IDs
F_SC_ID        = "fldBUwhBlhOMsJZdv"
F_DATE         = "fldQvmEwwzvQW95h9"
F_PARTNER      = "fldM2u6RwLRrO7ymW"
F_FARE         = "fldRT95SC88KSBATT"
F_ORIGIN       = "fldb24I9EQ2KPXv6S"
F_BOX_TEXT     = "fldTjLDmw5sNGszeD"   # 최종 외박스 수량 값
F_BOX_DIRECT   = "fldRjMaXa5TdSsGDL"   # 외박스 수량 직접입력
F_BOX_QTY      = "fldGXhlBwI6toXSJC"   # 외박스 수량 rollup
F_PRODUCT_FINAL = "fldgSupj5XLjJXYQo"  # 최종 출하 품목 (formula)
F_PRODUCT_ROLLUP = "fldZALJRcwwEmkyQh" # 출하 품목 (rollup)
F_PROJECT_CODE = "fldTs3FzaSdGYEiKX"


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


def tokenize(text: str) -> frozenset:
    """품목 텍스트를 토큰 집합으로 — 숫자/기호 제거, 2자 이상 한국어/영어만 유지"""
    tokens = set()
    for part in re.split(r"[\s,+×\(\)/·]+", text):
        stripped = re.sub(r"\d+", "", part).strip()
        if len(stripped) >= 2:
            tokens.add(stripped.lower())
    return frozenset(tokens)


def jaccard(a: frozenset, b: frozenset) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def fetch_all(formula: str, fields: list[str]) -> list[dict]:
    """Airtable 페이지네이션 헬퍼"""
    headers = {"Authorization": f"Bearer {PAT}"}
    url = f"https://api.airtable.com/v0/{TMS_BASE}/{TBL}"
    recs, cursor = [], None
    while True:
        params = {
            "filterByFormula": formula,
            "returnFieldsByFieldId": "true",
            "fields[]": fields,
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


def build_lookup(recs: list[dict]) -> dict:
    """
    품목 텍스트 → Counter({box_text: count}) 룩업 테이블 빌드
    같은 품목에 여러 박스 구성이 있으면 가장 많이 쓰인 것을 대표값으로 사용
    """
    lookup: dict[str, Counter] = defaultdict(Counter)
    for rec in recs:
        f = rec["fields"]
        box = _str(f.get(F_BOX_TEXT))
        if not box:
            continue
        product = _str(f.get(F_PRODUCT_FINAL)) or _str(f.get(F_PRODUCT_ROLLUP))
        if not product:
            continue
        lookup[product.strip()][box] += 1
    return lookup


def find_best_match(product: str, lookup: dict) -> tuple[str, str, float]:
    """
    룩업 테이블에서 가장 유사한 품목 찾기.
    Returns: (matched_product_key, best_box_text, score)
    score=1.0 → exact match
    """
    product = product.strip()

    # 1) exact match
    if product in lookup:
        best_box = lookup[product].most_common(1)[0][0]
        return product, best_box, 1.0

    # 2) token Jaccard 유사도
    target_tokens = tokenize(product)
    if not target_tokens:
        return "", "", 0.0

    best_key, best_score = "", 0.0
    for key in lookup:
        score = jaccard(target_tokens, tokenize(key))
        if score > best_score:
            best_score = score
            best_key = key

    if best_score >= 0.4:
        best_box = lookup[best_key].most_common(1)[0][0]
        return best_key, best_box, best_score

    return "", "", 0.0


def main():
    out = sys.stdout.buffer

    # ── Step 1: 룩업 테이블 빌드 (2024-01~ 전체 박스 데이터 있는 건) ──
    out.write("Step 1: 박스 룩업 테이블 빌드 중 (2024-01~현재)...\n".encode("utf-8"))
    lookup_recs = fetch_all(
        formula="AND({출하확정일}>='2024-01-01',NOT({최종 외박스 수량 값}=''))",
        fields=[F_PRODUCT_FINAL, F_PRODUCT_ROLLUP, F_BOX_TEXT],
    )
    lookup = build_lookup(lookup_recs)
    out.write(f"  룩업 품목 수: {len(lookup)}종  (원본 레코드: {len(lookup_recs)}건)\n\n".encode("utf-8"))

    # ── Step 2: 다영기획 출발 박종성 건 조회 (박스 없는 것만) ──
    out.write("Step 2: 다영기획 출발 박종성 건 조회 중...\n".encode("utf-8"))
    all_recs = fetch_all(
        formula="AND({출하확정일}>='2026-01-01',{출하확정일}<'2026-05-13',NOT({배송파트너}=''))",
        fields=[F_SC_ID, F_DATE, F_PARTNER, F_FARE, F_ORIGIN,
                F_BOX_TEXT, F_BOX_DIRECT, F_BOX_QTY,
                F_PRODUCT_FINAL, F_PRODUCT_ROLLUP, F_PROJECT_CODE],
    )
    targets = []
    for rec in all_recs:
        f = rec["fields"]
        if DRIVER_PARK not in (f.get(F_PARTNER) or []):
            continue
        origin = _str(f.get(F_ORIGIN))
        if "다영" not in origin and "성남시 중원구" not in origin:
            continue
        # 박스 데이터 이미 있는 건 제외
        box = _str(f.get(F_BOX_TEXT)) or _str(f.get(F_BOX_DIRECT)) or _str(f.get(F_BOX_QTY))
        if box:
            continue
        targets.append({
            "rec_id": rec["id"],
            "sc_id":  _str(f.get(F_SC_ID)),
            "date":   (f.get(F_DATE) or "")[:10],
            "fare":   f.get(F_FARE) or 0,
            "product": _str(f.get(F_PRODUCT_FINAL)) or _str(f.get(F_PRODUCT_ROLLUP)),
            "proj":   _str(f.get(F_PROJECT_CODE))[:12],
        })
    targets.sort(key=lambda x: x["date"])
    out.write(f"  박스 데이터 없는 다영기획 건: {len(targets)}건\n\n".encode("utf-8"))

    # ── Step 3: 품목 매칭 → 하차비 추정 ──
    out.write("Step 3: 품목 매칭 결과\n".encode("utf-8"))
    header = (
        f"{'SC ID':<13} {'날짜':<11} {'fare':>9} {'하차비':>7}  {'점수':>5}  "
        f"{'품목':<30}  매칭된 박스구성\n"
    )
    out.write(header.encode("utf-8"))
    out.write(("-" * 105 + "\n").encode())

    total_unload = 0
    matched = 0
    unmatched_products = []
    results = []
    for r in targets:
        product = r["product"]
        matched_key, box_text, score = find_best_match(product, lookup)
        unload = parse_unload(box_text)

        results.append({**r, "matched_key": matched_key, "box_text": box_text,
                        "score": score, "unload": unload})
        total_unload += unload
        if score > 0:
            matched += 1
        else:
            unmatched_products.append((r["sc_id"], product))

        score_str = f"{score:.2f}" if score > 0 else "  -  "
        prod_disp = (product or "(없음)")[:28]
        box_disp  = box_text[:35] if box_text else "(매칭 실패)"
        line = (
            f"{r['sc_id']:<13} {r['date']:<11} {r['fare']:>9,} {unload:>7,}"
            f"  {score_str:>5}  {prod_disp:<30}  {box_disp}\n"
        )
        out.write(line.encode("utf-8"))

    out.write(("-" * 105 + "\n").encode())

    # ── 요약 ──
    nonzero = sum(1 for r in results if r["unload"] > 0)
    summary = (
        f"\n합계: {len(results)}건  하차비 추정 합계: {total_unload:,}원"
        f"  (>0: {nonzero}건 / =0: {len(results)-nonzero}건)\n"
        f"품목 매칭: {matched}건 / 미매칭: {len(results)-matched}건\n"
    )
    out.write(summary.encode("utf-8"))

    if unmatched_products:
        out.write("\n미매칭 품목 목록:\n".encode("utf-8"))
        for sc, prod in unmatched_products:
            out.write(f"  {sc}: {prod or '(품목 없음)'}\n".encode("utf-8"))

    # ── 박스구성별 빈도 ──
    out.write("\n[추정 박스구성 분포]\n".encode("utf-8"))
    box_counter: Counter = Counter(r["box_text"] for r in results if r["box_text"])
    for box, cnt in box_counter.most_common(10):
        fee = parse_unload(box)
        out.write(f"  {box:<35}  → 하차비 {fee:>6,}원  ({cnt}건)\n".encode("utf-8"))


if __name__ == "__main__":
    main()
