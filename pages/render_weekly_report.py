# -*- coding: utf-8 -*-
"""
render_weekly_report.py
────────────────────────────────────────────────────────────────────────────────
주간 리포트(크림+클레이) 데이터 주도 렌더러.  [chain: pages-weekly-report-port P3]

전략 (P2/P3):
  · 크림 템플릿(WeeklyReport-물류파트-2026-W32-cream.html)을 HEAD / MIDDLE / TAIL 로 분할.
  · HEAD  = <style> + 프레임워크 + Ⅰ 전환 KPI  → 반정적(전환 KPI 값만 치환), 디자인 100% 보존.
  · MIDDLE = Ⅱ 운영 KPI(6 차트 + 20 스냅샷 카드) → weekly_report_data.compute() 로 **완전 생성**.
  · TAIL  = 카드 상세 모달 <script> → 참조 드릴다운(정적, W31 기준). data-modal 키는 카드가 그대로 유지.

출력: docs/weekly-report.html  (Pages 파이프라인 배포 대상)
실행: python pages/render_weekly_report.py 2026-W31 [out.html]
"""
import re
import sys
import json
import pathlib
import datetime
from collections import Counter
from datetime import date, timedelta


def _default_week():
    """인자 없이 실행 시 직전 ISO 주(월~금) — deploy_pages weekly_review 케이던스."""
    today = date.today()
    prev_mon = today - timedelta(days=today.weekday() + 7)
    y, w, _ = prev_mon.isocalendar()
    return f"{y}-W{w:02d}"

_PAGES = pathlib.Path(__file__).resolve().parent
if str(_PAGES) not in sys.path:
    sys.path.insert(0, str(_PAGES))
from weekly_report_data import compute  # noqa: E402

ROOT = _PAGES.parent
# 템플릿은 pages/ 아래 추적 파일로 보관 (_AutoResearch/**/outputs/ 는 .gitignore → CI 미포함).
TEMPLATE = _PAGES / "weekly_report.template.html"
DEFAULT_OUT = ROOT / "docs" / "weekly-report.html"
REPORTS_DIR = ROOT / "history" / "reports"

SPLIT_HEAD = '  <!-- ===================== Ⅱ 운영 KPI ===================== -->'
SPLIT_TAIL = '<!-- ===================== 카드 상세 모달 ===================== -->'

WD_KR = {"월": "월", "화": "화", "수": "수", "목": "목", "금": "금"}


# ── HTML emit 헬퍼 ────────────────────────────────────────────────────────────
def _esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# ── 주간 리포트 데이터 freeze/load 헬퍼 ───────────────────────────────────────
def _jsonable(o):
    if isinstance(o, dict):
        return {k: _jsonable(v) for k, v in o.items()}
    if isinstance(o, Counter):
        return {k: _jsonable(v) for k, v in o.items()}
    if isinstance(o, (list, tuple, set)):
        return [_jsonable(v) for v in o]
    if isinstance(o, (datetime.date, datetime.datetime)):
        return o.isoformat()
    return o


def _write_report_json(d, path):
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_jsonable(d), ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def load_report(path):
    return json.loads(pathlib.Path(path).read_text(encoding="utf-8"))


def freeze_week(week_id, reports_dir=REPORTS_DIR):
    d = compute(week_id)
    d["generated_at"] = datetime.datetime.now().isoformat(timespec="seconds")
    return _write_report_json(d, pathlib.Path(reports_dir) / f"{week_id}.json")


def vbar_chart(title, sub, items, val_key, fmt, dim_below=None):
    """세로 막대 차트 (일별 입고 건수 / 일별 출고 CBM)."""
    vals = [it[val_key] for it in items] or [0]
    mx = max(vals) or 1
    cols, xs = [], []
    for it in items:
        v = it[val_key]
        h = max(3, round(v / mx * 100))
        dim = " dim" if (dim_below is not None and v < dim_below) else ""
        cols.append(f'<div class="bar-col"><div class="bar{dim}" style="height:{h}%"><span class="bv">{fmt(v)}</span></div></div>')
        xs.append(f'<span class="bar-xl">{it["date"][-2:]}</span>')
    return (
        f'        <div class="ch">\n'
        f'          <div class="ch-head"><div><p class="ch-title">{title}</p><p class="ch-sub">{sub}</p></div><span class="pill good">실측</span></div>\n'
        f'          <div class="bars">\n            ' + "\n            ".join(cols) + '\n          </div>\n'
        f'          <div class="bar-x">' + "".join(xs) + '</div>\n'
        f'        </div>'
    )


