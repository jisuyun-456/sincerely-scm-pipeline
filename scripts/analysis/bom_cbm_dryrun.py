"""
BOM·CBM 수량전파 백본 — Phase-1 검증 dry-run (read-only).

§4 검증 게이트 3종 측정:
  1. 키 매칭률  — WMS order 굿즈명 ↔ TMS Product(견적코드 385) match_product 성공률 (Tier A, CBM 결선)
  2. CBM 커버리지 — TMS Product CBM>0 비율 + 매칭된 굿즈의 CBM 확보율
  3. BOM 부트스트랩 적용율 — WMS order를 굿즈로 그룹핑 → 파츠(PT####) 구성 + 소요량 산출 가능 비율

쓰기 없음. PAT는 환경변수로만:
  AIRTABLE_PAT (TMS) / AIRTABLE_WMS_PAT (WMS)
실행:
  AIRTABLE_PAT=... AIRTABLE_WMS_PAT=... python scripts/analysis/bom_cbm_dryrun.py
"""
import os
import re
import sys
import urllib.parse
import urllib.request
from collections import defaultdict

sys.path.insert(0, os.path.abspath("."))
from harness.settlement.cbm_calc import load_product_lookup, match_product  # noqa: E402

WMS_BASE = "appLui4ZR5HWcQRri"
TBL_ORDER = "tblJslWg8sYEdCkXw"
SERVICE_KW = ("배송", "하차", "퀵", "다마스", "택배", "설치", "용차", "탑차")
PT_RE = re.compile(r"\b(PT\d{3,6})\b")
TRAIL_QTY = re.compile(r"\s+(\d[\d,]*)\s*$")


def headers(pat: str) -> dict:
    return {"Authorization": f"Bearer {pat}"}


def goods_name(s: str) -> tuple[str, int]:
    """'심볼아크릴트로피 125' -> ('심볼아크릴트로피', 125). qty 없으면 0."""
    s = (s or "").strip()
    m = TRAIL_QTY.search(s)
    if m:
        qty = int(m.group(1).replace(",", ""))
        return s[: m.start()].strip(), qty
    return s, 0


def is_service(name: str) -> bool:
    return any(k in name for k in SERVICE_KW)


def fetch_orders(pat: str, limit: int) -> list[dict]:
    fields = ["project_code", "굿즈 주문 수량 (자동)", "주문수량", "파츠명"]
    out: list[dict] = []
    cursor = None
    while len(out) < limit:
        params = [("pageSize", "100")]
        for f in fields:
            params.append(("fields[]", f))
        if cursor:
            params.append(("offset", cursor))
        url = f"https://api.airtable.com/v0/{WMS_BASE}/{TBL_ORDER}?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, headers=headers(pat))
        import json
        data = json.load(urllib.request.urlopen(req))
        out.extend(data.get("records", []))
        cursor = data.get("offset")
        if not cursor:
            break
    return out[:limit]


