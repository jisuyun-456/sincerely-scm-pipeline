---
type: community
cohesion: 0.11
members: 29
---

# Cluster 32: config.py

**Cohesion:** 0.11 - loosely connected
**Members:** 29 nodes

## Members
- [[Airtable Content API로 PDF 파일 첨부.      Args         base 베이스 별칭 — wms_barcode]] - rationale - scm_mcp/scm_mcp/tms.py
- [[OTIF KPI 레코드 조회.      Args         year 연도 필터 (없으면 전체)         quarter 분기 필터]] - rationale - scm_mcp/scm_mcp/tms.py
- [[Shipment 레코드 필드 업데이트 (PATCH).      Args         record_id 업데이트할 Shipment 레코드 I]] - rationale - scm_mcp/scm_mcp/tms.py
- [[WMS 이동 트랜잭션 조회 (입하·재고이동·출하).      Args         date_from 시작일 YYYY-MM-DD (입하일자]] - rationale - scm_mcp/scm_mcp/wms.py
- [[__init__.py_10]] - code - scm_mcp/scm_mcp/__init__.py
- [[__main__.py]] - code - scm_mcp/scm_mcp/__main__.py
- [[_headers()]] - code - scm_mcp/scm_mcp/utils.py
- [[_request_with_retry()]] - code - scm_mcp/scm_mcp/utils.py
- [[config.py_3]] - code - scm_mcp/scm_mcp/config.py
- [[get_table_schema()_1]] - code - scm_mcp/scm_mcp/utils.py
- [[paginated_get()]] - code - scm_mcp/scm_mcp/utils.py
- [[patch_records()]] - code - scm_mcp/scm_mcp/utils.py
- [[server.py]] - code - scm_mcp/scm_mcp/server.py
- [[tms.py]] - code - scm_mcp/scm_mcp/tms.py
- [[tms_delivery_events()]] - code - scm_mcp/scm_mcp/tms.py
- [[tms_otif()]] - code - scm_mcp/scm_mcp/tms.py
- [[tms_shipments()]] - code - scm_mcp/scm_mcp/tms.py
- [[tms_update_shipment()]] - code - scm_mcp/scm_mcp/tms.py
- [[upload_attachment()]] - code - scm_mcp/scm_mcp/utils.py
- [[upload_pdf()]] - code - scm_mcp/scm_mcp/tms.py
- [[utils.py]] - code - scm_mcp/scm_mcp/utils.py
- [[wms.py]] - code - scm_mcp/scm_mcp/wms.py
- [[wms_inventory()]] - code - scm_mcp/scm_mcp/wms.py
- [[wms_movements()]] - code - scm_mcp/scm_mcp/wms.py
- [[wms_picking_docs()]] - code - scm_mcp/scm_mcp/wms.py
- [[배송 출하 레코드 조회.      Args         date_from 시작일 YYYY-MM-DD         date_to 종료일]] - rationale - scm_mcp/scm_mcp/tms.py
- [[배송이벤트 이력 조회.      Args         shipment_id Shipment 레코드 ID (rec…)      Returns]] - rationale - scm_mcp/scm_mcp/tms.py
- [[재고 원장 조회 — material(재고수량) + sync_parts(파츠 마스터) 조인.      Args         parts_code]] - rationale - scm_mcp/scm_mcp/wms.py
- [[피킹리스트·출고확인서·바코드 통합 조회 (3-way join).      Args         shipment_ref 출고확인서 레코드 I]] - rationale - scm_mcp/scm_mcp/wms.py

## Live Query (requires Dataview plugin)

```dataview
TABLE source_file, type FROM #community/Cluster_32_configpy
SORT file.name ASC
```