def hbar_chart(title, sub, rows):
    """가로 막대 차트. rows = [(label, value_number, display_str, dim_bool)]."""
    nums = [r[1] for r in rows if r[1] > 0] or [1]
    mx = max(nums) or 1
    out = []
    for label, num, disp, dim in rows:
        if dim or num <= 0:
            out.append(f'<div class="hbar-row"><span class="hbar-label">{_esc(label)}</span>'
                       f'<div class="hbar-track"><div class="hbar-fill dim" style="width:2%"></div></div>'
                       f'<span class="hbar-val mut">{_esc(disp)}</span></div>')
        else:
            w = round(num / mx * 100, 1)
            out.append(f'<div class="hbar-row"><span class="hbar-label">{_esc(label)}</span>'
                       f'<div class="hbar-track"><div class="hbar-fill" style="width:{w}%"></div></div>'
                       f'<span class="hbar-val">{_esc(disp)}</span></div>')
    return (
        f'        <div class="ch">\n'
        f'          <div class="ch-head"><div><p class="ch-title">{title}</p><p class="ch-sub">{sub}</p></div><span class="pill good">실측</span></div>\n'
        f'          <div class="hbars">\n            ' + "\n            ".join(out) + '\n          </div>\n'
        f'        </div>'
    )


def card(modal, title, pill, val_html, bench, src, pill_cls="good"):
    return (
        f'        <div class="kpi tappable" data-modal="{modal}" tabindex="0" role="button" aria-label="{_esc(title)} 상세 보기">\n'
        f'          <span class="tap-hint">＋</span>\n'
        f'          <div class="k-top"><span class="k-title">{_esc(title)}</span><span class="pill {pill_cls}">{pill}</span></div>\n'
        f'          <div class="k-val">{val_html}</div>\n'
        f'          <div class="k-bench">{_esc(bench)}</div>\n'
        f'          <div class="k-src">{_esc(src)}</div>\n'
        f'        </div>'
    )


def kpi_grid(cards):
    return '      <div class="kpi-grid">\n' + "\n".join(cards) + '\n      </div>'


def grp_tag(text, style):
    return f'      <span class="grp-tag" style="{style}">{_esc(text)}</span>'


# ── 미입하 협력사 캡션 ────────────────────────────────────────────────────────
def _noarrive_caption(by_sup):
    top = by_sup[:3]
    rest = sum(n for _, n in by_sup[3:])
    parts = [f"{_short_sup(s)} {n}" for s, n in top]
    if rest:
        parts.append(f"외 {rest}")
    return " · ".join(parts)


def _short_sup(s):
    s = s.strip('"').strip()
    return s.split()[0][:12] if s else "미기재"


