“””
Sincerely SCM 월간 출하 리포트
─────────────────────────────────────────────
매월 1일 09:00 KST 슬랙 DM 자동 발송

포함 지표:
[CBM]     월 총 CBM / 주차별 CBM 추이
[배차]    월 총 배차 건수 / 배송파트너별 배송 비율
[손익]    월 물류매출 / 운송비용 / 물류 손익
[품목]    월 출하 품목 Top 10

환경변수:
AIRTABLE_API_KEY_TMS   Airtable PAT
AIRTABLE_BASE_TMS_ID   TMS base (app4x70a8mOrIKsMf)
SLACK_BOT_TOKEN        Bot Token (xoxb-…)
SLACK_DM_USER_ID       수신자 Slack User ID
“””

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

# ── 환경변수 ──────────────────────────────────────────

API_KEY     = os.environ[“AIRTABLE_API_KEY_TMS”]
BASE_ID     = os.environ.get(“AIRTABLE_BASE_TMS_ID”, “app4x70a8mOrIKsMf”)
SLACK_TOKEN = os.environ[“SLACK_BOT_TOKEN”]
DM_USER_ID  = os.environ[“SLACK_DM_USER_ID”]

# ── Table ID ──────────────────────────────────────────

TABLE_SHIPMENT = “tbllg1JoHclGYer7m”
TABLE_BOX      = “tbltwH7bHk41rTzhM”
TABLE_PRODUCT  = “tblBNh6oGDlTKGrdQ”   # Product 테이블 (CBM 기준값)
TABLE_PRODUCT  = “tblBNh6oGDlTKGrdQ”   # Product 테이블 (CBM 기준값)

# ── Field ID ──────────────────────────────────────────

F_DATE       = “fldQvmEwwzvQW95h9”   # 출하확정일
F_ITEM       = “fldgSupj5XLjJXYQo”   # 최종 출하 품목
F_BOX_PARSED = “fldTjLDmw5sNGszeD”   # 최종 외박스 수량 값
F_BOX_MANUAL = “fldRjMaXa5TdSsGDL”   # 외박스 수량 직접입력
F_TOTAL_CBM  = “fldJ9DHjwoRyeUEqE”   # Total_CBM
F_STATUS     = “fldOhibgxg6LIpRTi”   # 발송상태_TMS
F_REVENUE    = “fldOFuvqBT0iXItcT”   # 물류매출
F_COST       = “fldRT95SC88KSBATT”   # 운송비용
F_PARTNER    = “fldHZ7yMT3KEu2gSj”   # 배송파트너

# Box 테이블

F_BOX_CODE = “fldELrd8bBVjQCHnp”
F_BOX_NAME = “fldgvlGjLb4FTlQ0v”
F_BOX_CBM  = “fldjFaXiYzeJ2Zt7M”

# ── 박스 CBM fallback ─────────────────────────────────

BOX_CBM = {
“극소”: 0.0098, “S280”: 0.0098,
“소”:   0.0117, “S360”: 0.0117,
“중”:   0.0201, “M350”: 0.0201,
“중대”: 0.0492, “M480”: 0.0492,
“대”:   0.1066, “L510”: 0.1066,
“특대”: 0.1663, “L560”: 0.1663,
}

# ── 파트너 그룹 정규화 ────────────────────────────────

# Airtable 파트너명 → 리포트 표시명

PARTNER_GROUP = {
“신시어리 (이장훈)”:  “신시어리 기사님 (이장훈)”,
“신시어리 (박종성)”:  “신시어리 기사님 (박종성)”,
“신시어리 (조희선)”:  “신시어리 기사님 (조희선)”,
“신시어리 (로젠)”:    “로젠 택배”,
“고객”:               “고객 직접수령”,
}

# 매핑 안 된 경우 그대로 사용

# ── 품목 → CBM 매핑은 Product 테이블에서 실시간 조회 (fetch_product_cbm 참조)

# 하드코딩 제거 → Airtable Product 테이블 사용

_BOX_RE = re.compile(
r”(극소|소|중대|중|대|특대|S280|S360|M350|M480|L510|L560)\s*(\d+)”
)

# ═══════════════════════════════════════════════════════

