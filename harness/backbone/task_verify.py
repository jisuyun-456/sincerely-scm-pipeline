"""⚡task 투입자재 vs WMS_BOM 검증 순수 로직 (P2b Task 2b.2).

⚡task의 (PNA, PT) 쌍 = 생산이 실제 그 자재로 실행된 증거 →
order그룹핑으로 부트스트랩된 WMS_BOM 행(검증상태='이송')을 '검증완료'로 승급.
신규 BOM INSERT 금지 — 승급 대상 record id 선별만.
"""
from __future__ import annotations

from harness.backbone.keys import PNA_RE, extract_pts

TASK_MATERIAL_FIELDS = ("생산공정_투입자재 (from order)", "이전공정_투입자재")


def _text(v) -> str:
    if isinstance(v, list):
        return " ".join(str(x) for x in v)
    return str(v or "")


def extract_task_pairs(task_fields_iter) -> set[tuple[str, str]]:
    """⚡task fields dicts → {(PNA, PT)}. lookup 필드 list 언랩."""
    pairs: set[tuple[str, str]] = set()
    for f in task_fields_iter:
        m = PNA_RE.search(_text(f.get("project_code")))
        if not m:
            continue
        for field in TASK_MATERIAL_FIELDS:
            for pt in extract_pts(_text(f.get(field))):
                pairs.add((m.group(0), pt))
    return pairs


def select_bom_promotions(bom_records, task_pairs) -> tuple[list[str], dict]:
    """검증상태='이송' BOM record 중 (PNA, 소품목_PT) ∈ task_pairs → 승급 대상 id + stats."""
    ids: list[str] = []
    stats = {"total": 0, "not_isong": 0, "no_key": 0, "matched": 0, "unmatched": 0}
    for rec in bom_records:
        f = rec.get("fields", {})
        stats["total"] += 1
        if f.get("검증상태") != "이송":
            stats["not_isong"] += 1
            continue
        m = PNA_RE.search(_text(f.get("프로젝트코드")))
        pt = _text(f.get("소품목_PT")).strip()
        if not m or not pt:
            stats["no_key"] += 1
            continue
        if (m.group(0), pt) in task_pairs:
            ids.append(rec["id"])
            stats["matched"] += 1
        else:
            stats["unmatched"] += 1
    return ids, stats
