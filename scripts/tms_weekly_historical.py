"""
tms_weekly_historical.py
──────────────────────────────────────────────────────────────────────────
1회성 유틸리티: CI가 리포트를 생성하지 못한 과거 주(W32, W33)의 헤드라인
KPI를 현재 Airtable 데이터에서 날짜 범위 필터로 재구성한다.
tms_weekly_runner.py의 "최근 30일" 롤링 윈도우 대신 명시적 (start, end)
윈도우를 쓴다는 점만 다르다. 읽기 전용 — patch_records 호출 없음.

사용법:
  python scripts/tms_weekly_historical.py
"""
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.tms_weekly_runner import (  # noqa: E402
    get_all_records, classify_partner, TBL_SHIPMENT, TBL_DISPATCH,
    TBL_OTIF, TBL_PARTNER,
)
from utils.vehicle_util import summarize_util  # noqa: E402

OUTPUTS_DIR = ROOT / "_AutoResearch" / "SCM" / "outputs"


def _first(v):
    """OTIF.약속납기일(fldtUxptEKXh7Nz8z)은 formula 필드지만 API가 list-wrap해서
    반환 — 다른 필드와 달리 첫 값을 꺼내야 문자열 날짜 비교가 가능하다."""
    if isinstance(v, list):
        return v[0] if v else None
    return v


_KR_DATE = re.compile(r"^(\d+)년\s*(\d+)월\s*(\d+)일$")


def _to_iso(v):
    """Shipment.출하일자(fldtEykbFxkO31FZP)는 'YYYY년 M월 D일' 한국어 형식으로
    반환됨(다른 날짜 필드와 달리 ISO가 아님) — ISO 범위 비교를 위해 변환한다.
    극소수(10056건 중 14건) 레코드는 formula 계산 오류로 {'error': '#ERROR!'}
    dict를 반환 — 날짜 매칭 불가로 취급해 건너뛴다."""
    if not v or not isinstance(v, str):
        return ""
    m = _KR_DATE.match(v)
    if not m:
        return v  # 이미 ISO 형식이면 그대로 통과
    y, mo, d = m.groups()
    return f"{int(y):04d}-{int(mo):02d}-{int(d):02d}"


