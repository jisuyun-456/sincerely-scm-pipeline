#!/usr/bin/env python3
"""
WMS Slack 이슈 — 카테고리별 MM번호 직접 조회 보고서
Slack에서 수집된 실제 보고 MM번호만 Airtable에서 조회하여 출력.
"""
import sys, os, time
from datetime import date
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import requests

PAT     = os.environ["AIRTABLE_WMS_PAT"]
BASE_ID = "appLui4ZR5HWcQRri"
TBL_MOV = "tblwq7Kj5Y9nVjlOw"
HDRS    = {"Authorization": f"Bearer {PAT}", "Content-Type": "application/json"}

F_MOV_ID  = "fldOhFtJFBYsxxre7"
F_CREATED = "fldDXUAF4JOORLJ2v"
F_PURPOSE = "fldFRNxG1pNooEOC7"
F_ITEM    = "fldwZKCYZ4IFOigRp"
F_IN_LOC  = "fldCvFgo3U6mdufWB"
F_IN_QTY  = "fldV8kVokQqMIsif0"
F_OUT_MAT = "fldQevLGnuqIuFRVO"

TODAY      = date.today().strftime("%Y%m%d")
TODAY_DASH = date.today().strftime("%Y-%m-%d")
OUT_DIR    = Path("c:/Users/yjisu/Desktop/SCM_WORK/_AutoResearch/SCM/outputs")
LOG_PATH   = Path("c:/Users/yjisu/Desktop/SCM_WORK/_AutoResearch/SCM/wiki/log.md")
OUT_PATH   = OUT_DIR / f"WMS-SlackMM-{TODAY}.md"

