from __future__ import annotations
from .config import TABLES, BASE_ALIAS, AIRTABLE_CONTENT_URL
from .utils import paginated_get, patch_records, upload_attachment, get_table_schema


def tms_shipments(
    date_from: str,
    date_to: str,
    status: str | None = None,
    carrier: str | None = None,
) -> list[dict]:
    """배송 출하 레코드 조회.

    Args:
        date_from: 시작일 YYYY-MM-DD
        date_to: 종료일 YYYY-MM-DD
        status: 발송상태_TMS 필터 — 출하완료|배송중|배송완료 (없으면 전체)
        carrier: 배송파트너 필터 — CJ|한진|로젠|우체국|신시어리 (없으면 전체)

    Returns:
        Shipment 레코드 리스트
    """
    base_id, table_id = TABLES["shipment"]

    conditions = [
        f"AND({{출하일자}}>='{date_from}', {{출하일자}}<='{date_to}')"
    ]
    if status:
        conditions.append(f"{{발송상태_TMS}}='{status}'")
    if carrier:
        conditions.append(f"{{배송파트너}}='{carrier}'")

    formula = f"AND({', '.join(conditions)})" if len(conditions) > 1 else conditions[0]
    records = paginated_get(base_id, table_id, formula=formula)
    return [{"id": r["id"], **r["fields"]} for r in records]


def tms_delivery_events(shipment_id: str) -> list[dict]:
    """배송이벤트 이력 조회.

    Args:
        shipment_id: Shipment 레코드 ID (rec…)

    Returns:
        배송이벤트 레코드 리스트 (시간순)
    """
    base_id, table_id = TABLES["delivery_event"]
    formula = f"FIND('{shipment_id}', ARRAYJOIN({{Shipment}}, ','))>0"
    records = paginated_get(base_id, table_id, formula=formula)
    return [{"id": r["id"], **r["fields"]} for r in records]


def tms_otif(year: int | None = None, quarter: int | None = None) -> list[dict]:
    """OTIF KPI 레코드 조회.

    Args:
        year: 연도 필터 (없으면 전체)
        quarter: 분기 필터 1~4 (없으면 전체)

    Returns:
        OTIF 레코드 리스트
    """
    base_id, table_id = TABLES["otif"]

    conditions: list[str] = []
    if year:
        conditions.append(f"{{연도}}={year}")
    if quarter:
        conditions.append(f"{{분기}}={quarter}")

    formula = f"AND({', '.join(conditions)})" if len(conditions) > 1 else (conditions[0] if conditions else None)
    records = paginated_get(base_id, table_id, formula=formula)
    return [{"id": r["id"], **r["fields"]} for r in records]


def tms_update_shipment(record_id: str, fields: dict) -> dict:
    """Shipment 레코드 필드 업데이트 (PATCH).

    Args:
        record_id: 업데이트할 Shipment 레코드 ID (rec…)
        fields: 업데이트할 필드 딕셔너리 e.g. {"실제배송일수": 2}

    Returns:
        업데이트된 레코드
    """
    base_id, table_id = TABLES["shipment"]
    results = patch_records(base_id, table_id, [{"id": record_id, "fields": fields}])
    if results:
        r = results[0]
        return {"id": r["id"], **r["fields"]}
    return {"error": "업데이트 실패"}


def upload_pdf(base: str, record_id: str, field_name: str, pdf_path: str) -> dict:
    """Airtable Content API로 PDF 파일 첨부.

    Args:
        base: 베이스 별칭 — wms_barcode | wms_material | tms
        record_id: 대상 레코드 ID (rec…)
        field_name: 첨부할 필드 이름 (예: "출고확인서PDF")
        pdf_path: 로컬 PDF 파일 절대 경로

    Returns:
        업로드 결과 딕셔너리
    """
    import os
    base_id = BASE_ALIAS.get(base)
    if not base_id:
        return {"error": f"알 수 없는 base 별칭: {base}. 사용 가능: {list(BASE_ALIAS.keys())}"}

    schema = get_table_schema(base_id)
    field_id: str | None = None
    for table in schema.get("tables", []):
        for f in table.get("fields", []):
            if f.get("name") == field_name:
                field_id = f["id"]
                break
        if field_id:
            break

    if not field_id:
        return {"error": f"필드 미발견: {field_name}"}

    with open(pdf_path, "rb") as fh:
        pdf_bytes = fh.read()

    filename = os.path.basename(pdf_path)
    return upload_attachment(base_id, record_id, field_id, filename, pdf_bytes)
