"""Verify 0001_initial_schema.sql uses IF NOT EXISTS on every CREATE TABLE."""
from pathlib import Path


def test_all_create_table_are_idempotent():
    sql = (
        Path(__file__).parent.parent.parent
        / "harness/virtual_sap/sql/migrations/0001_initial_schema.sql"
    ).read_text(encoding="utf-8")

    create_lines = [
        line.strip() for line in sql.splitlines()
        if line.strip().upper().startswith("CREATE TABLE")
    ]
    assert create_lines, "No CREATE TABLE statements found"
    for line in create_lines:
        assert "IF NOT EXISTS" in line.upper(), (
            f"Missing IF NOT EXISTS: {line}"
        )