def build_operational_section(d):
    """Ⅱ 운영 KPI 섹션 전체를 compute() dict 로부터 생성."""
    parts = [
        '  <!-- ===================== Ⅱ 운영 KPI ===================== -->',
        '  <section>',
        '    <div class="sec-head">',
        '      <span class="sec-num">Ⅱ</span>',
        '      <h2>운영 KPI</h2>',
        '      <span class="sec-tag lag">래깅 지표</span>',
        '    </div>',
        '',
        '    <!-- A. 추이 · 구성 그래프 -->',
        '    <div class="op-block">',
        f'      <div class="sub-head"><span class="sh-icon">📊</span>추이 · 구성 <span class="sh-hint">— 패턴이 정보인 지표 · {d["week_id"]} 실측</span></div>',
        '      <div class="chart-grid">',
        '',
    ]

    # 차트 1: 일별 입고 건수
    ib = d["chart_inbound_by_date"]
    parts.append(vbar_chart("일별 입고 건수", f'합계 {d["inbound_count"]}건 · {d["week_range"]}',
                            ib, "cnt", lambda v: f"{v}"))
    parts.append('')
    # 차트 2: 일별 출고 CBM
    ob = d["chart_outbound_cbm_by_date"]
    parts.append(vbar_chart("일별 출고 CBM (m³)", f'주간 Total {d["weekly_cbm"]} m³ · 회색=CBM 미입력',
                            ob, "cbm", lambda v: f"{v:.2f}".rstrip("0").rstrip(".") if v else "0", dim_below=1.0))
    parts.append('')
    # 차트 3: 입고 목적별
    pr = [(x["purpose"], x["cnt"], f'{x["cnt"]}건', False) for x in d["chart_inbound_by_purpose"]]
    parts.append(hbar_chart("입고 목적별 구성", f'총 {d["inbound_count"]}건 · 수량 {d["inbound_total_qty"]:,} ea', pr))
    parts.append('')
    # 차트 4: CBM 채널별
    ch = [(c["name"], c["cbm"], f'{c["cbm"]}m³' if c["cbm"] > 0 else "미기재", c["cbm"] <= 0)
          for c in d["chart_cbm_by_channel"]]
    parts.append(hbar_chart("CBM 채널별 구성", f'주간 Total {d["weekly_cbm"]} m³ · {d["outbound_count"]}건 · Shipment 배송파트너 기준', ch))
    parts.append('')
    # 차트 5: 배송방식별
    mt = [(m["method"], m["cbm"], f'{m["cbm"]}m³', False) for m in d["chart_by_method"]]
    parts.append(hbar_chart("배송방식별 구성", f'{d["outbound_count"]}건 기준 · 협력사는 파트너명 우선 분류', mt))
    parts.append('')
    # 차트 6: 기사별 이용률
    du = [(x["driver"], x["pct"], f'{x["pct"]}%', False) for x in d["chart_driver_util"]] or [("—", 0, "무배차", True)]
    parts.append(hbar_chart("기사별 차량이용률(%)", f'배차일지 median · {d["week_id"]} 실측', du))
    parts.extend(['', '      </div>', '    </div>', ''])

    # B. 스냅샷 카드
    parts.append('    <!-- B. 스냅샷 카드 -->')
    parts.append('    <div class="op-block">')
    parts.append('      <div class="sub-head"><span class="sh-icon">🔢</span>스냅샷 지표 <span class="sh-hint">— 대표 수치·상태로 충분한 지표</span></div>')

    # 입고 그룹
    parts.append(grp_tag(f"📥 입고 · Inbound / Receiving ({d['week_id']} 실측)",
                         "background:var(--info-bg);color:var(--info)"))
    pk = d["material_picking_by_purpose"]
    parts.append(kpi_grid([
        card("ingo", "입고 건수", "실측", f'{d["inbound_count"]}<small>건</small>',
             f'입하완료 {d["inbound_completed"]} / 미확인 {d["inbound_unconfirmed"]} · 완료율 {d["inbound_completion_rate"]}%', "WMS movement"),
        card("noarrive", "미입하 발생", "실측", f'{d["no_arrival_count"]}<small>건</small>',
             _noarrive_caption(d["no_arrival_by_supplier"]), "협력사별"),
        card("dts", "Dock-to-Stock", "실측", f'{d["dts_avg_min"]}<small>분 평균</small>',
             f'중앙값 {d["dts_median_min"]}분 · 목표(≤480분) 달성 {d["dts_target_pct"]}%({d["dts_within_target"]}/{d["dts_count"]})',
             f'IBSA sync_movement {d["dts_count"]}건 · WERC ★'),
        card("ontime", "공급사 납기 준수율", "실측", f'{d["supplier_ontime_pct"]}<small>%</small>',
             f'정시 {d["supplier_ontime"]}건 · 지연 {d["supplier_late"]}건 · 평균 {d["supplier_avg_diff_days"]}일',
             f'WMS movement 입하예상일 vs 실제입하일 {d["supplier_total"]}건'),
    ]))

    # 검수 그룹
    parts.append(grp_tag("🔎 검수 · Inspection / QC (최근 90일 실측)",
                         "background:var(--proxy-bg);color:var(--proxy);margin-top:20px"))
    parts.append(kpi_grid([
        card("qc", "QC 불합격률", "실측", f'{d["qc_fail_rate"]}<small>%</small>',
             f'품질이슈 {d["qc_quality_issue_cnt"]} / {d["inbound_count"]} · 이슈카테고리 실측', f'movement 이슈카테고리 · {d["week_id"]}'),
        card("fpy", "1차 합격률 (FPY)", "실측 NEW", f'{d["fpy_pct"]}<small>%</small>',
             f'합격 {d["fpy_pass"]} / 검수 {d["fpy_total"]}건', "IBSA 표본검수결과 · WERC ★"),
        card("aql", "AQL 샘플링 합격률", "실측 NEW", f'{d["aql_pct"]}<small>%</small>',
             f'미해결 이슈 {d["aql_unresolved"]}건 · 샘플링불합격 {d["aql_sample_fail"]} · {d["fpy_total"]}건', "IBSA 표본검수 품질 판정 · WERC ★"),
        card("insptime", "검수 처리시간", "실측 NEW", f'{d["inspect_time_median_min"]}<small>분 중앙값</small>',
             f'평균 {d["inspect_time_mean_min"]}분 · p90 {d["inspect_time_p90_min"]}분 · {d["inspect_time_count"]}건', "IBSA 입하완료→시안검수완료"),
    ]))

    # 자재 그룹
    parts.append(grp_tag(f"📦 자재 · Materials ({d['week_id']} 실측)",
                         "background:var(--lead-bg);color:var(--lead);margin-top:20px"))
    parts.append(kpi_grid([
        card("pick", "자재 피킹수", "실측", f'{d["material_picking_count"]}<small>건</small>',
             f'조립 {pk.get("조립투입", 0)} · 생산 {pk.get("생산투입", 0)} · 취소 {d["material_picking_cancelled"]} 제외(매칭 {d["material_picking_matched"]})',
             "조립·생산투입 ∩ 에이원/PNA"),
    ]))

    # 출하 그룹
    parts.append(grp_tag("🚚 출하 · Outbound / Shipping", "background:var(--good-bg);color:var(--good);margin-top:20px"))
    per_order_man = round(d["ship_cost_per_order_median"] / 10000, 1) if d["ship_cost_per_order_median"] else 0
    parts.append(kpi_grid([
        card("chulgo", "출고 건수", "실측", f'{d["outbound_count"]}<small>건</small>',
             f'출하확정 · 주간 Total_CBM {d["weekly_cbm"]} m³', f'TMS Shipment · {d["week_id"]}'),
        card("warehouse", "창고 가동율", "하한", f'{d["warehouse_util_pct"]}<small>%</small>',
             '주간 CBM ÷ 44.4 m³ · CBM 미입력 다수', "Total_CBM 기준", pill_cls="low"),
        card("shipcost", "출하 단가", "실측 NEW", f'{per_order_man}<small>만원/오더</small>',
             f'CBM당 {d["ship_cost_per_cbm_median"]:,}원/㎥ · 최근 30일 {d["ship_cost_count"]}건', "TMS 물류비(합계) · WERC ★"),
        card("cycletime", "오더 사이클타임", "실측 NEW", f'{d["order_cycle_median_days"]}<small>일 중앙값</small>',
             f'발주신청~최종출고 · p25 {d["order_cycle_p25_days"]:.0f} · p75 {d["order_cycle_p75_days"]:.0f}일',
             f'order {d["order_cycle_count"]:,}건 · 최근 90일 · WERC ★'),
        card("otif", "OTIF On-Time", "실측", f'{d["otif_ontime_pct"]}<small>%</small>',
             '벤치 ≥90% · 자동충족', f'OTIF {d["otif_total"]:,}건 · WERC ★'),
        card("infull", "In-Full", "실측", f'{d["otif_infull_pct"]}<small>%</small>', '벤치 ≥95%', "OTIF"),
        card("promise", "약속납기 전환율", "실측", f'{d["promise_conversion_pct"]}<small>%</small>',
             f'평균 납기차이 {d["promise_avg_delay_days"]}일', "OTIF"),
        card("claim", "배송 클레임 (90일)", "실측", f'{d["claim_count"]}<small>건</small>',
             f'미처리 {d["claim_open"]} · 90일 롤링(갱신)', "클레임 롤링"),
        card("forecast", "다음주 볼륨 예측", "실측", f'{d["forecast_count"]}<small>건 · {d["forecast_cbm"]}m³</small>',
             f'피크 {d.get("forecast_peak_day","-")}요일 · {d.get("forecast_data_weeks","-")}주 패턴', "Iter5 · CBM 이상치 제외"),
    ]))

    parts.extend(['    </div>', '  </section>'])
    return "\n".join(parts)