# ── 케이스 정의 ────────────────────────────────────────────────────────────────
CASES = [
    {
        "code": "C1",
        "label": "입고자재 공란 / 위치 상이",
        "slack_count": 21,
        "desc": "입하장소 vs 입고자재 위치 불일치, 자재 공란 입력 오류",
        "items": [
            {"date":"2026-01-09","mm":"MM00189501","pna":"PNA37618-YTN",                          "reason":"입고자재 공란 — 생산산출 입고 처리됐으나 어떤 자재가 입고됐는지 미입력, 자재 추적 불가"},
            {"date":"2026-01-09","mm":"MM00190815","pna":"PNA38139-충북자립지원전담기관",         "reason":"입고자재 공란 — 동일하게 자재 필드 미입력, 담당자 확인·수정 요청"},
            {"date":"2026-01-12","mm":"MM00190973","pna":"PNA38334-서울공예박물관",               "reason":"입고자재 공란 — 입고 레코드 생성됐으나 자재 연결 없음"},
            {"date":"2026-01-12","mm":"MM00190938","pna":"PNA37834-삼성서울병원",                 "reason":"입하장소 vs 입고자재 위치 상이 — 입하장소는 신시어리웨일즈로 설정됐으나 자재위치와 불일치, 재고 위치 파악 불가"},
            {"date":"2026-01-15","mm":"MM00192263","pna":"PNA37444-브레인크루",                   "reason":"내부생산 재제작 시 입고자재 반복 누락 — 재제작 진행 시마다 입고자재가 반복적으로 누락됨, 원인 파악 및 납품 전 체크 요청"},
            {"date":"2026-01-19","mm":"MM00191981","pna":"PNA38610-㎝메가터치",                   "reason":"입고자재 공란 — 입하수량 555개 입력됐으나 어떤 자재인지 미입력"},
            {"date":"2026-01-29","mm":"MM00194601","pna":"PNA50137-티르티르",                     "reason":"입고자재 공란 — MROZ 입하 30개 처리됐으나 자재 공란"},
            {"date":"2026-01-29","mm":"MM00194652","pna":"PNA50240-가비아",                       "reason":"입고자재 공란 — 에이원 입하 101개, 자재 필드 미입력"},
            {"date":"2026-01-29","mm":"MM00194966","pna":"PNA50223-에코다",                       "reason":"입고자재 공란 — 에이원 입하 100개, 자재 필드 미입력"},
            {"date":"2026-02-09","mm":"MM00196014","pna":"PNA37761-밀테니바이오텍코리아",         "reason":"입고자재 공란 — 담당자가 직접 발견, 입고자재 공란으로 확인 요청 (fyi 문경선)"},
            {"date":"2026-02-26","mm":"MM00198061","pna":"PNA50517-머스크컨트랙트로지스틱스코리아","reason":"입고자재 공란 — 입고 데이터 중 자재 필드 미입력, 담당자 확인 후 수정 요청"},
            {"date":"2026-02-26","mm":"MM00198264","pna":"PNA50165-오피스넥스",                   "reason":"입고자재 공란 — 동일 배치 점검 시 발견, 수정 요청"},
            {"date":"2026-02-26","mm":"MM00197740","pna":"PNA50588-주식회사디마이너스원",         "reason":"입하장소 vs 자재위치 상이 — 입하장소와 입고자재 위치가 다르게 입력됨, 확인 후 수정 요청"},
            {"date":"2026-03-19","mm":"MM00201674","pna":"PNA50693-삼성전자",                     "reason":"입하장소 vs 자재위치 상이 — 입하장소 MROZ로 설정됐으나 입고자재 위치와 불일치"},
            {"date":"2026-03-19","mm":"MM00198417","pna":"PNA50799-플랜비리서치",                 "reason":"입하장소 에이원이나 입고자재 공란 — 입하장소는 입력됐으나 자재 연결 없음"},
            {"date":"2026-04-08","mm":"MM00204075","pna":"PNA51301-사단법인조정인협회",           "reason":"입고자재 위치 vs 입하장소 상이 — 타우하이텍 입하 82개, 자재 위치 불일치"},
            {"date":"2026-04-08","mm":"MM00204618","pna":"PNA51130-라운비",                       "reason":"입고자재 위치 vs 입하장소 상이 — 피앤더블유인터네셔널 입하 130개, 자재 위치 불일치"},
            {"date":"2026-04-08","mm":"MM00204188","pna":"PNA51205-롯데의료재단",                 "reason":"입하장소 에이원 예정이나 입고자재 공란 — 발주 확인 완료된 건, 입고자재 미입력"},
            {"date":"2026-04-08","mm":"MM00204359","pna":"PNA51287-테스",                         "reason":"입고자재 공란 — 에이원 입하 302개 처리됐으나 자재 미연결"},
            {"date":"2026-04-08","mm":"MM00204915","pna":"PNA51375-무니스",                       "reason":"입고자재 공란 — 에이원 입하 105개, 자재 필드 미입력"},
            {"date":"2026-04-08","mm":"MM00205658","pna":"PNA51330-서울우유협동조합",             "reason":"입고자재 공란 — 에이원 입하 51개, 자재 필드 미입력"},
            {"date":"2026-04-08","mm":"MM00205683","pna":"PNA51453-나이키",                       "reason":"입고자재 공란 — 에이원 입하 122개, 자재 필드 미입력"},
            {"date":"2026-04-08","mm":"MM00205731","pna":"PNA51288-한국디자인진흥원",             "reason":"입고자재 공란 — 에이원 입하 201개, 자재 필드 미입력"},
            {"date":"2026-04-09","mm":"MM00197886","pna":"(PNA미기재)",                           "reason":"입고자재 위치 vs 입하장소 상이 — 베스트원 입하, 자재위치와 입하장소 불일치 (이동목적=재고생산, 690개)"},
            {"date":"2026-04-09","mm":"MM00205770","pna":"PNA51404-어퓨마케팅서비스",             "reason":"입하장소 에이원이나 입고자재 공란 — 에이원 입하 206개, 자재 미연결"},
            {"date":"2026-04-14","mm":"MM00206331","pna":"PNA51431-후지필름",                     "reason":"입하장소 에이원으로 설정됐으나 입고자재 공란 — 에이원 입하 303개"},
            {"date":"2026-04-14","mm":"MM00206720","pna":"PNA51476-대명건설",                     "reason":"입하장소 에이원이나 입고자재 공란 — 에이원 입하 101개 (3건 분할 입고 중 1)"},
            {"date":"2026-04-14","mm":"MM00206721","pna":"PNA51476-대명건설",                     "reason":"입하장소 에이원이나 입고자재 공란 — 에이원 입하 101개 (3건 분할 입고 중 2)"},
            {"date":"2026-04-14","mm":"MM00206722","pna":"PNA51476-대명건설",                     "reason":"입하장소 에이원이나 입고자재 공란 — 에이원 입하 101개 (3건 분할 입고 중 3)"},
            {"date":"2026-04-20","mm":"MM00207739","pna":"PNA51597-하이퍼엑셀",                   "reason":"입하장소 MROZ vs 자재위치 상이 — 입하장소와 입고자재 위치 불일치, 확인·수정 요청"},
            {"date":"2026-04-20","mm":"MM00207314","pna":"PNA51619-더에스엠씨",                   "reason":"입하장소 에이원 설정됐으나 입고자재 공란 — 워터보틀 샘플 건, 자재 미입력"},
            {"date":"2026-04-20","mm":"MM00207124","pna":"PNA51368-아머스포츠코리아",             "reason":"입하장소 에이원이나 입고자재 공란 — 본제작 건, 박스 협력사 납품 후 임가공 예정으로 분할 입고"},
            {"date":"2026-05-06","mm":"MM00209373","pna":"PNA51482-풀무원식품",                   "reason":"입하장소 다영기획 vs 자재위치 상이 — 조립투입 레코드에 입고자재+출고자재 모두 입력된 상태"},
        ],
    },
    {
        "code": "C2",
        "label": "재고생산 / Material 오류",
        "slack_count": 13,
        "desc": "생산산출·조립투입 데이터 오류, 자재 이중 입력, 잘못된 이동목적",
        "items": [
            {"date":"2026-01-22","mm":"MM00193003","pna":"(재고생산)",                    "reason":"재고생산 건 [project] vs [project_name] 필드 상이, status=lost — 물건은 입하됐으나 유효 데이터 여부 불명확, 확인 후 재생성 또는 수정 필요"},
            {"date":"2026-01-22","mm":"MM00191311","pna":"(재고생산)",                    "reason":"재고생산 과업 오류로 재생성 처리 요청 — 기존 데이터 취소 후 올바른 조건으로 과업 재생성"},
            {"date":"2026-03-18","mm":"MM00196323","pna":"PNA50562-NHR(현대모비스)",      "reason":"생산샘플→생산산출 변경 이유 확인 요청 — 생산산출이 맞다면 조립투입까지 생성 필요, 현재 생산샘플로 입고된 것이 맞아 보임"},
            {"date":"2026-03-27","mm":"MM00192235","pna":"PNA50013-현대자동차",           "reason":"현대자동차 건 입고자재 생성 오류 — 오더 수정으로 인해 생성된 MM 데이터 불일치, 1차 레코드"},
            {"date":"2026-03-27","mm":"MM00192236","pna":"PNA50013-현대자동차",           "reason":"현대자동차 건 입고자재 생성 오류 — 오더 수정으로 인해 생성된 MM 데이터 불일치, 2차 레코드"},
            {"date":"2026-03-27","mm":"MM00203536","pna":"PNA51279-LG유플러스",           "reason":"이미 졸업 처리된 파츠 PT4770-단품박스(스탠다드)_화이트가 조립투입으로 생성됨 — 취소 처리 후 올바른 파츠로 재생성 필요"},
            {"date":"2026-04-08","mm":"MM00205269","pna":"PNA51293-FIG",                  "reason":"1개 레코드에 입고자재와 출고자재 모두 입력 — 이동목적 오입력으로 이중 입력 상태, 분리 또는 삭제 후 재생성 필요"},
            {"date":"2026-04-14","mm":"MM00206739","pna":"PNA51286-광화문스퀘어민관합동협의회","reason":"자재 생성 없이 task만 있고 조립투입 데이터 생성 — 산출 데이터 변경 시 조립투입 미연동, 조립투입 레코드 검토 후 수정 필요"},
            {"date":"2026-05-06","mm":"MM00185622","pna":"PNA36271-휴메딕스",             "reason":"2025년 11월 프로젝트 조립투입 레코드에 입고+출고자재 이중 입력 — 발주 후 수정 시 조립투입 데이터 미연동, 이중 입력 제거 후 정합성 확인 필요"},
        ],
    },
    {
        "code": "C3",
        "label": "재고이동 / 전산수량 미반영",
        "slack_count": 12,
        "desc": "이동·출고 후 전산재고 미차감, 발주 vs 입고 수량 불일치",
        "items": [
            {"date":"2026-01-21","mm":"MM00189921","pna":"PNA38303-재단법인한국장기조직기증원","reason":"품절 예정 공지 후 발주 예약 반영으로 재고 소진 — 전산상 오더(150개) vs 조립투입(7개) 불일치로 실재고 잔류, 수량 정합성 확인 필요"},
            {"date":"2026-01-21","mm":"MM00189927","pna":"PNA38303-재단법인한국장기조직기증원","reason":"단품박스 조립투입 수량 불일치 — 품절 공지 이전 입력된 수량과 실제 투입 수량 상이, 조립투입 레코드 수정 필요"},
            {"date":"2026-04-02","mm":None,        "pna":"PT3325-리마커블UV컷솔살균기",        "reason":"전산재고 379개 vs 실재고 약 900개 미반영 — 이전 입고 건이 전산에 미차감된 것으로 추정, 실사 후 ADJUST 처리 필요"},
            {"date":"2026-04-13","mm":None,        "pna":"PT4763/PT4764-파워업PD충전기",       "reason":"파워업PD충전기 본품+박스 결합 입고됐으나 전산/실재고 차이 — 본품(PT4763)과 박스(PT4764) 분리 입고 처리 필요, 현재 전산 미반영"},
            {"date":"2026-04-27","mm":"TO00015690","pna":"(TMS전용)",                          "reason":"재고이동 운송오더 신청됐으나 이동목적=재고이동으로 WMS 입/출고 처리 필요, 전산수량 미반영 — TMS Shipment 테이블 별도 확인"},
            {"date":"2026-04-27","mm":"TO00015657","pna":"(TMS전용)",                          "reason":"재고이동 운송오더 신청됐으나 이동목적=재고이동으로 WMS 입/출고 처리 필요, 전산수량 미반영 — TMS Shipment 테이블 별도 확인"},
        ],
    },
    {
        "code": "C4",
        "label": "가용재고 / 수량 공유",
        "slack_count": 6,
        "desc": "임가공·조립 후 가용재고 수량 공유 및 불량 가능성 안내",
        "items": [
            {"date":"2026-02-27","mm":None,"pna":"PT4730-단품박스(전용)_화이트","reason":"가용재고 365개 공유 안내 — PNA50626/50652/50800 임가공 미완료로 불량 발생 시 추가 소요 가능, 응대 주의 요청"},
            {"date":"2026-03-23","mm":None,"pna":"PT1718-샤슈향(골든벨부)","reason":"PNA50111-도쿠일렉트론코리아 306개 임가공 완료 후 차감 미반영 — 현 가용재고 1,345개로 실제보다 높게 표시됨, 차감 처리 필요"},
        ],
    },
    {
        "code": "C5",
        "label": "아카이브 / 데이터 정합성",
        "slack_count": 5,
        "desc": "아카이브 처리 오류, 취소 후 재고 미정리",
        "items": [
            {"date":"2026-03-18","mm":"MM00191394","pna":"PNA38235-헤이데이","reason":"PNA38235-헤이데이 블랙팟 포함 아카이브 처리됨 — 정상 입고 건이었으나 아카이브 분류로 입고 미반영, 헤이데이 화이트도 동일 오류 확인"},
        ],
    },
    {
        "code": "C6",
        "label": "기타 안내 및 확인 요청",
        "slack_count": 14,
        "desc": "입하예상일 입력 요청, 이동목적 확인, 기타 운영 문의",
        "items": [
            {"date":"2026-04-09","mm":"MM00205502","pna":"PNA51253-에스엔세이프","reason":"입하 예정이나 입하예상일 미입력 — 배송 일정 관리 불가, 담당자에게 입력 요청"},
            {"date":"2026-04-08","mm":"MM00204978","pna":"PNA50484-SK일렉링크","reason":"SK일렉링크 가온팩토리 자재로 조립투입 데이터 생성됨 — 산출데이터 변경 시 조립투입도 함께 확인 필요, 현 데이터 검토 요청"},
            {"date":"2026-04-14","mm":"MM00204817","pna":"PNA50484-SK일렉링크","reason":"SK일렉링크 이동목적 불일치 — 추적 조사 후 이동목적에 맞게 데이터 수정 필요"},
        ],
    },
]


