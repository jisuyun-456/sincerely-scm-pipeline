from __future__ import annotations
from .config import TABLES
from .utils import paginated_get


def wms_movements(
    date_from: str,
    date_to: str,
    purpose: str | None = None,
    status: str | None = None,
) -> list[dict]:
    """WMS 이동 트랜잭션 조회 (입하·재고이동·출하).

    Args:
        date_from: 시작일 YYYY-MM-DD (입하일자 기준)
        date_to: 종료일 YYYY-MM-DD
        purpose: 이동목적 필터 — 생산산출|재고이동|조립투입|출하 (없으면 전체)
        status: 상태 필터 (없으면 전체)

    Returns:
        movement 레코드 리스트 (id + fields)
    """
    base_id, table_id = TABLES["movement"]

    conditions = [
        f"AND({{입하일자}}>='{date_from}', {{입하일자}}<='{date_to}')"
    ]
    if purpose:
        conditions.append(f"{{이동목적}}='{purpose}'")
    if status:
        conditions.append(f"{{상태}}='{status}'")

    formula = f"AND({', '.join(conditions)})" if len(conditions) > 1 else conditions[0]
    records = paginated_get(base_id, table_id, formula=formula)
    return [{"id": r["id"], **r["fields"]} for r in records]


def wms_inventory(parts_code: str | None = None) -> list[dict]:
    """재고 원장 조회 — material(재고수량) + sync_parts(파츠 마스터) 조인.

    Args:
        parts_code: 특정 파츠 코드 필터 (없으면 전체)

    Returns:
        파츠별 재고 정보 리스트
    """
    base_id, mat_table = TABLES["material"]
    _, parts_table = TABLES["sync_parts"]

    mat_formula = f"{{파츠코드}}='{parts_code}'" if parts_code else None
    material_records = paginated_get(base_id, mat_table, formula=mat_formula)
    parts_records = paginated_get(base_id, parts_table)

    parts_index: dict[str, dict] = {}
    for r in parts_records:
        code = r["fields"].get("파츠코드") or r["fields"].get("품번")
        if code:
            parts_index[code] = r["fields"]

    result = []
    for r in material_records:
        fields = r["fields"]
        code = fields.get("파츠코드") or fields.get("품번")
        merged = {"id": r["id"], **fields}
        if code and code in parts_index:
            for k, v in parts_index[code].items():
                if k not in merged:
                    merged[f"parts_{k}"] = v
        result.append(merged)
    return result


def wms_picking_docs(shipment_ref: str) -> dict:
    """피킹리스트·출고확인서·바코드 통합 조회 (3-way join).

    Args:
        shipment_ref: 출고확인서 레코드 ID (rec…) 또는 SC 번호 문자열

    Returns:
        {outbound_confirm, picking_list, barcodes} 통합 딕셔너리
    """
    barcode_base, barcode_table = TABLES["barcode"]
    _, picking_table = TABLES["picking_list"]
    _, confirm_table = TABLES["outbound_confirm"]

    if shipment_ref.startswith("rec"):
        confirm_formula = f"RECORD_ID()='{shipment_ref}'"
    else:
        confirm_formula = f"FIND('{shipment_ref}', {{SC번호}})>0"

    confirm_records = paginated_get(barcode_base, confirm_table, formula=confirm_formula)
    if not confirm_records:
        return {"error": f"출고확인서 미발견: {shipment_ref}"}

    confirm = confirm_records[0]
    confirm_id = confirm["id"]

    picking_records = paginated_get(
        barcode_base, picking_table,
        formula=f"FIND('{confirm_id}', ARRAYJOIN({{출고확인서}}, ','))>0",
    )
    barcode_records = paginated_get(
        barcode_base, barcode_table,
        formula=f"FIND('{confirm_id}', ARRAYJOIN({{출고확인서}}, ','))>0",
    )

    return {
        "outbound_confirm": {"id": confirm_id, **confirm["fields"]},
        "picking_list": [{"id": r["id"], **r["fields"]} for r in picking_records],
        "barcodes": [{"id": r["id"], **r["fields"]} for r in barcode_records],
    }