def main() -> None:
    tms_pat = os.environ["AIRTABLE_PAT"]
    wms_pat = os.environ["AIRTABLE_WMS_PAT"]

    print("=" * 64)
    print("BOM·CBM 백본 Phase-1 검증 dry-run (read-only)")
    print("=" * 64)

    # ---- TMS Product lookup (CBM 마스터) ----
    lookup = load_product_lookup(headers(tms_pat))
    products = {e["rec_id"]: e for e in lookup.values()}
    n_prod = len(products)
    n_cbm = sum(1 for e in products.values() if e["cbm_per_box"] > 0)
    print(f"\n[Gate 2] TMS Product 마스터")
    print(f"   품목 수: {n_prod}")
    print(f"   CBM>0 커버리지: {n_cbm}/{n_prod} = {n_cbm/n_prod*100:.1f}%")

    # ---- WMS orders sample ----
    orders = fetch_orders(wms_pat, 1500)
    print(f"\n   WMS order 샘플: {len(orders)}행")

    # ---- Gate 1: 굿즈명 ↔ TMS Product 매칭률 (Tier A, CBM 결선) ----
    goods_seen: dict[str, int] = {}  # 굿즈명 -> 등장 횟수
    for r in orders:
        gn, _ = goods_name(r["fields"].get("굿즈 주문 수량 (자동)", ""))
        if gn and not is_service(gn):
            goods_seen[gn] = goods_seen.get(gn, 0) + 1
    matched = matched_cbm = 0
    low_conf: list[str] = []
    for gn in goods_seen:
        key, entry, score = match_product(gn, lookup)
        if entry is not None:
            matched += 1
            if entry["cbm_per_box"] > 0:
                matched_cbm += 1
        else:
            low_conf.append(gn)
    n_goods = len(goods_seen)
    print(f"\n[Gate 1] 굿즈명 ↔ TMS Product 매칭 (Tier A · CBM 결선)")
    print(f"   distinct 굿즈명(서비스 제외): {n_goods}")
    if n_goods:
        print(f"   매칭 성공: {matched}/{n_goods} = {matched/n_goods*100:.1f}%")
        print(f"   매칭+CBM 확보: {matched_cbm}/{n_goods} = {matched_cbm/n_goods*100:.1f}%")
    print(f"   미매칭 예시: {low_conf[:12]}")

    # ---- Gate 2b: 파츠명 PT#### 추출률 (Tier B) ----
    pt_hit = pt_total = 0
    for r in orders:
        pn = r["fields"].get("파츠명", "")
        if pn:
            pt_total += 1
            if PT_RE.search(pn):
                pt_hit += 1
    print(f"\n[Gate 2b] 파츠명 PT#### 추출 (Tier B · BOM 구성품 결선)")
    if pt_total:
        print(f"   PT#### 추출: {pt_hit}/{pt_total} = {pt_hit/pt_total*100:.1f}%")

    # ---- Gate 3: BOM 부트스트랩 적용율 (굿즈 그룹핑 → 소요량) ----
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for r in orders:
        f = r["fields"]
        pc = f.get("project_code", "")
        gn, gqty = goods_name(f.get("굿즈 주문 수량 (자동)", ""))
        pn = f.get("파츠명", "")
        if isinstance(pc, list):
            pc = pc[0] if pc else ""
        if pc and gn and not is_service(gn) and PT_RE.search(pn or ""):
            groups[(str(pc), gn)].append({
                "pt": PT_RE.search(pn).group(1),
                "order_qty": f.get("주문수량", 0),
                "goods_qty": gqty,
            })
    usable = with_soyo = 0
    examples = []
    for (pc, gn), lines in groups.items():
        usable += 1
        gq = max((ln["goods_qty"] for ln in lines), default=0)
        if gq > 0 and all(isinstance(ln["order_qty"], (int, float)) for ln in lines):
            with_soyo += 1
            if len(examples) < 3:
                comp = [(ln["pt"], (ln["order_qty"] / gq) if gq else None) for ln in lines[:6]]
                examples.append((pc, gn, gq, comp))
    print(f"\n[Gate 3] BOM 부트스트랩 적용율 (굿즈 그룹핑 → 소요량)")
    print(f"   (project,굿즈) 그룹: {len(groups)}")
    if groups:
        print(f"   소요량 산출 가능: {with_soyo}/{len(groups)} = {with_soyo/len(groups)*100:.1f}%")
    for pc, gn, gq, comp in examples:
        print(f"   예) {pc} / {gn} (굿즈수량 {gq})")
        for pt, soyo in comp:
            print(f"        {pt}  소요량/개 = {soyo:.3f}" if soyo is not None else f"        {pt}  소요량 미산출")

    print("\n" + "=" * 64)
    print("dry-run 완료 (쓰기 0건)")
    print("=" * 64)


if __name__ == "__main__":
    main()
