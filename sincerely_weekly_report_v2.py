# Sincerely SCM 주간 출하 리포트 v3
# ---------------------------------------------
# 매주 월요일 09:00~09:30 KST 슬랙 DM 자동 발송
#
# CBM 산출 우선순위 (v3 변경):
#   1순위: Total_CBM 필드 (수동 입력)
#   2순위: 외박스 수량 문자열 파싱 (극소N, 중대N 패턴)
#   3순위: Product 테이블 CBM 실시간 매칭 (공백 정규화 후 부분일치)
#   * 매칭 안 되는 건은 CBM 산출에서 제외 (0 추정 없음)
#
# 포함 지표:
#   [CBM]    총 CBM / 일별 CBM / 박스 타입별 구성비
#   [물동량]  건수 / CBM 산출 건수 / 매칭 제외 건수
#   [품질]   당일 등록 비율 / 리드타임
#   [손익]   물류매출 / 운송비용 / CBM당 물류비 / 주간 트렌드
#
# 환경변수:
#   AIRTABLE_API_KEY      Airtable PAT
#   AIRTABLE_BASE_ID      TMS base (app4x70a8mOrIKsMf)
#   SLACK_BOT_TOKEN       Bot Token (xoxb-...)
#   SLACK_DM_USER_ID      수신자 Slack User ID (U로 시작)

import os
import json
import math
import re
import time
import random
from datetime import datetime, timedelta, date
from collections import defaultdict

import pyairtable
import requests

# -- 환경변수 ------------------------------------------
API_KEY       = os.environ["AIRTABLE_API_KEY"]
BASE_ID       = os.environ.get("AIRTABLE_BASE_ID", "app4x70a8mOrIKsMf")
SLACK_TOKEN   = os.environ["SLACK_BOT_TOKEN"]
DM_USER_ID    = os.environ["SLACK_DM_USER_ID"]   # 예: U0XXXXXXX

# -- Table ID ------------------------------------------
TABLE_SHIPMENT = "tbllg1JoHclGYer7m"
TABLE_BOX      = "tbltwH7bHk41rTzhM"
TABLE_PRODUCT  = "tblBNh6oGDlTKGrdQ"   # Product 테이블 (CBM 기준값)

# -- Field ID 상수 -------------------------------------
F_DATE        = "fldQvmEwwzvQW95h9"   # 출하확정일
F_ITEM        = "fldgSupj5XLjJXYQo"   # 최종 출하 품목
F_BOX_PARSED  = "fldTjLDmw5sNGszeD"   # 최종 외박스 수량 값 (formula)
F_BOX_MANUAL  = "fldRjMaXa5TdSsGDL"   # 외박스 수량 직접입력
F_TOTAL_CBM   = "fldJ9DHjwoRyeUEqE"   # Total_CBM (수동)
F_STATUS      = "fldOhibgxg6LIpRTi"   # 발송상태_TMS
F_ITEM_DETAIL = "fldXXnGOXkm90snKn"   # 최종 출고 품목 및 수량
F_REVENUE     = "fldOFuvqBT0iXItcT"   # 물류매출
F_COST        = "fldRT95SC88KSBATT"   # 운송비용
F_CREATED     = "fldeJIfwz6QDZFYm8"   # created_time (배송요청 테이블 기준)

# Box 테이블
F_BOX_CODE = "fldELrd8bBVjQCHnp"
F_BOX_NAME = "fldgvlGjLb4FTlQ0v"
F_BOX_CBM  = "fldjFaXiYzeJ2Zt7M"

# -- 박스 CBM fallback 사전 -----------------------------
BOX_CBM = {
    "극소": 0.0098, "S280": 0.0098,
    "소":   0.0117, "S360": 0.0117,
    "중":   0.0201, "M350": 0.0201,
    "중대": 0.0492, "M480": 0.0492,
    "대":   0.1066, "L510": 0.1066,
    "특대": 0.1663, "L560": 0.1663,
}