# ── Airtable 페이지네이션 ─────────────────────────────────────────────────────
def paginate(formula: str) -> list[dict]:
    url    = f"https://api.airtable.com/v0/{BASE_ID}/{TBL_MOV}"
    fields = [F_MOV_ID, F_CREATED, F_PURPOSE, F_ITEM, F_IN_LOC, F_IN_QTY, F_OUT_MAT]
    params = {
        "returnFieldsByFieldId": "true",
        "fields[]": fields,
        "filterByFormula": formula,
        "pageSize": 100,
    }
    records = []
    offset  = None
    while True:
        if offset:
            params["offset"] = offset
        resp = requests.get(url, headers=HDRS, params=params)
        resp.raise_for_status()
        data = resp.json()
        records.extend(data.get("records", []))
        offset = data.get("offset")
        if not offset:
            break
        time.sleep(0.2)
    return records


def fetch_mm_records(mm_list: list[str]) -> dict:
    """MM번호 리스트 → {mm_number: fields_dict}"""
    if not mm_list:
        return {}
    CHUNK = 30
    found: dict = {}
    for i in range(0, len(mm_list), CHUNK):
        chunk = mm_list[i:i + CHUNK]
        parts  = [f'{{{F_MOV_ID}}}="{m}"' for m in chunk]
        formula = "OR(" + ",".join(parts) + ")" if len(parts) > 1 else parts[0]
        recs = paginate(formula)
        for r in recs:
            f  = r.get("fields", {})
            mm = f.get(F_MOV_ID, "")
            if mm:
                found[mm] = f
        time.sleep(0.2)
    return found