def compute_week_kpis(start: date, end: date, week_label: str) -> dict:
    lo, hi = start.isoformat(), end.isoformat()

    # ── Shipment (볼륨 + 약속납기일 전환율) ──────────────────────────────
    ship_recs = get_all_records(TBL_SHIPMENT, [
        "fldQvmEwwzvQW95h9",  # 출하확정일
        "fldyYIfBhhu7sEX1P",  # 약속납기일
    ])
    week_ships = [
        r for r in ship_recs
        if lo <= (r["fields"].get("fldQvmEwwzvQW95h9") or "") <= hi
    ]
    proxy_count = sum(
        1 for r in week_ships
        if (r["fields"].get("fldyYIfBhhu7sEX1P") or "") ==
           (r["fields"].get("fldQvmEwwzvQW95h9") or "X")
    )
    promised_conversion_rate = round(
        (1 - proxy_count / max(len(week_ships), 1)) * 100, 1
    )

    # ── 퀵(수도권) 내부 소화율 ────────────────────────────────────────────
    partner_recs = get_all_records(TBL_PARTNER, ["fldUCl2kD890FqRkt"])
    partner_cache = {r["id"]: r["fields"].get("fldUCl2kD890FqRkt", "") for r in partner_recs}

    # tms_weekly_runner.py의 "최근 30일" 롤링 윈도우와 달리 임의의 과거 주를
    # 조회하므로 max_records=300 cap을 두지 않는다 — Airtable 기본 정렬은
    # 최신순이 아니라서 300건 cap 시 목표 주간 레코드가 잘려나갈 수 있음
    # (실측: 전체 10,056건 중 상위 300건에 2026-08 레코드 없음).
    quik_all = get_all_records(
        TBL_SHIPMENT,
        fields=["fldM2u6RwLRrO7ymW", "fldtEykbFxkO31FZP"],  # 배송파트너, 출하일자
        formula="FIND('퀵(수도권)', {배송 방식}) > 0",
    )
    week_quik = [
        r for r in quik_all
        if lo <= _to_iso(r["fields"].get("fldtEykbFxkO31FZP")) <= hi
    ]
    cat = {"internal": 0, "gogox": 0, "external": 0, "none": 0}
    for r in week_quik:
        partners = r["fields"].get("fldM2u6RwLRrO7ymW") or []
        if not partners:
            cat["none"] += 1
            continue
        cat[classify_partner(partner_cache.get(partners[0], ""))] += 1
    total_quik = sum(cat.values()) or 1

    # ── 차량 적재율 (배차일지) ────────────────────────────────────────────
    disp_recs = get_all_records(TBL_DISPATCH, [
        "fldZh2mZDIPQXfOcO",  # 날짜
        "fldyQAoRZFn6oeQ0E",  # 차량이용률(%)
    ])
    week_disp = [
        r for r in disp_recs
        if lo <= (r["fields"].get("fldZh2mZDIPQXfOcO") or "") <= hi
    ]
    util_stats = summarize_util([r["fields"].get("fldyQAoRZFn6oeQ0E") for r in week_disp])

    # ── OTIF (약속납기일 기준 필터) ───────────────────────────────────────
    otif_recs = get_all_records(TBL_OTIF, [
        "fldoUQOue0umGJ2xk",  # On_Time
        "fldiFhyU1k9YsnoGh",  # In_Full
        "fldtUxptEKXh7Nz8z",  # 약속납기일
    ])
    week_otif = [
        r for r in otif_recs
        if lo <= (_first(r["fields"].get("fldtUxptEKXh7Nz8z")) or "") <= hi
    ]
    on_time = sum(1 for r in week_otif if str(r["fields"].get("fldoUQOue0umGJ2xk")).lower() in ("true", "1"))
    in_full = sum(1 for r in week_otif if str(r["fields"].get("fldiFhyU1k9YsnoGh")).lower() in ("true", "1"))
    total_otif = len(week_otif) or 1

    return {
        "week_label": week_label,
        "date_range": f"{start.strftime('%m/%d')}~{end.strftime('%m/%d')}",
        "total_shipments": len(week_ships),
        "internal_rate": round(cat["internal"] / total_quik * 100, 1),
        "gogox_rate": round(cat["gogox"] / total_quik * 100, 1),
        "external_rate": round(cat["external"] / total_quik * 100, 1),
        "on_time_rate": round(on_time / total_otif * 100, 1),
        "in_full_rate": round(in_full / total_otif * 100, 1),
        "util_median": util_stats["median"] if util_stats["n_loaded"] else None,
        "n_loaded": util_stats["n_loaded"],
        "promised_conversion_rate": promised_conversion_rate,
        "otif_n": len(week_otif),
    }


def _parse_saved_report(path: Path, week_label: str, date_range: str) -> dict:
    """CI가 리포트를 생성했던 주(W31, W34)는 재조회 대신 저장된 .md에서
    파싱 — tms_weekly_runner._load_prior_kpis와 동일한 정규식 패턴을 사용."""
    text = path.read_text(encoding="utf-8")

    def _pct(pattern):
        m = re.search(pattern, text)
        return float(m.group(1)) if m else None

    m_ships = re.search(r"분석 대상:\s*(\d+)건", text)
    m_util = re.search(r"적재율 median.*?\*\*([\d.]+)%\*\*", text)
    return {
        "week_label": week_label,
        "date_range": date_range,
        "total_shipments": int(m_ships.group(1)) if m_ships else None,
        "internal_rate": _pct(r"내부 소화율.*?\|\s*([\d.]+)%"),
        "gogox_rate": _pct(r"고고엑스 비중:\s*([\d.]+)%"),
        "on_time_rate": _pct(r"OTIF On-Time율.*?\|\s*([\d.]+)%"),
        "in_full_rate": _pct(r"In-Full율.*?\|\s*([\d.]+)%"),
        "util_median": m_util and float(m_util.group(1)),
        "promised_conversion_rate": _pct(r"약속납기일 실측 전환율.*?\|\s*([\d.]+)%"),
    }