BOX_SIZE_ORDER = ["극소", "소", "중", "중대", "대", "특대"]

# -- 품목 -> CBM 매핑은 Product 테이블에서 실시간 조회 (fetch_product_cbm 참조)
# v3: 하드코딩 PRODUCT_CBM 제거 -> Airtable Product 테이블 사용

_BOX_RE = re.compile(
    r"(극소|소|중대|중|대|특대|S280|S360|M350|M480|L510|L560)\s*(\d+)"
)
WD_KR = ["월", "화", "수", "목", "금", "토", "일"]


# =======================================================
# 1. 날짜 유틸
# =======================================================
def week_range(offset: int = 0):
    today = date.today()
    mon = today - timedelta(days=today.weekday()) + timedelta(weeks=offset)
    fri = mon + timedelta(days=4)
    return mon, fri


# =======================================================
# 2. Airtable 조회
# =======================================================
def fetch_shipments(start: date, end: date) -> list[dict]:
    api   = pyairtable.Api(API_KEY)
    table = api.table(BASE_ID, TABLE_SHIPMENT)
    formula = (
        f"AND("
        f"IS_AFTER({{출하확정일}}, DATEADD('{start.isoformat()}', -1, 'days')), "
        f"IS_BEFORE({{출하확정일}}, DATEADD('{end.isoformat()}',  1, 'days'))"
        f")"
    )
    return table.all(formula=formula)


def fetch_prev_weeks(n: int = 4) -> list[dict]:
    """손익 트렌드용: 최근 n주 데이터"""
    mon, _ = week_range(-n)
    _, fri = week_range(-1)
    return fetch_shipments(mon, fri)


def fetch_box_cbm_live() -> dict:
    api   = pyairtable.Api(API_KEY)
    table = api.table(BASE_ID, TABLE_BOX)
    live  = {}
    for rec in table.all():
        f = rec["fields"]
        for key in (f.get("Box Code"), f.get("박스")):
            if key:
                live[key] = f.get("cbm", 0)
    return live


def fetch_product_cbm():
    # Product 테이블 전체 조회 후 field ID로 직접 접근
    # fldx01uKEnCd0J0nP = 품목명, fldN1JrkxIr5m6pXz = CBM/박스(단품), fld6W5ImO7UeBVMPI = CBM/박스(키트)
    api   = pyairtable.Api(API_KEY)
    table = api.table(BASE_ID, TABLE_PRODUCT)
    result = []
    for rec in table.all():
        f = rec["fields"]
        # field ID 또는 field 이름 둘 다 시도
        name = (
            f.get("fldx01uKEnCd0J0nP") or
            f.get("Name") or
            f.get("품목명") or
            ""
        ).strip()
        cbm = (
            f.get("fldN1JrkxIr5m6pXz") or
            f.get("fld6W5ImO7UeBVMPI") or
            f.get("박스당 CBM") or
            None
        )
        if name and cbm:
            try:
                norm = re.sub(r"\s+", "", name)
                result.append((norm, float(cbm)))
            except (ValueError, TypeError):
                pass
    result.sort(key=lambda x: -len(x[0]))
    print(f"  Product CBM 조회 완료: {len(result)}개 품목")
    return result


# =======================================================
# 3. CBM 파싱
# =======================================================
def parse_box_cbm(box_str: str, live: dict) -> tuple[float, dict]:
    """(total_cbm, {box_type: count}) 반환"""
    ref   = {**BOX_CBM, **live}
    total = 0.0
    by_type: dict[str, int] = {}
    for m in _BOX_RE.finditer(box_str):
        btype, cnt = m.group(1), int(m.group(2))
        total += ref.get(btype, 0) * cnt
        # 코드 -> 규격명 정규화
        norm = next((k for k in BOX_CBM if k == btype), btype)
        by_type[norm] = by_type.get(norm, 0) + cnt
    return round(total, 4), by_type


