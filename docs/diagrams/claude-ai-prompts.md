# Claude AI 다이어그램 생성 프롬프트

> **사용법**: 아래 각 프롬프트를 통째로 복사 → [claude.ai](https://claude.ai) 채팅창에 붙여넣기
> → 아티팩트로 Mermaid 다이어그램 생성
> → draw.io XML이 필요하면 "draw.io XML로 변환해줘" 추가 요청

---

## 프롬프트 1 — AS-IS: 현재 Airtable TMS + WMS 구조

```
다음 Airtable TMS/WMS 구조를 Mermaid erDiagram으로 그려줘.
TMS Base와 WMS Base를 주석으로 구분하고, 주요 필드 5~7개씩 포함해줘.

[TMS Base]
배송요청 ||--o{ Shipment : "has"
Shipment }o--|| 배송파트너 : "assigned_to"
Shipment }o--|| Location : "destination"
배송요청 }o--|| 출하장소 : "origin"

배송요청 {
  string logistics_PK PK
  string project
  date 출고요청일
  string 수령인주소
  string 배송방식
  string 발송상태
  string 운송장번호
}
Shipment {
  string SC_id PK
  date 출하일자
  string 발송상태
  number Total_CBM
  number 물류매출
  number 운송비용
  date 출하확정일
}
배송파트너 {
  string Name PK
  number CBM용량
  number 잔여용량
  string 배차담당
}
Location {
  string Name PK
  number Max_CBM
  number Current_CBM
  string 담당자
}
출하장소 {
  string Name PK
  string 출고지주소
  string 입하주소
}

[WMS Base]
project ||--o{ order : "contains"
project ||--o{ pkg_schedule : "has"
order ||--o{ movement : "triggers"
movement }o--|| material_stock : "affects"
pkg_schedule ||--o{ pkg_task : "consists_of"
sync_parts ||--o{ sync_item : "composes"
sync_item ||--o{ sync_goods : "forms"
material_stock ||--o{ 실사카운트 : "counted_in"

project {
  string Name PK
  string project_status
  string 고객회사명
  date 출고요청일
}
order {
  string order_id PK
  string 발주단계
  number 발주수량
  date 입고예정일
  string 협력사
  number 매출원가
}
movement {
  string movement_id PK
  string 이동목적
  number 이동수량
  date 실제입하일
}
material_stock {
  string Name PK
  number 실물재고수량
  number 전산재고수량
  string 좌표
}
pkg_schedule {
  string Name PK
  string 진행현황
  date 임가공예정일
  string 임가공장소
}
sync_parts {
  string 파츠명 PK
  string 파츠유형
  number 발주점
  string 보관창고
}
sync_goods {
  string Goods_Code PK
  string 제품유형
  number MOQ
  number 박스당포장수량
}
```

---

## 프롬프트 2 — TO-BE: Supabase SSOT 전체 스키마 (6개, finance 포함)

```
SAP S/4HANA + 더존 K-IFRS 기반 Supabase PostgreSQL 스키마를 Mermaid erDiagram으로 그려줘.
6개 Schema(shared/tms/wms/mm/pp/finance)를 그룹 또는 색상으로 구분해줘.

[SHARED — Master Data]
shared_organizations ||--o{ shared_users : "belongs_to"
shared_clients ||--o{ shared_projects : "client_id"
shared_vendors ||--o{ shared_parts_master : "vendor_id"
shared_vendors ||--o{ mm_purchase_orders : "vendor_id"
shared_goods_master ||--o{ shared_item_master : "goods_id"
shared_item_master ||--o{ shared_parts_master : "item_id"
shared_parts_master ||--o{ wms_quants : "parts_id"
shared_parts_master ||--o{ mm_stock_movements : "parts_id"
shared_gl_accounts ||--o{ finance_accounting_entries : "debit_account_id"

[TMS — Transportation]
shared_projects ||--o{ tms_transportation_requirements : "project_id"
tms_transportation_requirements ||--o{ tms_freight_orders : "tr_id"
tms_carriers ||--o{ tms_freight_orders : "carrier_id"
tms_dispatch_schedules ||--o{ tms_freight_orders : "dispatch_schedule_id"
tms_freight_orders ||--o{ finance_accounting_entries : "source_id"

[WMS — Warehouse]
wms_warehouses ||--o{ wms_storage_bins : "warehouse_id"
wms_storage_bins ||--o{ wms_quants : "storage_bin_id"
wms_batches ||--o{ wms_quants : "batch_id"
wms_inventory_count_docs ||--o{ wms_inventory_count_items : "doc_id"

[MM — Materials]
shared_projects ||--o{ mm_purchase_orders : "project_id"
mm_purchase_orders ||--o{ mm_purchase_order_items : "po_id"
mm_purchase_order_items ||--o{ mm_goods_receipts : "po_item_id"
mm_goods_receipts ||--o{ mm_stock_movements : "gr_id"
mm_goods_receipts ||--o{ finance_accounting_entries : "source_id"
mm_stock_movements ||--o{ finance_accounting_entries : "source_id"

[PP — Production]
pp_bom_headers ||--o{ pp_bom_items : "bom_id"
shared_projects ||--o{ pp_production_orders : "project_id"
pp_production_orders ||--o{ pp_production_order_components : "production_order_id"
pp_production_orders ||--o{ pp_production_confirmations : "production_order_id"
pp_production_orders ||--o{ tms_logistics_releases : "production_order_id"

[FINANCE — 더존 K-IFRS 연계]
finance_accounting_entries ||--o{ finance_douzone_sync_log : "entry_id"
finance_cost_settings ||--o{ finance_accounting_entries : "costing_method"

[Key Fields]
shared_parts_master {
  uuid id PK
  string parts_code
  string parts_name
  uuid vendor_id FK
  string parts_type
  boolean is_stock_managed
}
mm_purchase_order_items {
  uuid id PK
  uuid po_id FK
  uuid parts_id FK
  int order_qty
  numeric unit_price
  numeric total_amount
}
mm_goods_receipts {
  uuid id PK
  uuid po_item_id FK
  int received_qty
  numeric unit_cost
  string tax_invoice_no
  date actual_receipt_date
}
mm_stock_movements {
  uuid id PK
  string movement_type
  string sap_movement_code
  uuid parts_id FK
  int actual_qty
  numeric unit_cost_at_movement
}
wms_quants {
  uuid id PK
  uuid parts_id FK
  uuid storage_bin_id FK
  uuid batch_id FK
  int physical_qty
  int system_qty
}
finance_accounting_entries {
  uuid id PK
  string entry_number
  string entry_type
  string source_table
  uuid source_id
  uuid debit_account_id FK
  uuid credit_account_id FK
  numeric amount
  numeric unit_cost
  string costing_method
  string tax_invoice_no
  string status
  string douzone_slip_no
}
```

---

## 프롬프트 3 — 더존 연계 흐름도

```
다음 데이터 흐름을 Mermaid flowchart LR으로 그려줘.
Supabase 운영 이벤트 → finance 전표 자동생성 → 더존 아마란스10 입력 흐름.

flowchart LR
  subgraph OPS["운영 시스템 (Supabase SSOT)"]
    GR["📦 mm.goods_receipts\n입하 처리\n(unit_cost 기록)"]
    SM_IN["⚙️ stock_movements\nassembly_issue\n(임가공 투입)"]
    SM_OUT["✅ stock_movements\nassembly_receipt\n(임가공 완성)"]
    SM_DEL["🚚 stock_movements\ngoods_issue\n(출고)"]
    FO["🚛 tms.freight_orders\n배송 완료\n(운임 발생)"]
    INV["📊 inventory_count\n재고실사 조정"]
  end

  subgraph FIN["finance 스키마 (전표 자동생성)"]
    AE["📋 accounting_entries\nstatus: draft\n차변/대변 자동 분개"]
    CS["⚙️ cost_settings\nweighted_avg / fifo"]
    GLA["📒 gl_accounts\n계정과목 매핑"]
  end

  subgraph DZ["더존 아마란스10"]
    REV["👀 회계팀 검토\nstatus: reviewed"]
    POST["✏️ 전표 입력\ndouzone_slip_no 기재"]
    AUDIT["📁 연간 감사\nK-IFRS 대응"]
  end

  GR -->|"DR:원재료 CR:매입채무"| AE
  SM_IN -->|"DR:재공품 CR:원재료"| AE
  SM_OUT -->|"DR:제품 CR:재공품"| AE
  SM_DEL -->|"DR:매출원가 CR:제품"| AE
  FO -->|"DR:운임비용 CR:미지급금"| AE
  INV -->|"DR/CR:재고조정"| AE
  CS -->|"원가방식 적용"| AE
  GLA -->|"계정코드 매핑"| AE
  AE --> REV
  REV --> POST
  POST -->|"전표번호 역기록"| AE
  POST --> AUDIT
```
