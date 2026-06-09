"""order 라인 그룹핑 → BOM 행 변환 테스트."""
from harness.backbone.bom_bootstrap import build_bom_rows


def _rec(pc, goods, part, oqty):
    return {"fields": {"project_code": pc, "굿즈 주문 수량 (자동)": goods,
                       "파츠명": part, "주문수량": oqty}}


class TestBuildBomRows:
    def test_groups_parts_under_goods(self):
        recs = [
            _rec("PNA50702", "심볼아크릴트로피 125", "PT4900-아크릴트로피", 125),
            _rec("PNA50702", "심볼아크릴트로피 125", "PT4906-받침대", 125),
        ]
        rows = build_bom_rows(recs)
        assert len(rows) == 2
        by_pt = {r.part_code: r for r in rows}
        assert by_pt["PT4900"].soyoryang == 1.0
        assert by_pt["PT4906"].goods_name == "심볼아크릴트로피"
        assert by_pt["PT4900"].project_code == "PNA50702"

    def test_skips_service_lines(self):
        recs = [_rec("PNA1", "배송 1", "PT1282-하차서비스", 1)]
        assert build_bom_rows(recs) == []

    def test_skips_lines_without_pt(self):
        recs = [_rec("PNA1", "굿즈 10", "사양미정", 10)]
        assert build_bom_rows(recs) == []

    def test_double_soyoryang(self):
        recs = [_rec("PNA2", "키트 50", "PT100-볼트", 100)]
        rows = build_bom_rows(recs)
        assert rows[0].soyoryang == 2.0

    def test_bom_id_unique_format(self):
        recs = [_rec("PNA2", "키트 50", "PT100-볼트", 100)]
        rows = build_bom_rows(recs)
        assert rows[0].bom_id == "PNA2_키트_PT100"
