"""
기사님 운임비 정산 자동화 스크립트
Usage:
  py harness/settlement/settlement_calc.py --week 2026-05-04   # 해당 주 정산
  py harness/settlement/settlement_calc.py                     # 직전 주 자동 선택
  py harness/settlement/settlement_calc.py --dry-run           # 실제 쓰기 없이 미리보기
  py harness/settlement/settlement_calc.py --force             # 기존 운송비용 있어도 덮어쓰기

Settlement 로직:
  이장훈: 160,000원/일 / 당일 배송건수 (등분)
  조희선: (360,000 + max(0, 경기도건수-1)×30,000)/일 / 당일 배송건수
  박종성: 거리(km) × 830원 + 55,421원 기본 → 운송비용
          중대/5 + 대/3 + 특대/3 각 5,000원, 최대 50,000원 → 상하차비용
"""

import os
import re
import json
import sys
import time
import math
import argparse
import requests
from datetime import date, timedelta
from pathlib import Path
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent))
from cbm_calc import load_product_lookup, calc_from_products

load_dotenv()

# ─── Config ─────────────────────────────────────────────────────────────────
AIRTABLE_PAT = os.environ.get("AIRTABLE_PAT", "")
SLACK_TOKEN = os.environ.get("SLACK_BOT_TOKEN", "")
SLACK_DM_USER = os.environ.get("SLACK_DM_USER_ID", "")
TMS_BASE = "app4x70a8mOrIKsMf"
SHIPMENT_TABLE = "tbllg1JoHclGYer7m"
LOG_DIR = Path(__file__).parent / "state"

# Driver record IDs (배송파트너 table)
DRIVER_LEE = "recyVExCkk2Lty0E9"   # 신시어리 이장훈
DRIVER_CHO = "recPkgE4o3cs0krnR"   # 신시어리 조희선
DRIVER_PARK = "recXCfwVTqaoeQ9SS"  # 신시어리 박종성

# Park 박종성 fare model (from crossvalidation: R2=0.497)
PARK_BASE_FARE = 55421
PARK_KM_RATE = 831
PARK_TOLERANCE = 0.30  # flag if calc vs actual differs by >30%
OUTSOURCE_DAILY = 70_000  # 외주임가공→다영기획 일일 고정 운임 (수동 조정 예정)

# Origin coords for 박종성 distance calc
ORIGINS = {
    "에이원지식산업센터": (37.5477, 127.0446),
    "다영기획": (37.4360, 127.1436),
}

# Field IDs — Shipment table
F_SC_ID = "fldBUwhBlhOMsJZdv"
F_DATE = "fldQvmEwwzvQW95h9"       # 출하확정일
F_PARTNER = "fldM2u6RwLRrO7ymW"   # 배송파트너 (multipleRecordLinks)
F_FARE = "fldRT95SC88KSBATT"       # 운송비용
F_UNLOAD = "fldxmAZrBGqS7sQoL"    # 상하차비용
F_ORIGIN_ADDR = "fldb24I9EQ2KPXv6S"  # 출고지 주소 (rollup)
F_DEST_ADDR = "fldyJHUh9gN44Ggnh"   # 수령인(주소) (rollup)
F_BOX_TEXT        = "fldTjLDmw5sNGszeD"   # 최종 외박스 수량 값 (formula)
F_BOX_QTY_DIRECT  = "fldRjMaXa5TdSsGDL"  # 외박스 수량 (직접입력) — PNA fallback
F_BOX_QTY         = "fldGXhlBwI6toXSJC"   # 외박스 수량 (rollup from 배송요청) — PNA fallback
F_PROJECT_CODE    = "fldTs3FzaSdGYEiKX"   # project code (rollup) — PNA 식별용
F_REQUEST_NOTE    = "fldHQdGWe8jNrNYEM"   # 배송 요청사항 (rollup)
F_ITEMS_MFG       = "fldCnwsVrpkKHt4Hl"   # 임가공 품목 및 수량 (rollup, has qty) — CBM 계산용
F_PRODUCT_FINAL   = "fldgSupj5XLjJXYQo"   # 최종 출하 품목 (formula, name only) — CBM fallback