def match_cbm_from_product(item_str: str, product_cbm: list[tuple[str, float]]) -> float:
    """
    Product 테이블 CBM 데이터로 품목 CBM 산출.
    - 공백 제거 후 부분 일치 (greedy: 긴 이름 우선)
    - 매칭 안 되면 0.0 반환 -> 호출부에서 제외 처리
    """
    norm_item = re.sub(r"\s+", "", item_str)
    total = 0.0
    matched_any = False

    for line in item_str.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        norm_line = re.sub(r"\s+", "", line)
        # 수량 파싱: 품목명 끝에 붙은 숫자
        nums = re.findall(r"\d+", norm_line)

        for prod_norm, cbm_per_box in product_cbm:
            if prod_norm in norm_line:
                # 수량을 찾아 박스 수 환산 - 박스당수량 정보가 없으므로
                # cbm_per_box가 이미 (1개당 CBM) 기준이라면 곱하기 수량
                # Product 테이블의 fldN1JrkxIr5m6pXz = CBM/박스 (박스당수량으로 나눈 값)
                # -> 수량을 곱하면 총 CBM 근사
                if nums:
                    qty = int(nums[-1])
                    total += cbm_per_box * qty
                else:
                    total += cbm_per_box
                matched_any = True
                break

    return round(total, 4) if matched_any else 0.0