# 1. 날짜 유틸

# ═══════════════════════════════════════════════════════

def prev_month_range() -> tuple[date, date]:
“”“전월 1일 ~ 말일”””
today     = date.today()
first_day = today.replace(day=1)
last_day  = first_day - timedelta(days=1)
start     = last_day.replace(day=1)
return start, last_day

def month_label(d: date) -> str:
return f”{d.year}년 {d.month}월”

def week_number_of_month(d: date) -> int:
“”“해당 날짜가 월의 몇째주인지”””
return (d.day - 1) // 7 + 1

# ═══════════════════════════════════════════════════════

# 2. Airtable 조회

# ═══════════════════════════════════════════════════════

def fetch_month_shipments(start: date, end: date) -> list[dict]:
api   = pyairtable.Api(API_KEY)
table = api.table(BASE_ID, TABLE_SHIPMENT)
formula = (
f”AND(”
f”IS_AFTER({{출하확정일}}, DATEADD(’{start.isoformat()}’, -1, ‘days’)), “
f”IS_BEFORE({{출하확정일}}, DATEADD(’{end.isoformat()}’,  1, ‘days’))”
f”)”
)
return table.all(formula=formula)

def fetch_box_cbm_live() -> dict:
api   = pyairtable.Api(API_KEY)
table = api.table(BASE_ID, TABLE_BOX)
live  = {}
for rec in table.all():
f = rec[“fields”]
for key in (f.get(“Box Code”), f.get(“박스”)):
if key:
live[key] = f.get(“cbm”, 0)
return live

def fetch_product_cbm() -> list[tuple[str, float]]:
“””
Product 테이블에서 품목명 + CBM/박스 값을 읽어
(공백제거된 품목명, cbm_per_box) 리스트 반환.
긴 이름 → 짧은 이름 순 정렬로 greedy 매칭 준비.

```
필드:
  fldx01uKEnCd0J0nP  품목명
  fldN1JrkxIr5m6pXz  CBM/박스 (단품)
  fld6W5ImO7UeBVMPI  CBM/박스 (키트)
"""
api   = pyairtable.Api(API_KEY)
table = api.table(BASE_ID, TABLE_PRODUCT)
result = []
for rec in table.all(fields=[
    "fldx01uKEnCd0J0nP",
    "fldN1JrkxIr5m6pXz",
    "fld6W5ImO7UeBVMPI",
]):
    f    = rec["fields"]
    name = (f.get("fldx01uKEnCd0J0nP") or "").strip()
    cbm  = f.get("fldN1JrkxIr5m6pXz") or f.get("fld6W5ImO7UeBVMPI")
    if name and cbm:
        try:
            norm = re.sub(r"\s+", "", name)
            result.append((norm, float(cbm)))
        except (ValueError, TypeError):
            pass
result.sort(key=lambda x: -len(x[0]))
print(f"  Product CBM 조회 완료: {len(result)}개 품목")
return result
```

# ═══════════════════════════════════════════════════════

# 3. CBM 파싱

# ═══════════════════════════════════════════════════════

def parse_box_cbm(box_str: str, live: dict) -> float:
ref   = {**BOX_CBM, **live}
total = 0.0
for m in _BOX_RE.finditer(box_str):
btype, cnt = m.group(1), int(m.group(2))
total += ref.get(btype, 0) * cnt
return round(total, 4)

def match_cbm_from_product(item_str: str, product_cbm: list[tuple[str, float]]) -> float:
“””
Product 테이블 CBM으로 품목 CBM 산출.
- 공백 제거 후 부분 일치 (긴 이름 우선 greedy)
- 매칭 안 되면 0.0 반환
“””
total = 0.0
matched_any = False

```
for line in item_str.strip().splitlines():
    line = line.strip()
    if not line:
        continue
    norm_line = re.sub(r"\s+", "", line)
    nums = re.findall(r"\d+", norm_line)

    for prod_norm, cbm_per_box in product_cbm:
        if prod_norm in norm_line:
            qty = int(nums[-1]) if nums else 1
            total += cbm_per_box * qty
            matched_any = True
            break

return round(total, 4) if matched_any else 0.0
```

