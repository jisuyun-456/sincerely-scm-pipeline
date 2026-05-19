---
type: community
cohesion: 0.08
members: 37
---

# Barcode & PDF Generation

**Cohesion:** 0.08 - loosely connected
**Members:** 37 nodes

## Members
- [[Barcode 라벨지 GET 트리거 — Interface 'Open URL' 버튼용]] - rationale - api/app.py
- [[Barcode 베이스 출고확인서  피킹리스트  라벨지]] - rationale - api/app.py
- [[Barcode 출고확인서 GET 트리거 — Interface 'Open URL' 버튼용]] - rationale - api/app.py
- [[Barcode 피킹리스트 GET 트리거 — Interface 'Open URL' 버튼용]] - rationale - api/app.py
- [[BarcodeRequest]] - code - api/app.py
- [[BaseModel]] - code
- [[FastAPI 웹훅 서버 — Railway 배포용 GitHub Actions (generate-barcode-pdf, generate-pdf)]] - rationale - api/app.py
- [[PkgLabelRequest]] - code - api/app.py
- [[TMS 출고확인서 GET 트리거 — Interface 'Open URL' 버튼용]] - rationale - api/app.py
- [[TMSRequest]] - code - api/app.py
- [[WMS 출고서류 3종 carton_label  packing_list  shipping_mark  all]] - rationale - api/app.py
- [[WMS 출고서류 GET 트리거 — Interface 'Open URL' 버튼용]] - rationale - api/app.py
- [[WMSRequest]] - code - api/app.py
- [[_check_secret()]] - code - api/app.py
- [[_run()]] - code - api/app.py
- [[_run_bg()]] - code - api/app.py
- [[_run_wms_all()]] - code - api/app.py
- [[app.py]] - code - api/app.py
- [[generate_barcode_pdf()]] - code - api/app.py
- [[generate_pkg_label()]] - code - api/app.py
- [[generate_tms_pdf()]] - code - api/app.py
- [[generate_wms_pdf()]] - code - api/app.py
- [[health()]] - code - api/app.py
- [[pkg_schedule 투입자재 라벨 GET 트리거 — Interface 'Open URL' 버튼용]] - rationale - api/app.py
- [[pkg_schedule 투입자재 피킹 라벨 (80×55mm)]] - rationale - api/app.py
- [[trigger_barcode_label_get()]] - code - api/app.py
- [[trigger_barcode_outgoing_get()]] - code - api/app.py
- [[trigger_barcode_picking_get()]] - code - api/app.py
- [[trigger_customer_goods_label_get()]] - code - api/app.py
- [[trigger_inbound_label_get()]] - code - api/app.py
- [[trigger_pkg_label_get()]] - code - api/app.py
- [[trigger_pkg_return_sheet_get()]] - code - api/app.py
- [[trigger_tms_pdf_get()]] - code - api/app.py
- [[trigger_wms_pdf_get()]] - code - api/app.py
- [[고객물품 라벨 GET 트리거 — Interface 'Open URL' 버튼용]] - rationale - api/app.py
- [[임가공 리턴 자재 구분표 GET 트리거 — Interface 'Open URL' 버튼용]] - rationale - api/app.py
- [[입고 라벨 GET 트리거 — Interface 'Open URL' 버튼용]] - rationale - api/app.py

## Live Query (requires Dataview plugin)

```dataview
TABLE source_file, type FROM #community/Barcode__PDF_Generation
SORT file.name ASC
```