# =======================================================
# 4. 핵심 분석 함수
# =======================================================
def analyze(records: list[dict], live_cbm: dict, week_start: date,
            product_cbm: list[tuple[str, float]] | None = None) -> dict:
    """
    반환 구조:
      summary / by_date / box_type_dist / quality / leadtime
      item_top / profit / cbm_per_cbm_cost / cbm_sources
    """
    by_date: dict   = defaultdict(lambda: {
        "cbm": 0.0, "count": 0, "boxes": 0,
        "completed": 0, "pending": 0,
        "revenue": 0.0, "cost": 0.0,
    })
    box_type_all: dict[str, int] = defaultdict(int)
    item_agg:     dict = defaultdict(lambda: {"qty": 0, "cbm": 0.0})
    cbm_sources = {"manual": 0, "box_parse": 0, "product_match": 0, "unmatched": 0}

    # -- 품질 지표용 ----------------------------------
    missing_box_qty = 0          # 외박스수량 미기재
    same_day_create = 0          # 출하 당일 등록
    leadtimes: list[float] = []  # 대기->완료 리드타임(시간)

    total = len(records)

    for rec in records:
        f   = rec["fields"]
        d_s = f.get("출하확정일", "")
        if not d_s:
            continue
        ship_date = date.fromisoformat(d_s)
        bkt = by_date[ship_date]
        bkt["count"] += 1

        # 상태
        status_obj = f.get("발송상태_TMS")
        status = (status_obj["name"] if isinstance(status_obj, dict)
                  else (status_obj or ""))
        if "완료" in status:
            bkt["completed"] += 1
        else:
            bkt["pending"] += 1

        # 매출/비용
        bkt["revenue"] += f.get("물류매출") or 0
        bkt["cost"]    += f.get("운송비용") or 0

        # -- CBM --------------------------------------
        total_cbm_field = f.get("Total_CBM")
        box_qty = f.get("최종 외박스 수량 값") or f.get("외박스 수량 (직접입력)") or ""
        if isinstance(box_qty, list):
            box_qty = ", ".join(str(x) for x in box_qty)
        box_qty = box_qty.strip()

        cbm_val = 0.0
        btype_counts: dict = {}

        if total_cbm_field and total_cbm_field > 0:
            # 1순위: Total_CBM 수동 입력
            cbm_val = total_cbm_field
            cbm_sources["manual"] += 1
        else:
            item_str = f.get("최종 출하 품목") or f.get("최종 출고 품목 및 수량") or ""
            # 2순위: Product 테이블 CBM 매칭
            if item_str.strip() and product_cbm:
                cbm_val = match_cbm_from_product(item_str, product_cbm)
            else:
                cbm_val = 0.0

            if cbm_val > 0:
                cbm_sources["product_match"] += 1
            elif box_qty and _BOX_RE.search(box_qty):
                # 3순위: 외박스 수량 문자열 파싱 (Product 매칭 실패 시 기존 방식)
                cbm_val, btype_counts = parse_box_cbm(box_qty, live_cbm)
                for bt, cnt in btype_counts.items():
                    box_type_all[bt] += cnt
                    bkt["boxes"] += cnt
                cbm_sources["box_parse"] += 1
            else:
                # 4순위: 둘 다 없음 -> CBM 0 (집계 제외)
                cbm_sources["unmatched"] += 1

        bkt["cbm"] = round(bkt["cbm"] + cbm_val, 4)

        # -- 품질: 외박스 미기재 -----------------------
        if not box_qty or not _BOX_RE.search(box_qty):
            missing_box_qty += 1

        # -- 품질: 당일 등록 --------------------------
        created_s = rec.get("createdTime", "")
        if created_s:
            created_d = datetime.fromisoformat(
                created_s.replace("Z", "+00:00")
            ).date()
            if created_d == ship_date:
                same_day_create += 1

        # -- 리드타임 추정 (created -> 완료 기준) -------
        # 실제 상태변경 시각 필드가 없으므로 created vs ship_date 차이로 추정
        if "완료" in status and created_s:
            created_d = datetime.fromisoformat(
                created_s.replace("Z", "+00:00")
            ).date()
            delta_days = (ship_date - created_d).days
            if 0 <= delta_days <= 30:
                leadtimes.append(float(delta_days))

        # -- 품목 집계 ---------------------------------
        item_str = f.get("최종 출하 품목") or ""
        for line in item_str.strip().splitlines():
            line = line.strip()
            if not line:
                continue
            nums  = re.findall(r"\d+", line)
            iname = re.sub(r"\s*\d+\s*$", "", line).strip()
            if iname and nums:
                qty = int(nums[-1])
                item_agg[iname]["qty"] += qty
                # Product 테이블 매칭으로 CBM 추가
                if product_cbm:
                    norm_line = re.sub(r"\s+", "", iname)
                    for prod_norm, cbm_val_p in product_cbm:
                        if prod_norm in norm_line:
                            item_agg[iname]["cbm"] += round(cbm_val_p * qty, 4)
                            break

    # -- 집계 -----------------------------------------
    total_cbm  = round(sum(v["cbm"] for v in by_date.values()), 3)
    total_cnt  = sum(v["count"]     for v in by_date.values())
    total_done = sum(v["completed"] for v in by_date.values())
    total_pend = sum(v["pending"]   for v in by_date.values())
    total_rev  = sum(v["revenue"]   for v in by_date.values())
    total_cost = sum(v["cost"]      for v in by_date.values())

    # 건당 평균 CBM
    cbm_per_shipment = round(total_cbm / total_cnt, 3) if total_cnt else 0

    # 박스 타입별 비중
    total_boxes = sum(box_type_all.values())
    box_pct = {
        k: round(v / total_boxes * 100, 1)
        for k, v in box_type_all.items()
    } if total_boxes else {}

    # 요일별 집중도 (이번 주 기준)
    wd_cbm: dict[int, float] = defaultdict(float)
    for d, v in by_date.items():
        wd_cbm[d.weekday()] += v["cbm"]
    cbm_vals = list(wd_cbm.values())
    avg_wd   = sum(cbm_vals) / len(cbm_vals) if cbm_vals else 0
    variance = round(
        sum((x - avg_wd) ** 2 for x in cbm_vals) / len(cbm_vals), 2
    ) if cbm_vals else 0
    max_wd   = max(wd_cbm, key=wd_cbm.get) if wd_cbm else None

    # CBM당 물류비
    cbm_unit_cost = round(total_cost / total_cbm, 0) if total_cbm > 0 else 0

    # 리드타임
    avg_lead = round(sum(leadtimes) / len(leadtimes), 1) if leadtimes else None

    # 신뢰도
    confidence = round(
        (cbm_sources["manual"] + cbm_sources["box_parse"]) / total * 100, 1
    ) if total else 0

    top_items = sorted(
        [(k, v["qty"], round(v["cbm"], 3)) for k, v in item_agg.items()],
        key=lambda x: -x[2],
    )[:8]

    return {
        "by_date": dict(by_date),
        "summary": {
            "total_cbm":         total_cbm,
            "total_count":       total_cnt,
            "completed":         total_done,
            "pending":           total_pend,
            "revenue":           total_rev,
            "cost":              total_cost,
            "profit":            round(total_rev - total_cost, 0),
            "cbm_per_shipment":  cbm_per_shipment,
            "cbm_unit_cost":     cbm_unit_cost,
        },
        "box_type": {
            "counts": dict(box_type_all),
            "pct":    box_pct,
            "total":  total_boxes,
        },
        "weekday_dist": {
            "by_wd":   dict(wd_cbm),
            "variance": variance,
            "max_wd":  max_wd,
        },
        "quality": {
            "total_records":       total,
            "missing_box_qty":     missing_box_qty,
            "missing_rate":        round(missing_box_qty / total * 100, 1) if total else 0,
            "same_day_create":     same_day_create,
            "same_day_rate":       round(same_day_create / total * 100, 1) if total else 0,
            "avg_leadtime_days":   avg_lead,
        },
        "confidence":  confidence,
        "cbm_sources": cbm_sources,
        "top_items":   top_items,
    }


