"""V2 견적코드 reconciliation — WMS sync_item 코드를 TMS Product 등록 코드로 정합.

근거 (2026-06-16, adversarial-verified against registered siblings):
cascade S5 "출하CBM 미산출" 견적코드는 대부분 '미등록'이 아니라 WMS sync_item이
굿즈명에 붙이는 코드 ≠ TMS Product 등록 견적코드인 **코드 불일치**다.
- 동일명/세대 쌍둥이 → 1:1 alias (등록된 권위 스펙 그대로 점등)
- 사이즈 변형군 → 굿즈명 사이즈 토큰 파싱으로 사이즈 SKU 매핑 (없으면 __default__)

원칙: Product/WMS 운영 데이터 쓰기 없음. 캐스케이드 런타임에서만 코드 정합.
미해소 시 원본 코드 그대로 반환 → S5가 정직하게 "미산출" 보고 (silent-match 금지).
"""
import re

# 동일명/세대 쌍둥이 — WMS코드 → 등록된 권위 코드 (1:1)
ALIAS = {
    "LOPU": "LSPO",   # 로고스트랩 파우치        (LSPO 대형/100)
    "STTB": "STNB",   # 스탠드-업 칫솔           (STNB 중대형/60)
    "WCCV": "WCV",    # 웹캠 커버               (WCV 극소형/100)
    "SLVB": "SLVR",   # Quality 슬리브박스       (SLVR 특대형/20)
    "BCTW": "BCTL",   # 굿이너프 비치타월         (BCTL 대형/40)
    "CNPB": "CNPG",   # 컬러풀 노트패드(블랙)      (CNPG 중대형/100)
    "BMVS": "BMCH",   # 브릭 메모&캘린더 스탠드 v1→2.0 (BMCH 중대형/20)
    "DSKT": "DSKS",   # 데스크테리어 매트(사이즈 무표기) → 기본형 (DSKS 대형/30, 0.1066). 사용자 확정 2026-06-16
}

# Product 미등록 신규 SKU — 사용자 견적 입력 권위 박스 스펙. 런타임 product_lookup 주입(Product 쓰기 0).
# alias/SIZE_FAMILY로 기존 등록코드에 환원 불가한 고유 스펙(qty_per_box)인 경우만 등재.
# cbm_per_box는 표준 박스타입(cbm_calc.BOX_TYPE_TO_CBM_M3)에서 해소 — 단일 SSOT.
SYNTHETIC = {
    # TWKF Lite 스트랩 박스 — 대형 박스 L510(510×510×410), 박스당 12. 사용자 확정 2026-06-16.
    "TWKF": {"name": "Lite 스트랩 박스", "box_type": "대형", "qty_per_box": 12},
}

# 사이즈 변형군 — WMS코드 → {size: 등록 SKU코드}. __default__ 필수 (굿즈명에 사이즈 없을 때).
SIZE_FAMILY = {
    "DRCG": {"S": "SOLA", "M": "SOLB", "L": "SOLC", "__default__": "SOLB"},
    "SZBT": {"S": "SLZS", "M": "SLZB", "L": "SLZL", "__default__": "SLZB"},
    # ⚠️ VMCB: VMC 계열(VMCM 중형/48, VMCS 중형/100)에 매핑. VLM 계열(VLMM/VLMS 중대형/170)은
    #    명명·스펙이 별개·불일치 — 사용자 확인 전 VMC 계열 채택.
    "VMCB": {"S": "VMCS", "M": "VMCM", "__default__": "VMCM"},
    # RWCP(S,M)는 박스/수량 미입력 → S/M도 RWCL로 폴백.
    "RCPC": {"S": "RWCL", "M": "RWCL", "L": "RWCL", "XL": "RWCL", "__default__": "RWCL"},
}

_SIZE_KO = [("XL사이즈", "XL"), ("L사이즈", "L"), ("M사이즈", "M"), ("S사이즈", "S")]
_SIZE_PAREN = re.compile(r"\((XL|[SMLsml])\)")


def parse_size(goods_name):
    """굿즈명에서 사이즈 토큰 추출 (XL>L>M>S 우선). 없으면 None.

    예: 'Solid스탠다드G형박스(M사이즈)' → 'M' / '밸류메모큐브(S)' → 'S'.
    """
    s = goods_name or ""
    for ko, sz in _SIZE_KO:
        if ko in s:
            return sz
    m = _SIZE_PAREN.search(s)
    if m:
        return m.group(1).upper()
    return None


def _registered(code, lookup):
    """code가 product_lookup에 cbm_per_box>0로 존재하면 True."""
    e = lookup.get(str(code).lower())
    return e is not None and e.get("cbm_per_box", 0) > 0