# ── 보고서 렌더링 ──────────────────────────────────────────────────────────────
def render_item(idx: int, item: dict, found_map: dict) -> tuple[str, str]:
    """(콘솔 라인, 마크다운 라인) 반환"""
    mm     = item.get("mm")
    pna    = item.get("pna", "")
    reason = item.get("reason", "")
    slack_date = item.get("date", "")

    if mm is None:
        console_line = f"  {idx}) {slack_date} / (WMS 레코드 없음) / {pna} / {reason}"
        md_line      = f"| {idx} | {slack_date} | — | {pna} | {reason} | WMS 레코드 없음 |"
        return console_line, md_line

    if mm.startswith("TO"):
        console_line = f"  {idx}) {slack_date} / {mm} / {pna} / {reason}"
        md_line      = f"| {idx} | {slack_date} | {mm} | {pna} | {reason} | TMS전용 — WMS없음 |"
        return console_line, md_line

    rec = found_map.get(mm)
    if rec is None:
        console_line = f"  {idx}) {slack_date} / {mm} / {pna} / {reason}  ← 기간 외 또는 레코드 없음"
        md_line      = f"| {idx} | {slack_date} | {mm} | {pna} | {reason} | ❌ 미조회 |"
        return console_line, md_line

    created  = (rec.get(F_CREATED) or slack_date)[:10]
    purpose  = rec.get(F_PURPOSE) or ""
    location = rec.get(F_IN_LOC)  or ""
    in_qty   = rec.get(F_IN_QTY)  or 0
    out_mat  = rec.get(F_OUT_MAT)  or ""

    detail_parts = []
    if purpose:
        detail_parts.append(f"이동목적={purpose}")
    if location:
        detail_parts.append(f"입하장소={location}")
    if in_qty:
        detail_parts.append(f"입하수량={in_qty:,}")
    if out_mat:
        detail_parts.append("출고자재=있음")
    detail = " | ".join(detail_parts) if detail_parts else "—"

    console_line = f"  {idx}) {created} / {mm} / {pna} / {reason}\n     → {detail}"
    md_line      = f"| {idx} | {created} | {mm} | {pna} | {reason} | {detail} |"
    return console_line, md_line


