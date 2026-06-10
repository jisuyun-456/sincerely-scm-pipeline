"""⚡task 투입자재 vs WMS_BOM 검증 순수 로직 테스트 (P2b Task 2b.2)."""
from harness.backbone.task_verify import extract_task_pairs, select_bom_promotions


class TestExtractTaskPairs:
    def test_pairs_from_both_fields(self):
        rows = [{"project_code": "PNA12345_고객A",
                 "생산공정_투입자재 (from order)": "PT1234 투입",
                 "이전공정_투입자재": "PT5678, PT1234"}]
        assert extract_task_pairs(rows) == {("PNA12345", "PT1234"), ("PNA12345", "PT5678")}

    def test_no_project_skipped(self):
        assert extract_task_pairs([{"이전공정_투입자재": "PT1234"}]) == set()

    def test_list_wrapped_lookup_fields(self):
        rows = [{"project_code": ["PNA777"],
                 "생산공정_투입자재 (from order)": ["PT111222"]}]
        assert extract_task_pairs(rows) == {("PNA777", "PT111222")}


class TestSelectBomPromotions:
    BOM = [
        {"id": "rec1", "fields": {"프로젝트코드": "PNA12345_x", "소품목_PT": "PT1234", "검증상태": "이송"}},
        {"id": "rec2", "fields": {"프로젝트코드": "PNA12345_x", "소품목_PT": "PT9999", "검증상태": "이송"}},
        {"id": "rec3", "fields": {"프로젝트코드": "PNA12345_x", "소품목_PT": "PT1234", "검증상태": "검증완료"}},
        {"id": "rec4", "fields": {"프로젝트코드": "", "소품목_PT": "PT1234", "검증상태": "이송"}},
    ]

    def test_only_isong_matching_promoted(self):
        ids, stats = select_bom_promotions(self.BOM, {("PNA12345", "PT1234")})
        assert ids == ["rec1"]
        assert stats == {"total": 4, "not_isong": 1, "no_key": 1,
                         "matched": 1, "unmatched": 1}