def _hydrate_conversion(head, d):
    """HEAD(전환 KPI) 값을 CONVERSION_KPI 로 치환 (반정적 → 데이터 주도)."""
    c = d["conversion_kpi"]
    repl = {
        "81.2%": f'{c["cbm_completeness_pct"]}%',
        "(1,335 / 1,645)": f'({c["cbm_complete"]:,} / {c["cbm_total"]:,})',
        "310건": f'{c["cbm_pending"]}건',
    }
    for a, b in repl.items():
        head = head.replace(a, b, 1)
    return head


def render_from_data(d, sidebar_html="", template_path=TEMPLATE, out_path=None):
    src = pathlib.Path(template_path).read_text(encoding="utf-8")
    i1 = src.index(SPLIT_HEAD); i2 = src.index(SPLIT_TAIL)
    head, tail = src[:i1], src[i2:]
    wk = d["week_id"]
    head = re.sub(r'Weekly Report — 2026-W\d+', f'Weekly Report — {wk}', head)
    head = _hydrate_conversion(head, d)
    head = head.replace("@@SIDEBAR@@", sidebar_html)
    middle = build_operational_section(d)
    out = head + middle + "\n\n</div>\n\n" + tail
    if out_path:
        outp = pathlib.Path(out_path); outp.parent.mkdir(parents=True, exist_ok=True)
        outp.write_text(out, encoding="utf-8")
    return out


