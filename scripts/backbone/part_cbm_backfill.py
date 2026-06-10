"""P3' Task 2 — WMS_ItemMaster 파츠(PT) CBM_개당_m3 백필.

part_cbm tier 사다리(치수파싱 0.55 > QC버킷 0.40)로 blank CBM PT행을 산출해 PATCH.
- 소스: sync_parts.규격 → movement.제품규격(실제입하일 최신) 순. QC버킷은 분류
  소스 부재로 현재 dormant(배선만) — 미산출 사유로 리포트.
- 기존 CBM>0 행(굿즈 218·수기 실측) 불가침. 본 스크립트 태깅(출처=치수파싱/QC버킷)
  행만 재계산 대상 — 재실행 시 해소율 안정(INSERT 무관 집계, P2b lesson).
- dry-run 기본, --write 게이트(CP① 사용자 승인 + 출처 choice 신설 후).

Usage:
  python scripts/backbone/part_cbm_backfill.py            # dry-run 커버리지 리포트
  python scripts/backbone/part_cbm_backfill.py --write    # CBM_개당_m3 + 출처 PATCH
"""
import argparse
import os
import re
import sys
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from harness.backbone.part_cbm import (  # noqa: E402
    classify_qc_bucket,
    part_cbm_for_pt,
)
from utils.cbm_utils import (  # noqa: E402
    load_sync_parts_lookup,
    parse_inbound_item,
)

load_dotenv()
WP = os.environ["AIRTABLE_WMS_PAT"]
WMS = "appLui4ZR5HWcQRri"
ITEM = "tbl5ZGY373D5SCONV"   # WMS_ItemMaster (allowlist 내)
MOV = "tblwq7Kj5Y9nVjlOw"    # movement (read-only ⚡미러)

# movement 필드 ID (utils/cbm_utils.py와 동일)
F_MOV_ITEM = "fldwZKCYZ4IFOigRp"     # 이동물품
F_MOV_SPEC = "fldiYU7b6Ogf0zm2D"     # 제품 규격
F_MOV_ACT_DATE = "flduN8khmYwdn7uVD"  # 실제입하일

PT_KEY_RE = re.compile(r"^PT\d{3,6}$")
WRITE_TOL = 1e-6   # 기존값과 이 이내면 skip (idempotent 재실행)
BACKFILL_SOURCES = {"치수파싱", "QC버킷"}   # 본 스크립트 태깅 — 재계산 허용 범위


def fetch(base, tid, pat, fields, by_field_id=False):
    out, off = [], None
    while True:
        p = {"pageSize": 100, "fields[]": fields}
        if by_field_id:
            p["returnFieldsByFieldId"] = "true"
        if off:
            p["offset"] = off
        r = requests.get(
            f"https://api.airtable.com/v0/{base}/{tid}",
            headers={"Authorization": f"Bearer {pat}"}, params=p, timeout=60,
        )
        r.raise_for_status()
        d = r.json()
        out += d["records"]
        off = d.get("offset")
        if not off:
            break
    return out


def patch_batch(url, headers, batch):
    """10건 이하 batch PATCH. Returns (ok, err).

    typecast: 출처 singleSelect 신규 choice('치수파싱')는 Meta API field 업데이트가
    options 변경을 미지원하므로 typecast로 자동 생성 (CP① 승인 범위).
    """
    for attempt in range(3):
        try:
            r = requests.patch(url, headers=headers,
                               json={"records": batch, "typecast": True}, timeout=30)
            time.sleep(0.25)
            if r.ok:
                return len(batch), 0
            if r.status_code in (429, 500, 502, 503) and attempt < 2:
                time.sleep(30 * (attempt + 1))
                continue
            print(f"  PATCH 실패 {r.status_code}: {r.text[:200]}")
            return 0, len(batch)
        except requests.RequestException as exc:
            if attempt < 2:
                time.sleep(30 * (attempt + 1))
                continue
            print(f"  PATCH 예외: {exc}")
            return 0, len(batch)
    return 0, len(batch)


def build_mov_spec_by_pt():
    """movement → PT별 최신(실제입하일) 제품규격."""
    recs = fetch(WMS, MOV, WP, [F_MOV_ITEM, F_MOV_SPEC, F_MOV_ACT_DATE], by_field_id=True)
    latest: dict[str, tuple[str, str]] = {}   # pt -> (act_date, spec)
    for rec in recs:
        f = rec.get("fields", {})
        spec = str(f.get(F_MOV_SPEC) or "").strip()
        if not spec:
            continue
        pt = parse_inbound_item(f.get(F_MOV_ITEM))["parts_code"]
        if not PT_KEY_RE.match(pt):
            continue
        act = str(f.get(F_MOV_ACT_DATE) or "")
        if pt not in latest or act > latest[pt][0]:
            latest[pt] = (act, spec)
    return {pt: spec for pt, (_, spec) in latest.items()}, len(recs)


