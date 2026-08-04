"""Build the TMS Product create payload for V2 registration from the proposal.

REGISTER set = 9 inferable original codes + 4 new codes (user-approved 2026-06-16).
OFMP, UMUG, BSPK held (insufficient evidence → user input).

Minimal fields to light up cascade S5 (per build_context):
  견적코드 (join key) + 박스명칭 (→cbm_per_box>0 fallback) + 박스사이즈 (formula) +
  박스당 제품수 (qty/box) + Name (human readable).

Output: dry-run preview table (stdout) + payload JSON (data/v2_register_payload.json).
NO writes.
"""
import json
from pathlib import Path

FLD = {
    "name": "fldx01uKEnCd0J0nP",
    "code": "fldtpUf2UVooLcxwd",
    "box_type": "fldqGM1lw2TUpZdKW",
    "box_size": "fld1ECU2hhnEurOef",
    "qty_per_box": "fldENIdfxbVn8YnPI",
}

REGISTER = ["DRCG", "TWKF", "BMVS", "BCTW", "LOPU", "SLVB", "SZBT", "STTB",
            "VMCB", "WCCV", "DSKT", "CNPB", "RCPC"]
HOLD = ["OFMP", "UMUG", "BSPK"]

prop = json.loads(Path("data/v2_register_proposal.json").read_text(encoding="utf-8"))["proposals"]

records = []
print(f"{'코드':6s} {'굿즈명':22s} {'박스':5s} {'qty/box':>7s} {'근거':>5s} {'CBM검증':>7s}  비고")
print("-" * 92)
for code in REGISTER:
    p = prop[code]
    bt = p["inferred_box_type"]
    qpb = p["inferred_qty_per_box"]
    n = p["n_clean_box_evidence"]
    cm = p.get("cbm_match_median")
    votes = p.get("box_type_votes", {})
    note = ""
    if len(votes) > 1:
        note = f"박스혼재 {votes}"
    if max(p["qty_per_box_observations"]) / max(1, min(p["qty_per_box_observations"])) > 2.5:
        note += " 수량변동大"
    cmv = f"{cm}" if cm is not None else "—"
    print(f"{code:6s} {p['굿즈명']:22s} {bt:5s} {qpb:7d} {n:5d} {cmv:>7s}  {note}")
    records.append({"fields": {
        FLD["name"]: p["굿즈명"],
        FLD["code"]: code,
        FLD["box_type"]: bt,
        FLD["box_size"]: p["box_size_str"],
        FLD["qty_per_box"]: qpb,
    }})

print(f"\n등록 대상 {len(records)}건 / 보류 {len(HOLD)}건 ({', '.join(HOLD)} — 증거부족, 사용자입력)")
Path("data/v2_register_payload.json").write_text(
    json.dumps({"baseId": "app4x70a8mOrIKsMf", "tableId": "tblBNh6oGDlTKGrdQ",
                "records": records}, ensure_ascii=False, indent=2), encoding="utf-8")
print("[saved] data/v2_register_payload.json")