def render(week_id, template_path=TEMPLATE, out_path=DEFAULT_OUT):
    """단일 주 편의 래퍼: compute→freeze→render_from_data (사이드바 없음)."""
    freeze_week(week_id)
    d = load_report(REPORTS_DIR / f"{week_id}.json")
    return render_from_data(d, template_path=template_path, out_path=out_path)


def rebuild_index(reports_dir=REPORTS_DIR):
    reports_dir = pathlib.Path(reports_dir); entries = []
    for p in reports_dir.glob("*.json"):
        if p.name == "index.json": continue
        d = load_report(p)
        entries.append({"week_id": d["week_id"], "label": d.get("label", d["week_id"]),
                        "range": d.get("week_range",""), "file": f"weekly-report-{d['week_id']}.html",
                        "generated_at": d.get("generated_at","")})
    entries.sort(key=lambda e: e["week_id"], reverse=True)
    (reports_dir / "index.json").write_text(
        json.dumps({"reports": entries}, ensure_ascii=False, indent=2), encoding="utf-8")
    return entries


def build_sidebar(index, current_week):
    rows = []
    for e in index:
        cur = ' aria-current="page" class="wk-item active"' if e["week_id"] == current_week else ' class="wk-item"'
        rows.append(f'<a href="{e["file"]}"{cur}><span class="wk-key">{_esc(e["label"])}</span>'
                    f'<span class="wk-range">{_esc(e["range"])}</span></a>')
    return ('<aside class="sidebar">\n  <div class="sb-head">주차 이력</div>\n  <nav class="wk-list">\n    '
            + "\n    ".join(rows) + '\n  </nav>\n</aside>')


if __name__ == "__main__":
    wk = sys.argv[1] if len(sys.argv) > 1 else _default_week()
    outp = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_OUT
    render(wk, out_path=outp)