# Korean district coordinate lookup (same as crossvalidation.py)
KR_COORDS: dict[str, tuple[float, float]] = {
    "강남구": (37.5172, 127.0473), "강동구": (37.5301, 127.1237),
    "강북구": (37.6396, 127.0256), "강서구": (37.5510, 126.8496),
    "관악구": (37.4784, 126.9516), "광진구": (37.5384, 127.0823),
    "구로구": (37.4954, 126.8874), "금천구": (37.4569, 126.8955),
    "노원구": (37.6542, 127.0568), "도봉구": (37.6688, 127.0471),
    "동대문구": (37.5744, 127.0398), "동작구": (37.5124, 126.9393),
    "마포구": (37.5663, 126.9014), "서대문구": (37.5791, 126.9368),
    "서초구": (37.4837, 127.0324), "성동구": (37.5635, 127.0369),
    "성북구": (37.5894, 127.0167), "송파구": (37.5145, 127.1059),
    "양천구": (37.5169, 126.8664), "영등포구": (37.5264, 126.8962),
    "용산구": (37.5311, 126.9810), "은평구": (37.6026, 126.9291),
    "종로구": (37.5726, 126.9793), "중구": (37.5641, 126.9978),
    "중랑구": (37.6063, 127.0927),
    "인천중구": (37.4739, 126.5987), "인천서구": (37.5451, 126.6759),
    "인천남동구": (37.4492, 126.7312), "인천연수구": (37.4104, 126.6779),
    "인천부평구": (37.5074, 126.7218), "인천강화군": (37.7472, 126.4877),
    "인천계양구": (37.5374, 126.7381),
    "성남시": (37.4200, 127.1268), "분당구": (37.3808, 127.1178),
    "수원시": (37.2636, 127.0286), "화성시": (37.1995, 126.8319),
    "평택시": (37.0073, 127.0712), "오산시": (37.1520, 127.0773),
    "용인시": (37.2411, 127.1775), "안양시": (37.3943, 126.9568),
    "군포시": (37.3616, 126.9352), "의왕시": (37.3449, 126.9683),
    "과천시": (37.4297, 126.9878), "광명시": (37.4784, 126.8647),
    "시흥시": (37.3800, 126.8031), "안산시": (37.3219, 126.8309),
    "부천시": (37.5034, 126.7660), "김포시": (37.6146, 126.7162),
    "고양시": (37.6564, 126.8350), "파주시": (37.7600, 126.7798),
    "의정부시": (37.7382, 127.0337), "양주시": (37.7851, 127.0457),
    "남양주시": (37.6359, 127.2164), "구리시": (37.5943, 127.1296),
    "하남시": (37.5393, 127.2147),
    # 경기도 광주 — '광주'만 있으면 광주광역시(전남)로 오인식되므로 긴 패턴 우선 등록
    "경기도 광주": (37.4295, 127.2561), "경기 광주": (37.4295, 127.2561),
    "광주시": (37.4295, 127.2561),   # '경기도 광주시' 주소에서 시 단위 추출 시
    "이천시": (37.2719, 127.4348), "여주시": (37.2982, 127.6373),
    "가평군": (37.8315, 127.5109), "양평군": (37.4916, 127.4878),
    "연천군": (38.0965, 127.0743), "동두천시": (37.9038, 127.0606),
    "포천시": (37.8946, 127.2001), "안성시": (37.0079, 127.2798),
    # 충청권
    "대전": (36.3504, 127.3845), "청주시": (36.6424, 127.4890),
    "충주시": (36.9910, 127.9259), "천안시": (36.8065, 127.1524),
    "아산시": (36.7898, 127.0022), "공주시": (36.4465, 127.1190),
    "논산시": (36.1868, 127.0985), "서산시": (36.7847, 126.4503),
    "당진시": (36.8925, 126.6297), "홍성군": (36.6010, 126.6611),
    "보령시": (36.3333, 126.6127),
    "세종시": (36.4801, 127.2889),
    # 전라권
    "전주시": (35.8242, 127.1479), "군산시": (35.9677, 126.7368),
    "익산시": (35.9483, 126.9574), "정읍시": (35.5699, 126.8561),
    "남원시": (35.4163, 127.3903), "김제시": (35.8037, 126.8802),
    "순천시": (34.9506, 127.4872), "여수시": (34.7604, 127.6622),
    "목포시": (34.8118, 126.3922), "광양시": (34.9404, 127.6965),
    "나주시": (35.0159, 126.7103),
    # 광주광역시 — '경기도'/'경기' 없는 주소의 '광주'는 여기
    "광주": (35.1595, 126.8526),
    # 경상권
    "대구": (35.8714, 128.6014),
    "경산시": (35.8250, 128.7408), "구미시": (36.1196, 128.3444),
    "경주시": (35.8562, 129.2247), "안동시": (36.5684, 128.7295),
    "영천시": (35.9734, 128.9378), "상주시": (36.4107, 128.1591),
    "부산": (35.1796, 129.0756), "울산": (35.5384, 129.3114),
    "창원시": (35.2280, 128.6812), "진주시": (35.1799, 128.1076),
    "김해시": (35.2280, 128.8890), "거제시": (34.8800, 128.6211),
    "통영시": (34.8544, 128.4333), "사천시": (35.0030, 128.0643),
    "밀양시": (35.5036, 128.7460), "양산시": (35.3350, 129.0337),
    "포항시": (36.0190, 129.3435),
    # 강원권
    "춘천시": (37.8813, 127.7298), "원주시": (37.3422, 127.9202),
    "강릉시": (37.7519, 128.8761), "동해시": (37.5244, 129.1142),
    "속초시": (38.2070, 128.5918), "태백시": (37.1641, 128.9855),
    "삼척시": (37.4498, 129.1659), "홍천군": (37.6935, 127.8886),
    "횡성군": (37.4914, 127.9845), "양양군": (38.0758, 128.6188),
    "고성군": (38.3806, 128.4677), "인제군": (38.0708, 128.1706),
    "평창군": (37.3706, 128.3901), "정선군": (37.3793, 128.6602),
    "영월군": (37.1836, 128.4618), "화천군": (38.1059, 127.7082),
    "철원군": (38.1463, 127.3138), "양구군": (38.1109, 127.9894),
}