def _row(k: dict) -> str:
    util = f"{k['util_median']}%" if k["util_median"] is not None else "N/A"
    ships = k["total_shipments"] if k["total_shipments"] is not None else "N/A"
    return (
        f"| {k['week_label']} ({k['date_range']}) | {ships}건 | "
        f"{k['internal_rate']}% | {k['gogox_rate']}% | {k['on_time_rate']}% | "
        f"{k['in_full_rate']}% | {util} | {k['promised_conversion_rate']}% |"
    )


def build_comparison(weeks: list[dict]) -> str:
    header = (
        "# TMS 주간 KPI 비교 — W31~W34\n\n"
        f"> 자동 생성: {date.today().isoformat()} | "
        "W32·W33은 CI 실패로 당시 리포트 미생성 — 현재 Airtable 데이터를 "
        "해당 주 날짜범위로 재조회해 재구성한 값 (아래 '주의' 참고)\n\n"
        "---\n\n"
        "| 주차 | 총 볼륨 | 내부 소화율 | 고고엑스 | OTIF On-Time | In-Full | "
        "차량적재율 median | 약속납기 전환율 |\n"
        "|---|---|---|---|---|---|---|---|\n"
    )
    rows = "\n".join(_row(k) for k in weeks)
    footer = (
        "\n\n---\n\n"
        "## 주의사항 (재구성 데이터 한계)\n\n"
        "- **W32·W33**: 당시 CI가 리포트를 생성하지 못해 로그·리포트가 존재하지 않았음. "
        "이번에 현재 Airtable 상태를 해당 주 날짜범위로 필터링해 재구성한 값 — "
        "Immutable Ledger 원칙상 과거 레코드는 보존되어 있으나, 사후 보정 레코드가 "
        "있었다면 당시 실측치와 미세하게 다를 수 있음.\n"
        "- **차량한도**는 재구성/원본 리포트 공통으로 *현재* 라이브 값을 사용 — "
        "W31 시점 차량한도가 달랐다면 W31 적재율 median은 당시 실제값과 다를 수 있음.\n"
        "- W31·W34는 기존 저장된 리포트에서 파싱한 값 (재조회 아님).\n"
        "- **측정 구간 불일치**: W31·W34의 모든 지표(내부 소화율, 고고엑스, OTIF, "
        "적재율 median, 약속납기 전환율 포함)는 최근 30일 롤링 집계 시점 스냅샷이며, "
        "W32·W33의 정확한 5영업일 집계와 직접 비교 불가 — "
        "이 표만으로 4주간 주간 단위 트렌드를 판단하지 말 것.\n"
    )
    return header + rows + footer


if __name__ == "__main__":
    w31 = _parse_saved_report(OUTPUTS_DIR / "TMS-2026-W31.md", "2026-W31", "07/28~08/01")
    w32 = compute_week_kpis(date(2026, 8, 3), date(2026, 8, 7), "2026-W32")
    w33 = compute_week_kpis(date(2026, 8, 10), date(2026, 8, 14), "2026-W33")
    w34 = _parse_saved_report(OUTPUTS_DIR / "TMS-2026-W34.md", "2026-W34", "08/17~08/21")

    report = build_comparison([w31, w32, w33, w34])
    out_path = OUTPUTS_DIR / "TMS-Comparison-W31-W34.md"
    out_path.write_text(report, encoding="utf-8")
    print(f"저장: {out_path}")