def build_report(found_map: dict) -> tuple[str, str]:
    console_lines: list[str] = []
    md_lines: list[str]      = []

    for cat in CASES:
        items      = cat["items"]
        mm_count   = sum(1 for it in items if it.get("mm"))
        total_note = f"{len(items)}건 (Slack 보고 {cat['slack_count']}건 기준)"

        console_lines.append(f"\n{'='*60}")
        console_lines.append(f"● {cat['code']}. {cat['label']}")
        console_lines.append(f"  {total_note}")
        console_lines.append(f"  {cat['desc']}")
        console_lines.append("")

        md_lines.append(f"\n## ● {cat['code']}. {cat['label']}")
        md_lines.append(f"> {total_note} | {cat['desc']}\n")
        md_lines.append("| # | 날짜 | MM번호 | PNA | Slack 이슈 | Airtable 확인 |")
        md_lines.append("|---|------|--------|-----|-----------|--------------|")

        for i, item in enumerate(items, 1):
            cline, mline = render_item(i, item, found_map)
            console_lines.append(cline)
            md_lines.append(mline)

    return "\n".join(console_lines), "\n".join(md_lines)


# ── 로그 업데이트 ─────────────────────────────────────────────────────────────
def update_log() -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    entry = f"""## [{TODAY_DASH}] SCM | WMS Slack MM 직접 조회 보고서

**상태:** 완료

### 산출물
- [WMS-SlackMM-{TODAY}.md](../outputs/WMS-SlackMM-{TODAY}.md)

### 요약
- 전체 6개 카테고리 / Slack 71건 기준 MM번호 직접 조회
- C1: 33건 (Slack 21건 / 실제 MM수), C2: 9건, C3: 6건, C4: 2건, C5: 1건, C6: 3건

"""
    if LOG_PATH.exists():
        existing = LOG_PATH.read_text(encoding="utf-8")
        if f"## [{TODAY_DASH}] SCM | WMS Slack MM" in existing:
            print(f"  log.md: 오늘({TODAY_DASH}) 항목 이미 존재 → 스킵", flush=True)
            return
        LOG_PATH.write_text(existing + entry, encoding="utf-8")
    else:
        LOG_PATH.write_text("# WMS AutoResearch — Session Log\n\n" + entry, encoding="utf-8")
    print(f"[log] 업데이트 완료: {LOG_PATH}", flush=True)


