"""에이원센터 장기 미사용(휴면) 재고 검토.

Logic per user spec:
  1) material에서 에이원 자재 기준 추출 (좌표 또는 창고명으로 필터)
  2) order에서 출하예정일이 [2025-11-01, 2026-04-30] 범위인 행 추출
  3) material 중 출하예정 order가 없는 자재(휴면 후보) 식별
"""
from __future__ import annotations

import io
import re
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

MATERIAL_PATH = Path(r"C:\Users\yjisu\Desktop\material(parts-stock)-월말재고확인_에이원.xlsx")
ORDER_PATH = Path(r"C:\Users\yjisu\Desktop\order-실물재고 수량추적.xlsx")
OUT = Path(__file__).parent / "analyze_dormant_out.txt"
DORMANT_OUT = Path(__file__).parent / "dormant_candidates.csv"

WINDOW_START = pd.Timestamp("2025-11-01")
WINDOW_END = pd.Timestamp("2026-04-30")
AEONE_KEYWORDS = ["에이원지식산업센터", "에이원"]


def parse_date_kr(v):
    if pd.isna(v):
        return pd.NaT
    if isinstance(v, (pd.Timestamp, datetime)):
        return pd.Timestamp(v)
    s = str(v).strip()
    if not s:
        return pd.NaT
    m = re.match(r"^(\d{4})[.\-/](\d{1,2})[.\-/](\d{1,2})", s)
    if m:
        try:
            return pd.Timestamp(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return pd.NaT
    try:
        return pd.to_datetime(s, errors="coerce")
    except Exception:
        return pd.NaT


def is_aeone_location(coord) -> bool:
    if pd.isna(coord):
        return False
    s = str(coord)
    if any(k in s for k in AEONE_KEYWORDS):
        return True
    # 에이원 내부 BIN 패턴: A2/A1/A3... + 영문2 + 숫자  (예: A2AD3, A1AA2)
    if re.match(r"^A[1-9][A-Z]{2}\d", s):
        return True
    return False


def is_aeone_material(material_str) -> bool:
    if pd.isna(material_str):
        return False
    return any(k in str(material_str) for k in AEONE_KEYWORDS)


def main() -> None:
    buf = io.StringIO()
    pd.set_option("display.width", 200)
    pd.set_option("display.max_colwidth", 60)

    mat_sheet = pd.ExcelFile(MATERIAL_PATH).sheet_names[0]
    ord_sheet = pd.ExcelFile(ORDER_PATH).sheet_names[0]
    mat = pd.read_excel(MATERIAL_PATH, sheet_name=mat_sheet)
    odr = pd.read_excel(ORDER_PATH, sheet_name=ord_sheet)

    buf.write(f"[material] rows={len(mat)} cols={list(mat.columns)}\n")
    buf.write(f"[order]    rows={len(odr)} cols={list(odr.columns)}\n\n")

    # ---- material 분석 ----
    buf.write("===== Step 1. material 좌표 분포 (top20) =====\n")
    buf.write(mat["좌표"].value_counts(dropna=False).head(20).to_string())
    buf.write("\n\n")

    mat["is_aeone"] = mat["좌표"].apply(is_aeone_location)
    buf.write(f"[material] 에이원 자재 수 = {mat['is_aeone'].sum()} / {len(mat)}\n")
    non_aeone = mat.loc[~mat["is_aeone"], "좌표"].dropna().unique()
    buf.write(f"[material] 비-에이원으로 분류된 좌표 unique: {list(non_aeone)[:10]}\n\n")

    mat_aeone = mat[mat["is_aeone"]].copy()
    mat_aeone["order_date"] = mat_aeone["order"].apply(parse_date_kr)

    buf.write("===== Step 2. material[에이원] order(=출하예정일) 분포 =====\n")
    buf.write(f"  NaN(출하예정일 없음) = {mat_aeone['order_date'].isna().sum()}\n")
    in_win = mat_aeone["order_date"].between(WINDOW_START, WINDOW_END)
    buf.write(f"  in [2025-11-01, 2026-04-30] = {in_win.sum()}\n")
    out_win = mat_aeone["order_date"].notna() & ~in_win
    buf.write(f"  out of window               = {out_win.sum()}\n\n")

    # ---- order 분석 ----
    buf.write("===== Step 3. order 출하예정일 후보 컬럼 =====\n")
    # 출하예정일은 명시 컬럼이 없어 보임 → '최종 출고일' / '마지막재고선택 (조정일자 파악용)' 확인
    for col in ["최종 출고일", "마지막재고선택 (조정일자 파악용)"]:
        if col in odr.columns:
            ser = odr[col].apply(parse_date_kr)
            buf.write(f"  [{col}] non-null={ser.notna().sum()}, "
                      f"in window={ser.between(WINDOW_START, WINDOW_END).sum()}, "
                      f"min={ser.min()}, max={ser.max()}\n")

    # order에서 에이원 자재만 추출
    odr["is_aeone"] = odr["material"].apply(is_aeone_material)
    odr_aeone = odr[odr["is_aeone"]].copy()
    buf.write(f"\n[order] 에이원 material 행 수 = {len(odr_aeone)} / {len(odr)}\n")
    buf.write(f"[order] 발주단계 분포 (에이원만):\n")
    buf.write(odr_aeone["발주단계"].value_counts(dropna=False).head(20).to_string())
    buf.write("\n\n")

    # PT 코드 추출 함수
    def extract_pt(s):
        if pd.isna(s):
            return None
        m = re.match(r"(PT\d{4,5})", str(s))
        return m.group(1) if m else None

    odr_aeone["pt"] = odr_aeone["material"].apply(extract_pt)

    # 출하예정일 = '최종 출고일' 사용 (없으면 '마지막재고선택')
    odr_aeone["ship_date"] = odr_aeone["최종 출고일"].apply(parse_date_kr)
    odr_aeone["ship_in_window"] = odr_aeone["ship_date"].between(WINDOW_START, WINDOW_END)

    # 발주단계 중 아직 출고 안 된 active order도 고려
    # → 발주단계 NaN이 아니면 활성 오더로 가정
    odr_aeone["has_active_order"] = odr_aeone["발주단계"].notna()

    # 에이원 자재 중 활성 PT (윈도우 내 출고 OR 활성 발주단계)
    active_pt = set(odr_aeone[
        odr_aeone["ship_in_window"] | odr_aeone["has_active_order"]
    ]["pt"].dropna().unique())
    buf.write(f"[order] 에이원 활성 PT 코드 수 (윈도우 내 출고 + 발주단계 활성) = {len(active_pt)}\n\n")

    # ---- 휴면 후보 ----
    buf.write("===== Step 4. 휴면 재고 후보 (material 기준) =====\n")
    mat_aeone["pt"] = mat_aeone["파츠 코드 (from sync_parts)"]
    mat_aeone["has_active"] = mat_aeone["pt"].isin(active_pt)

    # 휴면 조건 1: material.order(출하예정일)이 NaN
    cond_no_date = mat_aeone["order_date"].isna()
    # 휴면 조건 2: order 파일에서도 활성 오더 없음
    cond_no_active = ~mat_aeone["has_active"]

    dormant_strict = mat_aeone[cond_no_date & cond_no_active].copy()
    dormant_loose = mat_aeone[cond_no_date].copy()

    buf.write(f"  엄격 휴면 (출하예정일 없음 AND order파일에 활성 오더 없음): {len(dormant_strict)}\n")
    buf.write(f"  느슨 휴면 (material.order 컬럼만 NaN):                     {len(dormant_loose)}\n\n")

    # 두 조건 차이
    diff = mat_aeone[cond_no_date & ~cond_no_active][
        ["sync_parts", "좌표", "실물재고수량", "전산재고수량", "order", "pt", "마지막 실재고 체크 완료 일시"]
    ]
    buf.write(f"  → material.order=NaN이지만 order파일엔 활성 오더 있는 자재: {len(diff)}\n")
    if len(diff) > 0:
        buf.write(diff.head(15).to_string())
        buf.write("\n\n")

    # 최종 휴면 리스트 (strict)
    final = dormant_strict[[
        "pt", "sync_parts", "좌표", "실물재고수량", "전산재고수량", "order",
        "마지막 실재고 체크 완료 일시", "자재_특이사항"
    ]].sort_values("실물재고수량", ascending=False)
    final.to_csv(DORMANT_OUT, index=False, encoding="utf-8-sig")
    buf.write(f"  CSV saved → {DORMANT_OUT.name} (rows={len(final)})\n\n")

    buf.write("===== 휴면 후보 Top 30 (재고수량 내림차순) =====\n")
    buf.write(final.head(30).to_string())
    buf.write("\n\n")

    # 통계
    buf.write("===== 휴면 후보 통계 =====\n")
    buf.write(f"  총 자재 종류: {len(final)}\n")
    buf.write(f"  총 실물재고 합계: {final['실물재고수량'].sum():,}\n")
    buf.write(f"  총 전산재고 합계: {final['전산재고수량'].sum():,}\n")
    diff_qty = (final["실물재고수량"] - final["전산재고수량"]).abs().sum()
    buf.write(f"  실물-전산 차이 절대합: {diff_qty:,}\n")
    mismatch = final[final["실물재고수량"] != final["전산재고수량"]]
    buf.write(f"  실물≠전산인 자재: {len(mismatch)}\n")

    OUT.write_text(buf.getvalue(), encoding="utf-8")
    print(f"WROTE {OUT}  /  {DORMANT_OUT}")


if __name__ == "__main__":
    main()