# ─── Helpers ─────────────────────────────────────────────────────────────────

def _str_field(raw) -> str:
    if isinstance(raw, list):
        return str(raw[0] or "").strip() if raw else ""
    return str(raw or "").strip()


def haversine_km(lat1, lng1, lat2, lng2) -> float:
    R = 6371
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def estimate_dest_coord(addr: str):
    if not addr:
        return None
    # 긴 패턴 우선 매칭 (경기도 광주 vs 광주광역시 등 중복 지명 해소)
    for name in sorted(KR_COORDS, key=len, reverse=True):
        if name in addr:
            return KR_COORDS[name]
    # 행정구역 정규식 추출
    m = re.search(r"([가-힣]+(?:구|시|군))", addr)
    if m and m.group(1) in KR_COORDS:
        return KR_COORDS[m.group(1)]
    # 광역시·특별시 단어 fallback — 광주는 경기 문맥 없을 때만 전남
    for city in ["인천", "대전", "대구", "부산", "울산", "세종"]:
        if city in addr:
            return KR_COORDS.get(city)
    if "광주" in addr:
        # 경기도 광주: 이미 위 긴패턴에서 처리됨. 여기 오면 전남 광주
        return KR_COORDS["광주"]
    return None


def _round500(x: float) -> int:
    """500원 단위 올림 — 1~499원은 500원으로, 501~999원은 1,000원으로"""
    return math.ceil(x / 500) * 500