def get_cbm(f: dict, live: dict,
product_cbm: list[tuple[str, float]] | None = None) -> float:
“””
CBM 산정 우선순위:
1순위: Total_CBM 수동 입력
2순위: Product 테이블 품목 매칭
3순위: 최종 외박스 수량 값 파싱
→ 둘 다 없으면 0.0
“””
# 1순위: 수동 입력
total_cbm_f = f.get(“Total_CBM”)
if total_cbm_f and total_cbm_f > 0:
return float(total_cbm_f)

```
# 2순위: Product 테이블 매칭
item_str = f.get("최종 출하 품목") or ""
if item_str.strip() and product_cbm:
    cbm_val = match_cbm_from_product(item_str, product_cbm)
    if cbm_val > 0:
        return cbm_val

# 3순위: 외박스 수량 파싱
box_qty = f.get("최종 외박스 수량 값") or f.get("외박스 수량 (직접입력)") or ""
if isinstance(box_qty, list):
    box_qty = ", ".join(str(x) for x in box_qty)
box_qty = box_qty.strip()
if box_qty and _BOX_RE.search(box_qty):
    return parse_box_cbm(box_qty, live)

# 모두 실패
return 0.0
```

# ═══════════════════════════════════════════════════════

# 4. 월간 분석

# ═══════════════════════════════════════════════════════

def analyze_month(records: list[dict], live_cbm: dict,
product_cbm: list[tuple[str, float]] | None = None) -> dict:
total_cbm   = 0.0
total_count = 0
total_rev   = 0.0
total_cost  = 0.0

```
# 주차별 집계 {1: cbm, 2: cbm, ...}
weekly_cbm: dict[int, float]  = defaultdict(float)
weekly_cnt: dict[int, int]    = defaultdict(int)

# 파트너별 집계
partner_cnt: dict[str, int]   = defaultdict(int)
partner_cbm: dict[str, float] = defaultdict(float)

# 품목별 집계
item_agg: dict = defaultdict(lambda: {"qty": 0, "cbm": 0.0})

for rec in records:
    f   = rec["fields"]
    d_s = f.get("출하확정일")
    if not d_s:
        continue

    ship_date   = date.fromisoformat(d_s)
    week_no     = week_number_of_month(ship_date)
    cbm_val     = get_cbm(f, live_cbm, product_cbm)

    total_count += 1
    total_cbm   += cbm_val
    total_rev   += f.get("물류매출") or 0
    total_cost  += f.get("운송비용") or 0

    weekly_cbm[week_no] += cbm_val
    weekly_cnt[week_no] += 1

    # 배송파트너 파싱
    partner_field = f.get("배송파트너 (from 배송파트너)")
    if partner_field:
        if isinstance(partner_field, dict):
            names = []
            for vals in partner_field.get("valuesByLinkedRecordId", {}).values():
                names.extend(vals)
        elif isinstance(partner_field, list):
            names = [str(p) for p in partner_field]
        else:
            names = [str(partner_field)]

        for raw_name in names:
            display = PARTNER_GROUP.get(raw_name, raw_name)
            partner_cnt[display] += 1
            partner_cbm[display] += cbm_val

    # 품목 집계 (Product 테이블 CBM 사용)
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
            if product_cbm:
                norm_line = re.sub(r"\s+", "", iname)
                for prod_norm, cpb in product_cbm:
                    if prod_norm in norm_line:
                        item_agg[iname]["cbm"] += round(cpb * qty, 4)
                        break

total_cbm  = round(total_cbm, 2)
total_rev  = round(total_rev, 0)
total_cost = round(total_cost, 0)

# 파트너별 비율
partner_pct = {}
for p, cnt in partner_cnt.items():
    partner_pct[p] = round(cnt / total_count * 100, 1) if total_count else 0

# Top 품목 (CBM 기준)
top_items = sorted(
    [(k, v["qty"], round(v["cbm"], 3)) for k, v in item_agg.items()],
    key=lambda x: -x[2],
)[:10]

return {
    "total_cbm":    total_cbm,
    "total_count":  total_count,
    "total_rev":    total_rev,
    "total_cost":   total_cost,
    "profit":       total_rev - total_cost,
    "cbm_per_ship": round(total_cbm / total_count, 3) if total_count else 0,
    "weekly_cbm":   dict(weekly_cbm),
    "weekly_cnt":   dict(weekly_cnt),
    "partner_cnt":  dict(partner_cnt),
    "partner_pct":  partner_pct,
    "partner_cbm":  dict(partner_cbm),
    "top_items":    top_items,
}
```

