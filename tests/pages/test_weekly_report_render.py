import json, pathlib, shutil, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "pages"))
import render_weekly_report as R

SEED_DIR = pathlib.Path(__file__).resolve().parents[2] / "history" / "reports"
SEED_WEEKS = ["2026-W31", "2026-W32"]


def _copy_seeds(dest_dir):
    dest_dir.mkdir(parents=True, exist_ok=True)
    for wk in SEED_WEEKS:
        shutil.copy(SEED_DIR / f"{wk}.json", dest_dir / f"{wk}.json")
    return dest_dir

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

def test_render_from_data_divbalanced():
    # 프로덕션 템플릿에 @@SIDEBAR@@ 토큰이 실재(Task 5) — 실제 기본 TEMPLATE 대상으로 검증.
    d = R.load_report(FIX)
    html = R.render_from_data(d, sidebar_html="<aside id='sb'></aside>")
    assert "2026-W32" in html
    assert "<aside id='sb'>" in html
    assert html.count("<div") == html.count("</div"), "div 불균형"


def test_template_two_column_layout(tmp_path):
    d = R.load_report(FIX)
    reports_dir = _copy_seeds(tmp_path / "reports")
    idx = R.rebuild_index(reports_dir)   # 시드 W31·W32 (격리된 tmp_path)
    html = R.render_from_data(d, R.build_sidebar(idx, "2026-W32"))
    assert 'class="layout"' in html
    assert 'class="sidebar"' in html
    assert "weekly-report-2026-W31.html" in html   # 사이드바 실제 주입
    assert html.count("<div") == html.count("</div")


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


def test_render_all_archive(tmp_path):
    reports_dir = _copy_seeds(tmp_path / "reports")
    out_dir = tmp_path / "out"
    weeks = R.render_all_archive(reports_dir=reports_dir, out_dir=out_dir)   # 시드 W31·W32 (격리된 tmp_path)
    assert set(weeks) == {"2026-W31","2026-W32"}
    assert (out_dir/"weekly-report-2026-W31.html").exists()
    assert (out_dir/"weekly-report-2026-W32.html").exists()
    idx_html = (out_dir/"index.html").read_text(encoding="utf-8")
    assert "2026-W32" in idx_html and 'class="sidebar"' in idx_html   # index=최신+사이드바


def test_render_all_archive_skips_bad_json(tmp_path):
    reports_dir = _copy_seeds(tmp_path / "reports")
    (reports_dir / "2026-W99.json").write_text("{bad", encoding="utf-8")
    out_dir = tmp_path / "out"
    weeks = R.render_all_archive(reports_dir=reports_dir, out_dir=out_dir)
    assert set(weeks) == {"2026-W31","2026-W32"}   # W99 skipped, not raised
    assert (out_dir/"weekly-report-2026-W31.html").exists()
    assert (out_dir/"weekly-report-2026-W32.html").exists()
    assert not (out_dir/"weekly-report-2026-W99.html").exists()


def test_render_all_archive_latest_render_fail_falls_back(tmp_path):
    # W99 = VALID JSON (rebuild_index 통과 → index[0], 최신) 이지만 render_from_data 가
    # 필요로 하는 운영 키가 없어 렌더 단계에서 실패 → done 에서 제외.
    # index.html 은 W99 가 아니라 done 에 있는 최신 주(W32)로 승격되어야 함.
    reports_dir = _copy_seeds(tmp_path / "reports")
    (reports_dir / "2026-W99.json").write_text(json.dumps({
        "week_id": "2026-W99",
        "week_range": "12-21 ~ 12-25",
        "label": "W99 (12/21~)",
        "generated_at": "2026-12-22T00:00:00",
    }, ensure_ascii=False), encoding="utf-8")
    out_dir = tmp_path / "out"

    weeks = R.render_all_archive(reports_dir=reports_dir, out_dir=out_dir)  # 크래시 금지

    assert "2026-W99" not in weeks
    assert set(weeks) == {"2026-W31", "2026-W32"}
    idx_html_path = out_dir / "index.html"
    assert idx_html_path.exists()
    assert "2026-W32" in idx_html_path.read_text(encoding="utf-8")
