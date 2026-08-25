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


def test_delta_kinds():
    assert R._delta(65.4, 42.5, "pp", thresh=10) == ("▲22.9p", True)
    assert R._delta(29.04, 18.86, "pct", thresh=20) == ("▲+54%", True)
    assert R._delta(5, 8, "abs", lower_better=True, thresh=2) == ("▼3 개선", True)
    assert R._delta(2, 10, "abs", lower_better=True, thresh=5) == ("▼8 개선", True)
    assert R._delta(97.8, 97.8, "none") == ("–", False)
    assert R._delta(100.0, 99.6, "pp", thresh=1) == ("▲0.4p", False)   # 임계 미만 → 이탈 아님
    assert R._delta(5, None, "abs") == ("–", False)                    # prev 없음


def test_render_markdown_structure(tmp_path):
    reports_dir = _copy_seeds(tmp_path / "reports")
    p = R.render_markdown("2026-W32", reports_dir=reports_dir, out_dir=reports_dir)
    md = p.read_text(encoding="utf-8")
    # 프로세스 5단계 버킷 + 순서(입하→검수→입고→자재→출하)
    for stage in ["📥 입하", "🔎 검수", "📦 입고", "🧰 자재", "🚚 출하"]:
        assert stage in md
    assert md.index("📥 입하") < md.index("🔎 검수") < md.index("📦 입고") < md.index("🧰 자재") < md.index("🚚 출하")
    # WoW 비교대상 + 실제 계산 (미입하 10→2 ▼8)
    # 주간 CBM 값은 2026-08-25 CBM_유효 소스 전환(구 Total_CBM 미입력 다수 버그 수정)으로
    # 42.24→38.89(▼7.9%)로 갱신 — freeze_week() 재실행 시 Airtable 실측이 바뀌면 이 값도 같이
    # 바뀔 수 있는 fixture라는 점 유의 (하드코딩 스냅샷, 라이브 재계산 아님).
    assert "compare_to: 2026-W31" in md
    assert "▼8 개선" in md
    assert "▼7.9%" in md
    # 예외중심 신호 테이블
    assert "이번 주 이탈·특이 신호" in md
    # 전환 KPI = 라이브 상수 (다영 86.5 · 프리패키징 12.1/88.6)
    assert "86.5%" in md
    assert "실측 12.1% / 추정포함 88.6%" in md


def test_render_markdown_no_prev_week(tmp_path):
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir(parents=True)
    shutil.copy(SEED_DIR / "2026-W31.json", reports_dir / "2026-W31.json")
    md = R.render_markdown("2026-W31", reports_dir=reports_dir, out_dir=reports_dir).read_text(encoding="utf-8")
    assert "compare_to: 없음" in md          # 직전주 없어도 생성
    assert "📥 입하" in md


def test_render_markdown_includes_breakdown_section(tmp_path):
    reports_dir = _copy_seeds(tmp_path / "reports")
    p = R.render_markdown("2026-W32", reports_dir=reports_dir, out_dir=reports_dir)
    md = p.read_text(encoding="utf-8")
    # HTML의 build_operational_section 6개 차트에 대응하는 MD 섹션 — 전에는 누락돼 있었음
    assert "### 📊 추이 · 구성" in md
    assert "일별 입고 건수" in md
    assert "일별 출고 CBM" in md
    assert "입고 목적별 구성" in md
    assert "CBM 채널별 구성" in md
    assert "배송방식별 구성" in md
    assert "기사별 차량이용률" in md
    # 2026-W32.json 실제 값 일부가 그대로 반영되는지
    assert "신시어리 기사님 (조희선)" in md
    assert "54.2%" in md   # 이장훈 적재율
    # 다음주 예측 + 피킹 목적별도 기존 표에 병합됨 (조립투입 수는 라이브 재계산 시 드리프트 가능한 fixture 값)
    assert "다음주 예측 볼륨" in md
    assert "조립 354" in md
    # 구성 breakdown도 WoW(직전주 대비) 표 — 이전엔 이번주 값만 보여줬음
    assert "| 요일 | 2026-W31 | 2026-W32 | Δ |" in md
    assert "| 목적 | 2026-W31 | 2026-W32 | Δ |" in md
    assert "| 기사 | 2026-W31 | 2026-W32 | Δ |" in md


def test_daily_wow_table_aligns_by_weekday_not_position():
    cur = [{"date": "2026-08-04", "cnt": 10}]     # 화요일만 존재
    prev = [{"date": "2026-07-28", "cnt": 4}]     # 화요일만 존재 (다른 주)
    md = R._daily_wow_table("t", "s", cur, prev, "cnt", "CUR", "PREV",
                             lambda v: f"{v}건", "pct", 15.0)
    assert "| 화 | 4건 | 10건 | ▲+150%" in md
    assert "| 월 | – | – | – |" in md   # 데이터 없는 요일은 공백 처리, 크래시 없음


def test_daily_wow_table_flags_low_baseline_and_skips_misleading_delta():
    # W33->W34 실사례: 0.08m³ -> 10.03m³ 처럼 근거리 0 분모 탓에 ▲+12437% 처럼 오독되는 delta가
    # 나오면 안 됨 — CBM_유효 미입력 하한값 가능성을 ⚠️로 표시하고 Δ는 "–" 처리.
    cur = [{"date": "2026-08-19", "cbm": 10.03}]   # 수요일
    prev = [{"date": "2026-08-12", "cbm": 0.08}]   # 수요일 (전주), 1.0 미만 하한값
    md = R._daily_wow_table("일별 출고 CBM", "s", cur, prev, "cbm", "CUR", "PREV",
                             lambda v: f"{v:.2f}m³", "pct", 20.0, low_thresh=1.0)
    assert "| 수 | 0.08m³ ⚠️ | 10.03m³ | – |" in md   # Δ 미표시, 오독 방지
    assert "1.0 미만은 CBM_유효 등 실측 미입력" in md    # 캐비엇 안내 노출


def test_category_wow_table_unmatched_key_shows_dash():
    cur = [{"name": "신규채널", "cbm": 5.0, "cnt": 2}]
    prev = [{"name": "기존채널", "cbm": 3.0, "cnt": 1}]
    md = R._category_wow_table("t", "s", cur, prev, "name", "채널", "cbm", "CUR", "PREV",
                                lambda v: f"{v}m³" if v else "미기재", "pct", 20.0,
                                note_fn=lambda x: f'({x["cnt"]}건)')
    assert "신규채널" in md and "기존채널" not in md   # prev에만 있던 채널은 행에 안 나옴(현재 기준 순회)
    assert "| 신규채널 | – | 5.0m³ (2건) | – |" in md   # 매칭 안 되면 prev=–, Δ=–


def test_render_all_archive_emits_markdown(tmp_path):
    reports_dir = _copy_seeds(tmp_path / "reports")
    R.render_all_archive(reports_dir=reports_dir, out_dir=tmp_path / "out")
    assert (reports_dir / "2026-W32.md").exists()   # HTML 옆에 MD 동시 산출
    assert (reports_dir / "2026-W31.md").exists()


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