# ═══════════════════════════════════════════════════════

# 5. Slack Block 빌더

# ═══════════════════════════════════════════════════════

def _bar(val: float, max_val: float, width: int = 10) -> str:
filled = round(val / max_val * width) if max_val else 0
return “█” * filled + “░” * (width - filled)

def _pct_bar(pct: float, width: int = 8) -> str:
filled = round(pct / 100 * width)
return “█” * filled + “░” * (width - filled)

def build_monthly_blocks(data: dict, month_start: date) -> list[dict]:
label = month_label(month_start)

```
# ── 주차별 CBM ────────────────────────────────────
max_w_cbm  = max(data["weekly_cbm"].values(), default=1)
weekly_txt = ""
for wk in sorted(data["weekly_cbm"].keys()):
    cbm = data["weekly_cbm"][wk]
    cnt = data["weekly_cnt"].get(wk, 0)
    bar = _bar(cbm, max_w_cbm, 10)
    weekly_txt += f"  `{wk}주차`  {bar}  *{cbm:.1f}m³*  ({cnt}건)\n"

# ── 배송파트너 비율 ───────────────────────────────
partner_txt = ""
sorted_partners = sorted(
    data["partner_cnt"].items(), key=lambda x: -x[1]
)
total_with_partner = sum(data["partner_cnt"].values())

for name, cnt in sorted_partners:
    pct = data["partner_pct"].get(name, 0)
    cbm = round(data["partner_cbm"].get(name, 0), 2)
    bar = _pct_bar(pct, 8)
    partner_txt += (
        f"  `{name}`\n"
        f"    {bar}  *{pct:.1f}%*  {cnt}건  |  {cbm:.2f}m³\n"
    )

unassigned = data["total_count"] - total_with_partner
if unassigned > 0:
    pct = round(unassigned / data["total_count"] * 100, 1)
    partner_txt += f"  `미배정`  {'░' * 8}  {pct:.1f}%  {unassigned}건\n"

# ── Top 품목 ──────────────────────────────────────
item_txt = ""
for i, (name, qty, cbm) in enumerate(data["top_items"][:8], 1):
    item_txt += f"  {i}. {name}  `{qty:,}개`  →  *{cbm:.3f}m³*\n"

# ── 손익 ──────────────────────────────────────────
profit_sign = "+" if data["profit"] >= 0 else ""
rev_txt = (
    f"  물류매출   ₩{data['total_rev']:,.0f}\n"
    f"  운송비용   ₩{data['total_cost']:,.0f}\n"
    f"  물류 손익  *₩{profit_sign}{data['profit']:,.0f}*"
)
if data["total_rev"] == 0:
    rev_txt += "\n  _물류매출 필드 입력 필요_"

blocks = [
    {
        "type": "header",
        "text": {
            "type": "plain_text",
            "text": f"📊 SCM 월간 출하 리포트 — {label}",
        },
    },
    {
        "type": "context",
        "elements": [{
            "type": "mrkdwn",
            "text": (
                f"{month_start.strftime('%Y-%m-%d')} ~ "
                f"{(month_start.replace(month=month_start.month % 12 + 1, day=1) - timedelta(1)).strftime('%m-%d')}  |  "
                f"생성: {datetime.now().strftime('%m/%d %H:%M')}"
            ),
        }],
    },
    {"type": "divider"},
    # ① 핵심 요약
    {
        "type": "section",
        "text": {
            "type": "mrkdwn",
            "text": (
                f"*📦 월간 핵심 요약*\n"
                f"  총 CBM         *{data['total_cbm']:.2f} m³*\n"
                f"  총 배차 건수    *{data['total_count']}건*\n"
                f"  건당 평균 CBM   {data['cbm_per_ship']:.3f} m³"
            ),
        },
    },
    {"type": "divider"},
    # ② 주차별 CBM
    {
        "type": "section",
        "text": {
            "type": "mrkdwn",
            "text": f"*📅 주차별 CBM 추이*\n{weekly_txt}",
        },
    },
    {"type": "divider"},
    # ③ 배송파트너 비율
    {
        "type": "section",
        "text": {
            "type": "mrkdwn",
            "text": (
                f"*🚚 배송파트너별 배송 비율*  (총 {data['total_count']}건)\n"
                f"{partner_txt}"
            ),
        },
    },
    {"type": "divider"},
    # ④ 물류 손익
    {
        "type": "section",
        "text": {
            "type": "mrkdwn",
            "text": f"*💰 물류 손익*\n{rev_txt}",
        },
    },
    {"type": "divider"},
    # ⑤ Top 품목
    {
        "type": "section",
        "text": {
            "type": "mrkdwn",
            "text": f"*🏷️ 월간 출하 품목 Top (CBM 기준)*\n{item_txt}",
        },
    },
    {"type": "divider"},
    {
        "type": "context",
        "elements": [{
            "type": "mrkdwn",
            "text": "_sincerely-scm-pipeline  |  월간 리포트_",
        }],
    },
]
return blocks
```

