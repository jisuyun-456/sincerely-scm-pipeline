"""VerifierResult serialization tests."""
from harness.virtual_sap.verifier.base import DimScore, Issue, Severity, VerifierResult


def test_verifier_result_to_dict_passed():
    result = VerifierResult(
        passed=True,
        dim_scores=[DimScore("D1", passed=True, issue_count=0)],
        issues=[],
    )
    d = result.to_dict()
    assert d["passed"] is True
    assert d["issues"] == []
    assert d["dim_scores"][0]["dim"] == "D1"


def test_verifier_result_to_dict_failed():
    issue = Issue(dim="D2", severity=Severity.ERROR,
                  entity_type="mat_document", entity_id="abc", msg="orphan item")
    result = VerifierResult(
        passed=False,
        dim_scores=[DimScore("D2", passed=False, issue_count=1)],
        issues=[issue],
    )
    d = result.to_dict()
    assert d["passed"] is False
    assert len(d["issues"]) == 1
    assert d["issues"][0]["dim"] == "D2"
    assert d["issues"][0]["severity"] == "ERROR"


def test_issue_str_representation():
    issue = Issue(dim="D5", severity=Severity.WARN,
                  entity_type="sales_order", entity_id="SO-001", msg="test msg")
    s = str(issue)
    assert "D5" in s
    assert "WARN" in s
    assert "test msg" in s
