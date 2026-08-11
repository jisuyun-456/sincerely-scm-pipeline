import json, pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "pages"))
import render_weekly_report as R

def test_freeze_load_roundtrip(tmp_path):
    d = {"week_id": "2026-W32", "inbound_count": 247,
         "chart_inbound_by_date": [{"date": "2026-08-03", "cnt": 60}],
         "material_picking_by_purpose": {"조립투입": 320}}
    p = R._write_report_json(d, tmp_path / "2026-W32.json")
    assert p.exists()
    back = R.load_report(p)
    assert back["inbound_count"] == 247
    assert back["chart_inbound_by_date"][0]["cnt"] == 60


FIX = pathlib.Path(__file__).resolve().parents[2] / "history" / "reports" / "2026-W32.json"

def test_render_from_data_divbalanced(tmp_path):
    d = R.load_report(FIX)
    # 프로덕션 템플릿엔 @@SIDEBAR@@ 토큰이 아직 없음(Task 5에서 추가 예정) — head 슬라이스 안에
    # 토큰을 심은 스크래치 사본으로 치환 로직 자체를 지금 검증한다.
    tpl_src = R.TEMPLATE.read_text(encoding="utf-8")
    tpl_src = tpl_src.replace(R.SPLIT_HEAD, "@@SIDEBAR@@\n" + R.SPLIT_HEAD, 1)
    tpl = tmp_path / "tpl.html"
    tpl.write_text(tpl_src, encoding="utf-8")

    html = R.render_from_data(d, sidebar_html="<aside id='sb'></aside>", template_path=tpl)
    assert "2026-W32" in html
    assert "<aside id='sb'>" in html
    assert html.count("<div") == html.count("</div"), "div 불균형"


def test_rebuild_index_and_sidebar(tmp_path):
    for wk, rng in [("2026-W31","2026-07-27 ~ 2026-07-31"), ("2026-W32","2026-08-03 ~ 2026-08-07")]:
        R._write_report_json({"week_id":wk,"week_range":rng,"label":f"{wk[-3:]} ({rng[5:10]}~)",
                              "generated_at":"2026-08-10T00:00:00"}, tmp_path/f"{wk}.json")
    idx = R.rebuild_index(tmp_path)
    assert [e["week_id"] for e in idx] == ["2026-W32","2026-W31"]  # 최신 위
    assert (tmp_path/"index.json").exists()
    sb = R.build_sidebar(idx, "2026-W32")
    assert "W32" in sb and "W31" in sb
    assert "weekly-report-2026-W31.html" in sb   # 링크
    assert sb.count("aria-current") == 1          # 현재 주만 표시