def resolve_registered_code(code, goods_name, lookup):
    """WMS 견적코드 → TMS Product 등록 코드. 못 찾으면 원본 반환.

    1) 이미 등록됨 → 그대로
    2) 동일명 alias → 등록 코드
    3) 사이즈 변형군 → 굿즈명 사이즈 파싱 → SKU (없으면 __default__)
    4) 미해소 → 원본 (S5가 미산출 보고)
    """
    if not code:
        return code
    cu = str(code).upper()
    if _registered(cu, lookup):
        return cu
    if cu in ALIAS and _registered(ALIAS[cu], lookup):
        return ALIAS[cu]
    if cu in SIZE_FAMILY:
        fam = SIZE_FAMILY[cu]
        size = parse_size(goods_name)
        cand = fam.get(size) if size else None
        if cand and _registered(cand, lookup):
            return cand
        dflt = fam.get("__default__")
        if dflt and _registered(dflt, lookup):
            return dflt
    return cu


def inject_synthetic(lookup):
    """SYNTHETIC 신규 SKU를 product_lookup에 주입(code·name 키). 박스 CBM은 표준 박스타입에서 해소.

    이미 동일 code가 등록돼 있으면(향후 ⑤ WMS↔Product 소스정합 시) 스킵 — Product 우선.
    load_product_lookup 직후 build_context에서 1회 호출 (Product/WMS 운영 데이터 쓰기 0).
    """
    from harness.settlement.cbm_calc import BOX_TYPE_TO_CBM_M3
    for code, spec in SYNTHETIC.items():
        ck = code.lower()
        if ck in lookup:
            continue
        entry = {
            "rec_id": f"synthetic:{code}", "name": spec["name"], "code": code,
            "box_type": spec["box_type"], "qty_per_box": spec["qty_per_box"],
            "cbm_per_box": BOX_TYPE_TO_CBM_M3.get(spec["box_type"], 0.0),
        }
        lookup[ck] = entry
        if spec["name"]:
            lookup.setdefault(spec["name"].lower(), entry)
    return lookup


def remap_lines(lines, goods_name, lookup):
    """[(code, qty)] → 등록코드로 재매핑·합산 후 정렬.

    동일 등록코드로 모이면 수량 합산 (예: 사이즈군 default 수렴).
    """
    agg: dict[str, float] = {}
    for code, qty in lines:
        rc = resolve_registered_code(code, goods_name, lookup)
        agg[rc] = agg.get(rc, 0.0) + qty
    return sorted(agg.items())


def resolve_product_entry(name, code, name2code, lookup):
    """이름·코드 → 등록 Product entry(dict) + 해소코드 + 방법. 캐스케이드·정산 공유 리졸버.

    우선순위:
      1) 코드 직접 (+alias)               — 캐스케이드 경로 (code 보유 시)
      2) 이름 → sync_item 코드 (+alias)   — 정산 경로 (Shipment에 코드 없음 → 이름으로 코드 복원)
      3) 이름 Jaccard 폴백                — sync_item 미등록 이름 (현행 정산 동작 보존)
      4) 정규화 재시도                    — 변형 접미('(단품)'·'[2]'·'_재제작') 제거 후 3단 반복

    Returns (entry|None, resolved_code|None, method).
      method: 'code' | 'name2code' | 'jaccard' | 'jaccard_norm' | 'unmatched'.
    name2code: {normalize_goods(굿즈명): 굿즈코드(upper)} (None/{}이면 2단 스킵 → 현행 Jaccard만).
    하위호환: name2code 미전달 + code 미전달 시 (3)만 실행 → 기존 match_product 동작과 동일.
    """
    from harness.backbone.keys import normalize_goods
    from harness.settlement.cbm_calc import match_product

    # 1) 코드 직접 (+alias). cbm_per_box==0(data_gap)이면 의도적으로 통과시켜 이름 폴백으로 —
    #    기존 Jaccard-only 동작 보존(미입력 박스코드를 0으로 묵살하지 않음). audit data_gap이 별도 감시.
    if code:
        rc = resolve_registered_code(code, name, lookup)
        e = lookup.get(str(rc).lower())
        if e is not None and e.get("cbm_per_box", 0) > 0:
            return e, rc, "code"

    # 2) 이름 → sync_item 코드 (+alias)
    if name and name2code:
        c = name2code.get(normalize_goods(name))
        if c:
            rc = resolve_registered_code(c, name, lookup)
            e = lookup.get(str(rc).lower())
            if e is not None and e.get("cbm_per_box", 0) > 0:
                return e, rc, "name2code"

    # 3) 이름 Jaccard 폴백 (현행 정산 동작)
    if name:
        _k, e, _score = match_product(name, lookup)
        if e is not None:
            return e, (str(e.get("code") or "").upper() or None), "jaccard"

    # 4) 정규화 재시도 — '(단품)'·'[2]'·'_재제작' 등 변형 접미 제거 후 3단(Jaccard)만 반복.
    #    2단(name2code)은 이미 normalize_goods 키로 조회하므로 재시도 대상이 아니다.
    #    crosswalk.build_crosswalk(:17-19)이 쓰는 검증된 패턴과 동일.
    if name:
        nm = normalize_goods(name)
        if nm and nm != name:
            _k, e, _score = match_product(nm, lookup)
            if e is not None:
                return e, (str(e.get("code") or "").upper() or None), "jaccard_norm"

    return None, None, "unmatched"