def parse_unload_fee(box_text) -> int:
    if not box_text:
        return 0
    s = str(box_text)
    try:
        heavy = int(re.search(r"중대(\d+)", s).group(1)) if re.search(r"중대(\d+)", s) else 0
        large = int(re.search(r"(?<!중)(?<!특)대(\d+)", s).group(1)) if re.search(r"(?<!중)(?<!특)대(\d+)", s) else 0
        xlarge = int(re.search(r"특대(\d+)", s).group(1)) if re.search(r"특대(\d+)", s) else 0
        return min((heavy // 5) * 5000 + (large // 3) * 5000 + (xlarge // 3) * 5000, 50000)
    except Exception:
        return 0


def week_range(week_start: str) -> tuple[str, str]:
    """Return (monday, sunday) ISO dates for the week containing week_start."""
    d = date.fromisoformat(week_start)
    mon = d - timedelta(days=d.weekday())
    sun = mon + timedelta(days=6)
    return mon.isoformat(), sun.isoformat()


def today_iso() -> str:
    return date.today().isoformat()

# ─── Airtable API ─────────────────────────────────────────────────────────────

def fetch_week(monday: str, sunday: str) -> list[dict]:
    """Fetch all Shipments for the given week with a 배송파트너 linked."""
    url = f"https://api.airtable.com/v0/{TMS_BASE}/{SHIPMENT_TABLE}"
    headers = {"Authorization": f"Bearer {AIRTABLE_PAT}"}
    # Airtable stores dates as ISO datetime strings ("2026-05-08T00:00:00.000Z"),
    # so <= 'YYYY-MM-DD' would exclude that day. Use < next_day instead.
    end_excl = (date.fromisoformat(sunday) + timedelta(days=1)).isoformat()
    formula = (
        f"AND("
        f"{{출하확정일}}>='{monday}',"
        f"{{출하확정일}}<'{end_excl}',"
        f"NOT({{배송파트너}}='')"
        f")"
    )
    records, cursor = [], None
    while True:
        params = {
            "filterByFormula": formula,
            "returnFieldsByFieldId": "true",
            "fields[]": [F_SC_ID, F_DATE, F_PARTNER, F_FARE, F_UNLOAD,
                         F_ORIGIN_ADDR, F_DEST_ADDR, F_BOX_TEXT,
                         F_BOX_QTY_DIRECT, F_BOX_QTY, F_PROJECT_CODE,
                         F_REQUEST_NOTE, F_ITEMS_MFG, F_PRODUCT_FINAL],
            "pageSize": 100,
        }
        if cursor:
            params["offset"] = cursor
        r = requests.get(url, headers=headers, params=params, timeout=30)
        if not r.ok:
            raise RuntimeError(f"Airtable {r.status_code}: {r.text[:200]}")
        data = r.json()
        records.extend(data.get("records", []))
        cursor = data.get("offset")
        if not cursor:
            break
        time.sleep(0.2)
    return records


def notify_slack(monday: str, sunday: str, dry_run: bool, written: int, skipped: int, totals: dict) -> None:
    if not SLACK_TOKEN or not SLACK_DM_USER:
        return
    label = "[DRY-RUN] " if dry_run else ""
    date_label = monday if monday == sunday else f"{monday} ~ {sunday}"
    lines = [f"{label}*정산 완료* {date_label}"]
    for drv, t in totals.items():
        u_str = f"  상하차 {t['unload']:,}" if t.get("unload") else ""
        lines.append(f"  {drv}: {t['count']}건  운임 {t['fare']:,}{u_str}")
    lines.append(f"작성: {written}건 / 기존값 스킵: {skipped}건")
    try:
        ch = requests.post(
            "https://slack.com/api/conversations.open",
            headers={"Authorization": f"Bearer {SLACK_TOKEN}", "Content-Type": "application/json"},
            json={"users": SLACK_DM_USER}, timeout=10,
        ).json()["channel"]["id"]
        requests.post(
            "https://slack.com/api/chat.postMessage",
            headers={"Authorization": f"Bearer {SLACK_TOKEN}", "Content-Type": "application/json"},
            json={"channel": ch, "text": "\n".join(lines)},
            timeout=10,
        )
    except Exception:
        pass


def update_record(rec_id: str, fare: int, unload: int, dry_run: bool) -> bool:
    """Update 운송비용 and 상하차비용 on a Shipment record."""
    fields = {F_FARE: fare}
    if unload > 0:
        fields[F_UNLOAD] = unload
    if dry_run:
        return True
    url = f"https://api.airtable.com/v0/{TMS_BASE}/{SHIPMENT_TABLE}/{rec_id}"
    r = requests.patch(
        url,
        headers={"Authorization": f"Bearer {AIRTABLE_PAT}", "Content-Type": "application/json"},
        json={"fields": fields},
        timeout=15,
    )
    if not r.ok:
        print(f"  ERROR updating {rec_id}: {r.status_code} {r.text[:100]}")
        return False
    time.sleep(0.25)  # stay under rate limit
    return True

# ─── Settlement calculations ──────────────────────────────────────────────────

def calc_lee(recs: list[dict]) -> list[dict]:
    """
    이장훈: 160,000원/day ÷ 당일 배송건수
    """
    from collections import defaultdict
    daily: defaultdict[str, list] = defaultdict(list)
    for rec in recs:
        d = rec["fields"].get(F_DATE, "")
        daily[d].append(rec)

    results = []
    for d, day_recs in sorted(daily.items()):
        n = len(day_recs)
        per_ship = _round500(160000 / n)
        for rec in day_recs:
            results.append({
                "rec_id": rec["id"],
                "sc_id": rec["fields"].get(F_SC_ID, ""),
                "date": d,
                "driver": "이장훈",
                "fare_calc": per_ship,
                "unload_calc": 0,
                "fare_existing": rec["fields"].get(F_FARE) or 0,
                "note": f"160,000/{n}",
            })
    return results


def calc_cho(recs: list[dict]) -> list[dict]:
    """
    조희선: (360,000 + max(0, 경기도건수-1) × 30,000) / 당일 배송건수
    경기도 판단: 수령인(주소) 에 '경기' 포함
    """
    from collections import defaultdict
    daily: defaultdict[str, list] = defaultdict(list)
    for rec in recs:
        d = rec["fields"].get(F_DATE, "")
        daily[d].append(rec)

    results = []
    for d, day_recs in sorted(daily.items()):
        gyeonggi_count = sum(
            1 for rec in day_recs
            if "경기" in _str_field(rec["fields"].get(F_DEST_ADDR))
        )
        surcharge = max(0, gyeonggi_count - 1) * 30000
        daily_total = 360000 + surcharge
        n = len(day_recs)
        per_ship = _round500(daily_total / n)
        for rec in day_recs:
            dest = _str_field(rec["fields"].get(F_DEST_ADDR))
            results.append({
                "rec_id": rec["id"],
                "sc_id": rec["fields"].get(F_SC_ID, ""),
                "date": d,
                "driver": "조희선",
                "fare_calc": per_ship,
                "unload_calc": 0,
                "fare_existing": rec["fields"].get(F_FARE) or 0,
                "note": f"({360000}+{surcharge}=>{daily_total})/{n}  경기={gyeonggi_count}건",
            })
    return results


def _is_outsource(rec: dict) -> bool:
    """MM 외주임가공 → 다영기획 배송 여부 판별.
    SC id가 'MM'으로 시작 + 수령인(주소)에 '다영기획' + 배송요청사항에 '외주임가공' 포함.
    이 경우 일일 고정 70,000원을 당일 해당 건수로 나눔(수동 콘솔 조정 예정).
    """
    sc_id = rec["fields"].get(F_SC_ID, "") or ""
    dest  = _str_field(rec["fields"].get(F_DEST_ADDR))
    note  = _str_field(rec["fields"].get(F_REQUEST_NOTE))
    return (
        sc_id.startswith("MM") and
        "다영기획" in dest and
        "외주임가공" in note
    )


def _is_pna(rec: dict) -> bool:
    """PNA 프로젝트 고객납품건 여부 — project code 필드에 'PNA' 포함."""
    code = _str_field(rec["fields"].get(F_PROJECT_CODE))
    return "PNA" in code.upper()


def calc_park(recs: list[dict], product_lookup: dict | None = None) -> list[dict]:
    """
    박종성:
      일반건: 운송비용 = PARK_BASE_FARE + PARK_KM_RATE × road_km
              상하차비용 우선순위:
                1) F_BOX_TEXT 있으면 → parse_unload_fee
                2) F_BOX_TEXT 없고 PNA → F_BOX_QTY_DIRECT / F_BOX_QTY fallback
                3) 위 모두 없고 product_lookup 있으면 → cbm_calc (임가공 품목 및 수량)
      외주임가공건: SC id='MM'+수령인=다영기획+요청사항='외주임가공'
              → 일일 고정 70,000원 / 당일 해당 건수
    """
    from collections import defaultdict

    outsource = [r for r in recs if _is_outsource(r)]
    normal    = [r for r in recs if not _is_outsource(r)]

    results = []

    # ── 외주임가공 케이스: 날짜별 70,000원 균등 배분 ──
    outsource_by_date: defaultdict[str, list] = defaultdict(list)
    for rec in outsource:
        outsource_by_date[rec["fields"].get(F_DATE, "")].append(rec)

    for d, day_recs in sorted(outsource_by_date.items()):
        n = len(day_recs)
        per_ship = _round500(OUTSOURCE_DAILY / n)
        for rec in day_recs:
            results.append({
                "rec_id": rec["id"],
                "sc_id": rec["fields"].get(F_SC_ID, ""),
                "date": d,
                "driver": "박종성",
                "fare_calc": per_ship,
                "unload_calc": 0,
                "fare_existing": rec["fields"].get(F_FARE) or 0,
                "note": f"MM외주임가공70k/{n}건",
            })

    # ── 일반 케이스: haversine 거리 운임 ──
    for rec in normal:
        sc_id = rec["fields"].get(F_SC_ID, "")
        date_val = rec["fields"].get(F_DATE, "")
        origin_addr = _str_field(rec["fields"].get(F_ORIGIN_ADDR))
        dest_addr   = _str_field(rec["fields"].get(F_DEST_ADDR))
        box_text = rec["fields"].get(F_BOX_TEXT, "") or ""
        if not box_text and _is_pna(rec):
            # PNA 고객납품건: 직접입력 → rollup 순으로 fallback
            box_text = (
                _str_field(rec["fields"].get(F_BOX_QTY_DIRECT))
                or _str_field(rec["fields"].get(F_BOX_QTY))
                or ""
            )
        # Priority 3: CBM 마스터 기반 하차비 (박스 데이터 없을 때)
        cbm_unload = 0
        if not box_text and product_lookup:
            items_text = (
                _str_field(rec["fields"].get(F_ITEMS_MFG))
                or _str_field(rec["fields"].get(F_PRODUCT_FINAL))
            )
            if items_text:
                cbm_result = calc_from_products(items_text, product_lookup)
                cbm_unload = cbm_result["unload_fee"]

        origin_coord = ORIGINS["에이원지식산업센터"]
        if "성남시" in origin_addr or "다영" in origin_addr:
            origin_coord = ORIGINS["다영기획"]

        dest_coord = estimate_dest_coord(dest_addr)
        fare_calc = 0
        note = ""

        if dest_coord:
            hav = haversine_km(origin_coord[0], origin_coord[1], dest_coord[0], dest_coord[1])
            road_km = hav * 1.35
            fare_calc = _round500(PARK_BASE_FARE + PARK_KM_RATE * road_km)
            note = f"{road_km:.1f}km ({PARK_BASE_FARE}+{PARK_KM_RATE}x{road_km:.1f})"
        else:
            note = f"NO_COORD: {dest_addr[:30]}"

        unload_calc = parse_unload_fee(box_text) or cbm_unload
        existing_fare = rec["fields"].get(F_FARE) or 0

        if fare_calc and existing_fare:
            delta = abs(fare_calc - existing_fare) / existing_fare
            if delta > PARK_TOLERANCE:
                note += f"  [FLAG >{PARK_TOLERANCE*100:.0f}%: calc={fare_calc:,} existing={existing_fare:,}]"

        results.append({
            "rec_id": rec["id"],
            "sc_id": sc_id,
            "date": date_val,
            "driver": "박종성",
            "fare_calc": fare_calc,
            "unload_calc": unload_calc,
            "fare_existing": existing_fare,
            "note": note,
        })
    return results

# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="기사님 운임비 정산 자동화")
    parser.add_argument("--date", help="정산 날짜 (YYYY-MM-DD). 기본: 오늘")
    parser.add_argument("--week", help="정산 주 시작일 (YYYY-MM-DD, 월요일 기준) — 주간 일괄 모드")
    parser.add_argument("--dry-run", action="store_true", help="실제 쓰기 없이 미리보기")
    parser.add_argument("--force", action="store_true", help="기존 운송비용 있어도 덮어쓰기")
    parser.add_argument("--auto-confirm", action="store_true", help="사용자 확인 없이 자동 실행 (CI용)")
    args = parser.parse_args()

    if not AIRTABLE_PAT:
        print("ERROR: AIRTABLE_PAT environment variable not set")
        return

    # 1. Determine date range
    if args.week:
        monday, sunday = week_range(args.week)
        label = f"Week: {monday} ~ {sunday}"
    else:
        target = args.date or today_iso()
        monday = sunday = target
        label = f"Date: {target}"
    print(f"\n[Settlement] {label}  {'[DRY-RUN]' if args.dry_run else '[LIVE WRITE]'}\n")

    # 2. Fetch shipments
    print(f"Fetching shipments...")
    all_recs = fetch_week(monday, sunday)
    print(f"  Total: {len(all_recs)}")

    # 3. Split by driver
    lee_recs = [r for r in all_recs if DRIVER_LEE in (r["fields"].get(F_PARTNER) or [])]
    cho_recs = [r for r in all_recs if DRIVER_CHO in (r["fields"].get(F_PARTNER) or [])]
    park_recs = [r for r in all_recs if DRIVER_PARK in (r["fields"].get(F_PARTNER) or [])]
    print(f"  이장훈={len(lee_recs)}  조희선={len(cho_recs)}  박종성={len(park_recs)}")

    # 3b. Load CBM product lookup for 박종성 unload fee fallback
    product_lookup: dict | None = None
    if park_recs:
        print(f"  CBM 품목 룩업 로딩 중...")
        try:
            product_lookup = load_product_lookup({"Authorization": f"Bearer {AIRTABLE_PAT}"})
            print(f"  {len(product_lookup)//2}개 품목 로드 완료")
        except Exception as e:
            print(f"  WARNING: CBM 룩업 실패 (unload fallback 비활성) — {e}")

    # 4. Calculate
    settlement = (
        calc_lee(lee_recs) +
        calc_cho(cho_recs) +
        calc_park(park_recs, product_lookup=product_lookup)
    )

    if not settlement:
        print("\nNo records to settle for this week.")
        return

    # 5. Filter: skip if fare already set and not --force
    to_write = []
    skipped_existing = 0
    for item in settlement:
        if item["fare_existing"] and not args.force:
            skipped_existing += 1
        else:
            to_write.append(item)

    # 6. Preview
    print(f"\n{'='*70}")
    print(f"SETTLEMENT PREVIEW — {len(to_write)} records to update ({skipped_existing} skipped: already set)")
    print(f"{'='*70}")
    print(f"{'SC ID':<13} {'Date':<11} {'Driver':<8} {'Calc':>8} {'Unload':>8}  Note")
    print("-" * 70)

    driver_totals: dict[str, dict] = {}
    for item in to_write:
        drv = item["driver"]
        if drv not in driver_totals:
            driver_totals[drv] = {"count": 0, "fare": 0, "unload": 0}
        driver_totals[drv]["count"] += 1
        driver_totals[drv]["fare"] += item["fare_calc"]
        driver_totals[drv]["unload"] += item["unload_calc"]
        u = f"{item['unload_calc']:>8,}" if item["unload_calc"] else "       -"
        print(f"{item['sc_id']:<13} {item['date']:<11} {item['driver']:<8} "
              f"{item['fare_calc']:>8,}  {u}  {item['note']}")

    print(f"\nDriver totals:")
    for drv, totals in driver_totals.items():
        u_str = f"  unload={totals['unload']:,}" if totals["unload"] else ""
        print(f"  {drv}: {totals['count']}건  fare={totals['fare']:,}{u_str}")

    if args.dry_run:
        print("\n[DRY-RUN] No changes written.")
        notify_slack(monday, sunday, dry_run=True, written=0, skipped=skipped_existing, totals=driver_totals)
        return

    # 7. Confirm
    if not args.auto_confirm:
        resp = input("\nProceed with writing to Airtable? [y/N] ").strip().lower()
        if resp != "y":
            print("Aborted.")
            return

    # 8. Write
    print(f"\nWriting {len(to_write)} records...")
    ok = 0
    for item in to_write:
        success = update_record(item["rec_id"], item["fare_calc"], item["unload_calc"], dry_run=False)
        if success:
            ok += 1
        else:
            print(f"  FAILED: {item['sc_id']}")

    # 9. Save log
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / f"settlement_{monday}.json"
    with open(log_path, "w", encoding="utf-8") as f:
        json.dump({
            "week": {"monday": monday, "sunday": sunday},
            "dry_run": args.dry_run,
            "force": args.force,
            "written": ok,
            "skipped_existing": skipped_existing,
            "records": settlement,
        }, f, ensure_ascii=False, indent=2)

    print(f"\nDone: {ok}/{len(to_write)} written. Log -> {log_path}")
    notify_slack(monday, sunday, dry_run=False, written=ok, skipped=skipped_existing, totals=driver_totals)


if __name__ == "__main__":
    main()