def build_trend(prev_records: list[dict], live_cbm: dict,
                product_cbm: list[tuple[str, float]] | None = None) -> list[dict]:
    """최근 4주 주간 손익 트렌드"""
    weekly: dict[date, dict] = defaultdict(lambda: {
        "cbm": 0.0, "revenue": 0.0, "cost": 0.0, "count": 0
    })
    for rec in prev_records:
        f   = rec["fields"]
        d_s = f.get("출하확정일")
        if not d_s:
            continue
        d = date.fromisoformat(d_s)
        mon = d - timedelta(days=d.weekday())
        w   = weekly[mon]
        w["count"] += 1
        w["revenue"] += f.get("물류매출") or 0
        w["cost"]    += f.get("운송비용") or 0

        # CBM (우선순위 동일하게 적용)
        box_qty = f.get("최종 외박스 수량 값") or ""
        if isinstance(box_qty, list):
            box_qty = ", ".join(str(x) for x in box_qty)
        total_cbm_f = f.get("Total_CBM")

        if total_cbm_f and total_cbm_f > 0:
            # 1순위: 수동 입력
            w["cbm"] += total_cbm_f
        else:
            item_str = f.get("최종 출하 품목") or ""
            # 2순위: Product 테이블 매칭
            cv = 0.0
            if item_str.strip() and product_cbm:
                cv = match_cbm_from_product(item_str, product_cbm)
            if cv > 0:
                w["cbm"] += cv
            elif box_qty and _BOX_RE.search(box_qty):
                # 3순위: 외박스 수량 파싱
                cv, _ = parse_box_cbm(box_qty, live_cbm)
                w["cbm"] += cv
            # 4순위: 둘 다 없으면 0 (제외)

    result = []
    for mon in sorted(weekly.keys())[-4:]:
        w   = weekly[mon]
        wn  = f"{mon.month}/{mon.day}주"
        cbm = round(w["cbm"], 2)
        rev = round(w["revenue"])
        cst = round(w["cost"])
        result.append({
            "week":    wn,
            "cbm":     cbm,
            "revenue": rev,
            "cost":    cst,
            "profit":  rev - cst,
            "count":   w["count"],
        })
    return result


# =======================================================
# 5. 슬랙 메시지 빌더
# =======================================================
def _bar(val: float, max_val: float, width: int = 12) -> str:
    filled = round(val / max_val * width) if max_val else 0
    return "#" * filled + "." * (width - filled)


def _pct_bar(pct: float, width: int = 10) -> str:
    filled = round(pct / 100 * width)
    return "#" * filled + "." * (width - filled)