# ── 메인 ─────────────────────────────────────────────────────────────────────
def main() -> None:
    print("=" * 60, flush=True)
    print("WMS Slack 이슈 — 카테고리별 MM번호 직접 조회", flush=True)
    print("=" * 60, flush=True)

    all_mm = [
        it["mm"] for cat in CASES for it in cat["items"]
        if it.get("mm") and it["mm"].startswith("MM")
    ]
    all_mm = list(dict.fromkeys(all_mm))  # dedup, preserve order
    print(f"[fetch] 조회 대상 MM번호: {len(all_mm)}개", flush=True)

    found_map = fetch_mm_records(all_mm)
    print(f"[fetch] Airtable 조회 결과: {len(found_map)}개 매칭", flush=True)

    console_out, md_out = build_report(found_map)
    print(console_out, flush=True)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    header = f"""# WMS Slack 이슈 — 카테고리별 MM번호 직접 조회

> 분석일: {TODAY_DASH}  |  Slack 채널: #scm_팀_재고관리  |  기간: 2026-01-01 ~ 2026-05-08
> 방법: Slack 보고 MM번호 직접 수집 → Airtable Movement 레코드 직접 조회 (전수 스캔 아님)

"""
    OUT_PATH.write_text(header + md_out, encoding="utf-8")
    print(f"\n[report] 저장 완료: {OUT_PATH}", flush=True)

    update_log()
    print("=" * 60, flush=True)


if __name__ == "__main__":
    main()
