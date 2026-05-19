"""Golden suite — 10 cases locking in fare calc correctness.

Lee  ×2: 2-ship day (÷2=80,000) | 3-ship day (53,500+53,500+53,000=160,000)
Cho  ×2: 경기1+서울1 (÷2=180,000) | 경기3 (surcharge×2÷3=140,000)
Park ×5: NO_COORD | 강남(59,500) | 부산(414,500) | 광주(354,000) | unload(+25,000)
Out  ×1: MM외주임가공/1건 (70,000)

If a test here breaks, confirm the change was intentional before updating the
expected value — these numbers match the contractual fare formula as of 2026-01-01.
"""
from __future__ import annotations

from tests.tms_settlement.conftest import rec
from harness.tms_settlement.calc import calc_cho, calc_lee, calc_park
from harness.tms_settlement.config import DRIVER_CHO, DRIVER_LEE, DRIVER_PARK

DATE = "2026-05-05"


# ── Lee ──────────────────────────────────────────────────────────────────────

def test_lee_two_ships_same_day():
    # 160,000 / 2 = 80,000 (exact multiple of 500)
    recs = [
        rec("r1", "SC-001", DATE, DRIVER_LEE, "서울 강남구 테헤란로"),
        rec("r2", "SC-002", DATE, DRIVER_LEE, "서울 서초구 반포대로"),
    ]
    items = calc_lee(recs, DRIVER_LEE)
    assert len(items) == 2
    assert all(i.fare_gross == 80_000 for i in items)
    assert all(i.driver_name == "이장훈" for i in items)
    assert all(i.withholding == 0 for i in items)  # T0-1 not yet resolved


def test_lee_three_ships_same_day():
    # per_ship = ceil(160,000/3/500)*500 = 53,500 for first 2; last = 160,000 - 107,000 = 53,000
    # total = 160,000 (slot fare exactly, no rounding over-run)
    recs = [
        rec("r1", "SC-001", DATE, DRIVER_LEE, "서울 강남구 테헤란로"),
        rec("r2", "SC-002", DATE, DRIVER_LEE, "서울 서초구 반포대로"),
        rec("r3", "SC-003", DATE, DRIVER_LEE, "서울 송파구 올림픽로"),
    ]
    items = calc_lee(recs, DRIVER_LEE)
    assert len(items) == 3
    assert items[0].fare_gross == 53_500
    assert items[1].fare_gross == 53_500
    assert items[2].fare_gross == 53_000
    assert sum(i.fare_gross for i in items) == 160_000


# ── Cho ──────────────────────────────────────────────────────────────────────

def test_cho_gyeonggi1_seoul1():
    # gyeonggi=1 → surcharge=max(0,1-1)×30,000=0 → 360,000/2 = 180,000
    recs = [
        rec("r1", "SC-001", DATE, DRIVER_CHO, "경기 수원시 팔달구"),
        rec("r2", "SC-002", DATE, DRIVER_CHO, "서울 강남구 테헤란로"),
    ]
    items = calc_cho(recs, DRIVER_CHO)
    assert len(items) == 2
    assert all(i.fare_gross == 180_000 for i in items)
    assert all(i.driver_name == "조희선" for i in items)


def test_cho_gyeonggi3():
    # gyeonggi=3 → surcharge=2×30,000=60,000 → (360,000+60,000)/3 = 140,000
    recs = [
        rec("r1", "SC-001", DATE, DRIVER_CHO, "경기 수원시 팔달구"),
        rec("r2", "SC-002", DATE, DRIVER_CHO, "경기 용인시 기흥구"),
        rec("r3", "SC-003", DATE, DRIVER_CHO, "경기 성남시 분당구"),
    ]
    items = calc_cho(recs, DRIVER_CHO)
    assert len(items) == 3
    assert all(i.fare_gross == 140_000 for i in items)


# ── Park ─────────────────────────────────────────────────────────────────────

def test_park_no_coord():
    # Unrecognised address → no_coord=True, fare_gross=0, must not be PATCHed
    recs = [rec("r1", "SC-001", DATE, DRIVER_PARK, "배송지 미확인 임시창고")]
    items = calc_park(recs, DRIVER_PARK)
    assert len(items) == 1
    assert items[0].no_coord is True
    assert items[0].fare_gross == 0


def test_park_gangnam():
    # 에이원지식산업센터(37.5477,127.0446) → 강남구(37.5172,127.0473)
    # hav≈3.40km  road≈4.59km  55,421+831×4.59≈59,235 → ceil_500=59,500
    recs = [rec("r1", "SC-001", DATE, DRIVER_PARK, "서울 강남구 테헤란로")]
    items = calc_park(recs, DRIVER_PARK)
    assert len(items) == 1
    assert items[0].fare_gross == 59_500
    assert items[0].no_coord is False
    assert items[0].driver_name == "박종성"


def test_park_busan():
    # 에이원지식산업센터 → 부산(35.1796,129.0756)
    # hav≈320.0km  road≈432.0km  55,421+831×432.0≈414,413 → ceil_500=414,500
    # NOTE: "해운대구" contains "대구" as a substring → Daegu false-match; use "수영구"
    recs = [rec("r1", "SC-001", DATE, DRIVER_PARK, "부산 수영구 민락동")]
    items = calc_park(recs, DRIVER_PARK)
    assert items[0].fare_gross == 414_500


def test_park_gwangju():
    # 에이원지식산업센터 → 광주(35.1595,126.8526)
    # hav≈266.1km  road≈359.3km  55,421+831×359.3≈353,955 → ceil_500=354,000
    recs = [rec("r1", "SC-001", DATE, DRIVER_PARK, "광주 서구 상무지구")]
    items = calc_park(recs, DRIVER_PARK)
    assert items[0].fare_gross == 354_000


def test_park_unload_fee():
    # box_text "중대10대6특대3":
    #   heavy=10 → (10//5)*5,000=10,000
    #   large=6  → (6//3)*5,000=10,000
    #   xlarge=3 → (3//3)*5,000=5,000
    #   total=25,000 (under 50,000 cap)
    recs = [
        rec("r1", "SC-001", DATE, DRIVER_PARK, "서울 강남구 테헤란로",
            box_text="중대10대6특대3")
    ]
    items = calc_park(recs, DRIVER_PARK)
    assert items[0].fare_gross == 59_500
    assert items[0].unload_calc == 25_000


# ── Outsource ─────────────────────────────────────────────────────────────────

def test_park_outsource_single():
    # MM외주임가공 trigger: SC_ID starts "MM" + dest contains "다영기획" OR "성남시" + note "외주임가공"
    # Real Airtable dest is a street address (no literal "다영기획") — must still match.
    # 1 ship → ceil(70,000/1/500)*500 = 70,000
    recs = [
        rec(
            "r1", "MM-2026-001", DATE, DRIVER_PARK,
            "경기 성남시 분당구 정자동 10",
            request_note="외주임가공 1박스",
        )
    ]
    items = calc_park(recs, DRIVER_PARK)
    assert len(items) == 1
    assert items[0].fare_gross == 70_000
    assert items[0].no_coord is False
    assert "MM외주임가공" in items[0].note