def build_slack_blocks(
    this: dict, next_: dict,
    trend: list[dict],
    week_mon: date,
) -> list[dict]:
    s    = this["summary"]
    q    = this["quality"]
    bt   = this["box_type"]
    wd   = this["weekday_dist"]
    next_s = next_["summary"]

    wk_no   = (week_mon.day - 1) // 7 + 1
    wk_label = f"{week_mon.month}월 {wk_no}주차"
    fri = week_mon + timedelta(4)

    # -- 상태 이모지 ------------------------------------
    cbm_emoji = "" if s["total_cbm"] > 30 else ("" if s["total_cbm"] > 15 else "")
    q_emoji   = "" if q["missing_rate"] > 50 else ("" if q["missing_rate"] > 25 else "")

    # -- 박스 구성비 텍스트 -----------------------------
    box_lines = ""
    for btype in BOX_SIZE_ORDER:
        pct = bt["pct"].get(btype, 0)
        cnt = bt["counts"].get(btype, 0)
        if cnt > 0:
            box_lines += f"  `{btype:3}` {_pct_bar(pct, 8)}  {pct:4.1f}%  ({cnt}박스)\n"

    # -- 요일별 CBM -------------------------------------
    max_wd_cbm = max(wd["by_wd"].values(), default=1)
    wd_lines   = ""
    for d in sorted(this["by_date"].keys()):
        v   = this["by_date"][d]
        bar = _bar(v["cbm"], max_wd_cbm, 10)
        chk = " [OK]" if v["completed"] > 0 and v["pending"] == 0 else (
              " [...]" if v["pending"] > 0 else "")
        wd_lines += (
            f"  `{d.strftime('%m/%d')}({WD_KR[d.weekday()]})`  "
            f"{bar}  *{v['cbm']:.2f}m3*  {v['count']}건{chk}\n"
        )
    if wd["variance"] > 0:
        conc = "집중" if wd["variance"] > 10 else "분산"
        wd_lines += f"  _분산도 {wd['variance']:.1f} - 요일별 물동량 {conc} 패턴_\n"

    # -- Top 품목 ---------------------------------------
    item_lines = ""
    for i, (name, qty, cbm) in enumerate(this["top_items"][:6], 1):
        item_lines += f"  {i}. {name}  `{qty:,}개`  ->  *{cbm:.3f}m3*\n"

    # -- 손익 트렌드 ------------------------------------
    trend_lines = ""
    if trend:
        max_cbm_t = max(t["cbm"] for t in trend) or 1
        for t in trend:
            bar    = _bar(t["cbm"], max_cbm_t, 8)
            profit = t["profit"]
            sign   = "+" if profit >= 0 else ""
            trend_lines += (
                f"  `{t['week']}`  {bar}  {t['cbm']:.1f}m3  "
                f"손익 {sign}{profit:,.0f}원\n"
            )

    # -- 알림 ------------------------------------------
    alerts = []
    if s["pending"] > 0:
        alerts.append(f"[!]  미완료 출하 {s['pending']}건 - 진행 확인 필요")
    if q["missing_rate"] > 30:
        alerts.append(
            f"[!]  외박스 수량 미기재율 {q['missing_rate']:.0f}% "
            f"({q['missing_box_qty']}건) - CBM 신뢰도 저하"
        )
    if q["same_day_rate"] > 40:
        alerts.append(
            f"  당일 신규 등록 {q['same_day_rate']:.0f}% "
            f"- 사전 입력 프로세스 점검 권장"
        )
    if s["total_cbm"] > 25:
        alerts.append("  주간 CBM 25m3 초과 - 차량 용량 사전 조율 권장")
    if not alerts:
        alerts.append("[OK]  특이 사항 없음")

    alert_text = "\n".join(alerts)

    # -- 차량 추천 --------------------------------------
    truck_lines = ""
    if bt["pct"].get("특대", 0) > 20:
        truck_lines = "  -> 특대 박스 비중 높음 - 5톤 이상 차량 권장"
    elif bt["pct"].get("대", 0) + bt["pct"].get("특대", 0) > 40:
        truck_lines = "  -> 대형 박스 비중 높음 - 2.5t~5t 검토"
    else:
        truck_lines = "  -> 중소형 박스 위주 - 1t 다수 배차 또는 용달 적합"

    blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f" SCM 주간 출하 리포트 - {wk_label}",
            },
        },
        {
            "type": "context",
            "elements": [{
                "type": "mrkdwn",
                "text": (
                    f"{week_mon.strftime('%Y-%m-%d')}(월) ~ "
                    f"{fri.strftime('%m-%d')}(금)  |  "
                    f"생성: {datetime.now().strftime('%m/%d %H:%M')}  |  "
                    f"CBM 신뢰도 {this['confidence']}%"
                ),
            }],
        },
        {"type": "divider"},
        # (1) 핵심 요약
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"* 이번주 핵심 요약*\n"
                    f"{cbm_emoji}  총 CBM  *{s['total_cbm']:.2f} m3*\n"
                    f"  총 출하  {s['total_count']}건  "
                    f"(완료 {s['completed']} / 대기 {s['pending']})\n"
                    f"  건당 평균 CBM  {s['cbm_per_shipment']:.3f} m3\n"
                    f"  물류매출  W{s['revenue']:,.0f}  |  "
                    f"비용  W{s['cost']:,.0f}  |  "
                    f"손익  W{s['profit']:+,.0f}\n"
                    f"  CBM당 물류비  W{s['cbm_unit_cost']:,.0f} / m3"
                ),
            },
        },
        {"type": "divider"},
        # (2) 일별 CBM
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"* 일별 CBM 현황*\n{wd_lines}",
            },
        },
        {"type": "divider"},
        # (3) 박스 구성비
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"* 박스 타입 구성비* (총 {bt['total']}박스)\n"
                    f"{box_lines}"
                    f"{truck_lines}"
                ),
            },
        },
        {"type": "divider"},
        # (4) 출하 품목 Top
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"* 출하 품목 Top (CBM 기준)*\n{item_lines}",
            },
        },
        {"type": "divider"},
        # (5) 운영 품질 KPI
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"*{q_emoji} 운영 품질 KPI*\n"
                    f"  외박스 수량 미기재율  "
                    f"*{q['missing_rate']:.1f}%*  "
                    f"({q['missing_box_qty']}/{q['total_records']}건)\n"
                    f"  당일 신규 등록 비율  "
                    f"*{q['same_day_rate']:.1f}%*  "
                    f"({q['same_day_create']}건) - 예측성 지표\n"
                    + (
                        f"  평균 리드타임  "
                        f"*{q['avg_leadtime_days']:.1f}일*  (등록->출하 완료)\n"
                        if q["avg_leadtime_days"] is not None else ""
                    )
                    + f"  CBM 산출 근거  "
                    f"수동 {this['cbm_sources']['manual']} / "
                    f"박스파싱 {this['cbm_sources']['box_parse']} / "
                    f"품목매칭 {this['cbm_sources']['product_match']} / "
                    f"미산출 {this['cbm_sources']['unmatched']}"
                ),
            },
        },
        {"type": "divider"},
        # (6) 손익 트렌드
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"* 최근 4주 물동량 . 손익 트렌드*\n{trend_lines}",
            },
        },
        {"type": "divider"},
        # (7) 다음주 예고
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"* 다음주 예고 "
                    f"({(week_mon+timedelta(7)).strftime('%m/%d')}~)*\n"
                    f"  예정 건수  {next_s['total_count']}건  |  "
                    f"예상 CBM  {next_s['total_cbm']:.2f} m3"
                ),
            },
        },
        {"type": "divider"},
        # (8) 알림
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"* 주요 알림*\n{alert_text}"},
        },
    ]

    return blocks