# ═══════════════════════════════════════════════════════

# 6. Slack DM 전송

# ═══════════════════════════════════════════════════════

def send_dm(blocks: list[dict], fallback_text: str):
headers = {
“Authorization”: f”Bearer {SLACK_TOKEN}”,
“Content-Type”: “application/json; charset=utf-8”,
}

```
ch_resp = requests.post(
    "https://slack.com/api/conversations.open",
    headers=headers,
    json={"users": DM_USER_ID},
    timeout=15,
).json()

if not ch_resp.get("ok"):
    raise RuntimeError(f"conversations.open 실패: {ch_resp.get('error')}")

channel = ch_resp["channel"]["id"]

msg_resp = requests.post(
    "https://slack.com/api/chat.postMessage",
    headers=headers,
    json={
        "channel":     channel,
        "text":        fallback_text,
        "blocks":      blocks,
        "unfurl_links": False,
    },
    timeout=15,
).json()

if not msg_resp.get("ok"):
    raise RuntimeError(f"chat.postMessage 실패: {msg_resp.get('error')}")

print(f"[OK] Slack 월간 리포트 DM 전송 완료 → {DM_USER_ID}")
```

# ═══════════════════════════════════════════════════════

# 7. 메인

# ═══════════════════════════════════════════════════════

def main():
# 9:00~9:30 랜덤 지연
skip = os.environ.get(“SKIP_DELAY”, “0”)
if skip != “1”:
delay = random.randint(0, 29 * 60)
print(f”[{datetime.now().strftime(’%H:%M:%S’)}] {delay//60}분 {delay%60}초 후 실행”)
time.sleep(delay)

```
print(f"[{datetime.now().strftime('%H:%M:%S')}] 월간 리포트 생성 시작")

start, end = prev_month_range()
print(f"  대상 기간: {start} ~ {end}  ({month_label(start)})")

live_cbm    = fetch_box_cbm_live()
product_cbm = fetch_product_cbm()
records     = fetch_month_shipments(start, end)
print(f"  조회 건수: {len(records)}건")

data   = analyze_month(records, live_cbm, product_cbm)
blocks = build_monthly_blocks(data, start)

fallback = (
    f"📊 SCM 월간 리포트 — {month_label(start)} | "
    f"총 CBM {data['total_cbm']:.1f}m³ / {data['total_count']}건"
)

send_dm(blocks, fallback)

# JSON 아카이브
fname = f"monthly_report_{start.strftime('%Y-%m')}.json"
with open(fname, "w", encoding="utf-8") as fp:
    json.dump(
        {"generated_at": datetime.now().isoformat(), "month": start.isoformat(), **data},
        fp, ensure_ascii=False, indent=2, default=str,
    )
print(f"[OK] {fname} 저장 완료")
print(f"[{datetime.now().strftime('%H:%M:%S')}] 완료")
```

if **name** == “**main**”:
main()