def main():
    ap = argparse.ArgumentParser(description="ItemMaster 파츠 CBM 백필")
    ap.add_argument("--write", action="store_true", help="CBM_개당_m3 + 출처 PATCH 실행")
    args = ap.parse_args()

    print("로딩: ItemMaster / sync_parts 규격 / movement 제품규격...")
    items = fetch(WMS, ITEM, WP, ["품목키", "CBM_개당_m3", "출처"])
    sp_lookup = load_sync_parts_lookup()
    mov_spec_by_pt, n_mov = build_mov_spec_by_pt()
    print(f"  ItemMaster {len(items)}행 / sync_parts 규격 {len(sp_lookup)}PT / "
          f"movement {n_mov}행→규격 {len(mov_spec_by_pt)}PT")

    # 스코프: PT행 AND (CBM blank OR 본 스크립트 태깅) — 재실행 시 집계 안정
    pt_rows = [r for r in items if PT_KEY_RE.match(str(r["fields"].get("품목키", "")))]
    scope = [r for r in pt_rows
             if (r["fields"].get("CBM_개당_m3") or 0) <= 0
             or r["fields"].get("출처") in BACKFILL_SOURCES]
    untouchable = len(pt_rows) - len(scope)

    stats = {"치수파싱_sp": 0, "치수파싱_mov": 0, "QC버킷": 0, "미산출_규격없음": 0, "미산출_파싱실패": 0}
    bucket_dist = {"소": 0, "중": 0, "대": 0}
    to_write, reject_samples = [], []

    for r in scope:
        pt = r["fields"]["품목키"]
        # sp 단독 → 실패 시 mov 포함 재시도 (소스 분리 집계)
        cbm, conf, tier = part_cbm_for_pt(pt, {}, sp_lookup)
        src = "sp"
        if tier == "미산출":
            cbm, conf, tier = part_cbm_for_pt(pt, {}, sp_lookup, mov_spec_by_pt)
            src = "mov"
        if tier == "치수파싱":
            stats[f"치수파싱_{src}"] += 1
            bucket_dist[classify_qc_bucket(cbm)] += 1
            cur = r["fields"].get("CBM_개당_m3") or 0
            if abs(cur - cbm) > WRITE_TOL:
                to_write.append({"id": r["id"],
                                 "fields": {"CBM_개당_m3": cbm, "출처": "치수파싱"}})
        elif tier == "QC버킷":
            stats["QC버킷"] += 1
        else:
            has_spec = bool((sp_lookup.get(pt) or "").strip()) or pt in mov_spec_by_pt
            if has_spec:
                stats["미산출_파싱실패"] += 1
                if len(reject_samples) < 10:
                    reject_samples.append((pt, (sp_lookup.get(pt) or mov_spec_by_pt.get(pt, ""))[:40]))
            else:
                stats["미산출_규격없음"] += 1

    resolved = stats["치수파싱_sp"] + stats["치수파싱_mov"] + stats["QC버킷"]
    n_pt = len(pt_rows)
    print("\n=== ItemMaster 파츠 CBM 백필 (PT행 기준) ===")
    print(f"PT행 {n_pt} | 스코프 {len(scope)} (기존 실측 불가침 {untouchable})")
    print(f"해소: {resolved}/{len(scope)} ({resolved / len(scope) * 100:.1f}%)"
          f" — 치수파싱 sp {stats['치수파싱_sp']} + mov {stats['치수파싱_mov']}"
          f" / QC버킷 {stats['QC버킷']} (분류 소스 부재 — dormant)")
    print(f"미산출: 규격없음 {stats['미산출_규격없음']} / 파싱실패 {stats['미산출_파싱실패']}")
    print(f"PT CBM 커버리지: {n_pt - len(scope) + resolved}/{n_pt}"
          f" ({(n_pt - len(scope) + resolved) / n_pt * 100:.1f}%)")
    print(f"해소분 QC버킷 분포(참고): 소 {bucket_dist['소']} / 중 {bucket_dist['중']} / 대 {bucket_dist['대']}")
    if reject_samples:
        print("파싱실패 샘플:", "; ".join(f"{p}:'{s}'" for p, s in reject_samples))

    if not args.write:
        print(f"\n[DRY-RUN] PATCH 예정 {len(to_write)}행 — 반영하려면 --write "
              f"(선행: ItemMaster 출처 choice '치수파싱'·'QC버킷' 신설, CP① 승인)")
        return

    ok = err = 0
    url = f"https://api.airtable.com/v0/{WMS}/{ITEM}"
    headers = {"Authorization": f"Bearer {WP}", "Content-Type": "application/json"}
    for i in range(0, len(to_write), 10):
        o, e = patch_batch(url, headers, to_write[i:i + 10])
        ok += o
        err += e
    print(f"\n[WRITE] ItemMaster patched={ok} err={err} (출처='치수파싱')")


if __name__ == "__main__":
    main()