# =======================================================
# 6. Slack DM 전송
# =======================================================
def _slack_api(endpoint: str, payload: dict) -> dict:
    resp = requests.post(
        f"https://slack.com/api/{endpoint}",
        headers={
            "Authorization": f"Bearer {SLACK_TOKEN}",
            "Content-Type": "application/json; charset=utf-8",
        },
        json=payload,
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()
    if not data.get("ok"):
        raise RuntimeError(f"Slack API error [{endpoint}]: {data.get('error')}")
    return data


def send_dm(blocks: list[dict], fallback_text: str):
    # 1. DM 채널 열기
    ch_data  = _slack_api("conversations.open", {"users": DM_USER_ID})
    channel  = ch_data["channel"]["id"]

    # 2. 메시지 전송
    _slack_api("chat.postMessage", {
        "channel":  channel,
        "text":     fallback_text,   # 알림 미리보기 텍스트
        "blocks":   blocks,
        "unfurl_links": False,
    })
    print(f"[OK] Slack DM 전송 완료 -> {DM_USER_ID} (채널 {channel})")


# =======================================================
# 7. 메인
# =======================================================
def main():
    # 9:00~9:30 사이 랜덤 지연 (GitHub Actions 동시 실행 분산)
    if not os.environ.get("SKIP_DELAY"):
        delay_sec = random.randint(0, 29 * 60)
        print(f"[{datetime.now().strftime('%H:%M:%S')}] {delay_sec//60}분 {delay_sec%60}초 후 실행")
        time.sleep(delay_sec)

    print(f"[{datetime.now().strftime('%H:%M:%S')}] 리포트 생성 시작")

    this_mon, this_fri = week_range(0)
    next_mon, next_fri = week_range(1)
    print(f"  이번주: {this_mon} ~ {this_fri}")
    print(f"  다음주: {next_mon} ~ {next_fri}")

    live_cbm    = fetch_box_cbm_live()
    product_cbm = fetch_product_cbm()

    this_recs = fetch_shipments(this_mon, this_fri)
    next_recs = fetch_shipments(next_mon, next_fri)
    prev_recs = fetch_prev_weeks(4)
    print(f"  이번주 {len(this_recs)}건 / 다음주 {len(next_recs)}건 / 트렌드 {len(prev_recs)}건")

    this_data = analyze(this_recs, live_cbm, this_mon, product_cbm)
    next_data = analyze(next_recs, live_cbm, next_mon, product_cbm)
    trend     = build_trend(prev_recs, live_cbm, product_cbm)

    # CBM 소스 요약 출력
    src = this_data["cbm_sources"]
    total_cbm_cnt = src["manual"] + src["box_parse"] + src["product_match"]
    print(
        f"  CBM 산출: 수동{src['manual']} + 박스파싱{src['box_parse']} "
        f"+ 품목매칭{src['product_match']} = {total_cbm_cnt}건 / "
        f"매칭제외 {src['unmatched']}건"
    )

    blocks       = build_slack_blocks(this_data, next_data, trend, this_mon)
    fallback_txt = (
        f" SCM 주간 리포트 - {this_mon.month}월 W"
        f"{(this_mon.day-1)//7+1} | "
        f"이번주 CBM {this_data['summary']['total_cbm']:.1f}m3 / "
        f"{this_data['summary']['total_count']}건"
    )

    send_dm(blocks, fallback_txt)

    # JSON 아카이브
    archive = {
        "generated_at": datetime.now().isoformat(),
        "week_start":   this_mon.isoformat(),
        "this_week":    {
            "summary":     this_data["summary"],
            "quality":     this_data["quality"],
            "box_type":    this_data["box_type"],
            "top_items":   this_data["top_items"],
            "cbm_sources": this_data["cbm_sources"],
        },
        "trend": trend,
    }
    fname = f"report_{this_mon.isoformat()}.json"
    with open(fname, "w", encoding="utf-8") as fp:
        json.dump(archive, fp, ensure_ascii=False, indent=2, default=str)
    print(f"[OK] {fname} 저장 완료")
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 완료")


if __name__ == "__main__":
    main()
