# Retool + Supabase SCM 연결 가이드

> **목적:** Supabase 6스키마 51테이블을 Retool에서 운영/관리할 수 있는 내부 툴 구축
> **원칙:** Supabase = 불변 원장 (INSERT ONLY), Retool = 운영 UI + 조회/입력 레이어

---

## 1. Retool Resource 연결

### Step 1: Retool 가입 및 PostgreSQL Resource 생성

1. [retool.com](https://retool.com) 가입 (Free tier: 5 users, unlimited apps)
2. Settings → Resources → **+ New Resource** → **PostgreSQL**

### Step 2: 연결 정보 입력

| 항목 | 값 |
|------|-----|
| **Name** | `SCM_Supabase` |
| **Host** | `aws-1-ap-south-1.pooler.supabase.com` |
| **Port** | `6543` |
| **Database** | `postgres` |
| **Username** | `postgres.aigykrijhgjxqludjqed` |
| **Password** | (Supabase 대시보드에서 확인) |
| **SSL** | **Required** (Connect with SSL 체크) |

> **주의:** Direct Connection(`5432`)이 아닌 **Transaction Pooler**(`6543`)를 사용합니다.
> Supabase가 ap-south-1 리전이므로 호스트가 `aws-1-ap-south-1`입니다.

### Step 3: 연결 테스트

**Test Connection** 클릭 → 성공 시 Save

테스트 쿼리:
```sql
SELECT schemaname, COUNT(*) AS table_count
FROM pg_tables
WHERE schemaname IN ('shared','mm','wms','tms','pp','finance')
GROUP BY schemaname
ORDER BY schemaname;
```
**예상 결과:** 6개 스키마, 총 51개 테이블 (기존 NocoDB/Metabase와 동일)

---

## 2. Retool 앱 구조 — SCM 워크플로우 기반

### 전체 앱 맵

```
SCM Retool Workspace
│
├── [1] 프로젝트 대시보드     ← shared 스키마
│     전체 프로젝트 현황 + 상태별 필터 + 진행률
│
├── [2] 구매/발주 관리         ← mm 스키마
│     PO 생성 → 입고 확인 → 검수 → 반품 처리
│
├── [3] 창고/재고 관리         ← wms + mm 스키마
│     재고 현황 → 이동 내역 → 실사 → 재고 조정
│
├── [4] 생산/조립 관리         ← pp 스키마
│     생산지시 → BOM 확인 → 진행률 → 완료 보고
│
├── [5] 배송/물류 관리         ← tms 스키마
│     배송 요청 → 배차 → 출고 → 배송 추적
│
├── [6] 회계 조회              ← finance 스키마
│     분개 내역 → 더존 동기화 → 기간 마감
│
└── [7] 마스터 데이터 관리      ← shared 스키마
      고객/공급업체/품목/BOM 조회 및 등록
```

---

## 3. 앱별 상세 설계

---

### App 1: 프로젝트 대시보드

**용도:** 전체 프로젝트 파이프라인 한눈에 보기 (경영진 + CX 담당자)

#### 메인 화면 구성

```
┌─────────────────────────────────────────────────────┐
│  [KPI Cards]                                         │
│  총 프로젝트: 25  |  진행중: 20  |  완료: 5          │
│  이번달 배송: 3건  |  총 매출: ₩XX,XXX,XXX           │
├─────────────────────────────────────────────────────┤
│  [Status Filter] ○All ○Active ○Completed ○Planning  │
├─────────────────────────────────────────────────────┤
│  [프로젝트 테이블]                                    │
│  코드 | 이름 | 고객 | 수량 | 상태 | 담당 | 배송예정  │
│  PRJ-001 STCLab 임직원키트  100 completed 채효경 1/15│
│  PRJ-006 업스테이지 AI Day  120 active    지윤미 4/10│
│  ...                                                │
├─────────────────────────────────────────────────────┤
│  [클릭 시 사이드 패널 — 프로젝트 상세]                │
│  PO현황 / 입고현황 / 생산현황 / 배송현황 타임라인     │
└─────────────────────────────────────────────────────┘
```

#### 핵심 쿼리

**프로젝트 목록 (메인 테이블):**
```sql
SELECT
  p.project_code,
  p.project_name,
  c.client_name,
  p.project_status,
  p.first_shipment_date,
  p.last_shipment_date,
  p.lead_time_days,
  u.display_name AS cx_specialist
FROM shared.projects p
JOIN shared.clients c ON c.id = p.client_id
LEFT JOIN shared.users u ON u.id = p.cx_specialist_id
ORDER BY p.project_code DESC;
```

**상태별 KPI (카드):**
```sql
SELECT
  project_status,
  COUNT(*) AS count
FROM shared.projects
GROUP BY project_status;
```

**프로젝트별 진행 단계 요약:**
```sql
-- 프로젝트 코드로 필터: {{ project_table.selectedRow.data.id }}
WITH po_stats AS (
  SELECT project_id, COUNT(*) AS po_count,
    COUNT(*) FILTER (WHERE po_status = 'closed') AS po_closed
  FROM mm.purchase_orders GROUP BY project_id
),
gr_stats AS (
  SELECT po.project_id, COUNT(*) AS gr_count
  FROM mm.goods_receipts gr
  JOIN mm.purchase_orders po ON po.id = gr.po_id
  GROUP BY po.project_id
),
prod_stats AS (
  SELECT project_id, status AS prod_status,
    planned_qty, completed_qty
  FROM pp.production_orders
),
tms_stats AS (
  SELECT project_id,
    COUNT(*) FILTER (WHERE status = 'completed') AS delivered
  FROM tms.transportation_requirements GROUP BY project_id
)
SELECT
  COALESCE(pos.po_count, 0) AS total_po,
  COALESCE(pos.po_closed, 0) AS closed_po,
  COALESCE(grs.gr_count, 0) AS total_gr,
  ps.prod_status,
  ps.planned_qty,
  ps.completed_qty,
  COALESCE(ts.delivered, 0) AS deliveries_done
FROM shared.projects p
LEFT JOIN po_stats pos ON pos.project_id = p.id
LEFT JOIN gr_stats grs ON grs.project_id = p.id
LEFT JOIN prod_stats ps ON ps.project_id = p.id
LEFT JOIN tms_stats ts ON ts.project_id = p.id
WHERE p.id = {{ project_table.selectedRow.data.id }};
```

---

### App 2: 구매/발주 관리

**용도:** PO 생성/조회, 입고 처리, 검수, 반품 (구매 담당자)

#### 화면 구성

```
┌─────────────────────────────────────────────────────┐
│  [탭: PO 목록 | 입고 대기 | 검수 | 반품]             │
├─────────────────────────────────────────────────────┤
│  [PO 목록 탭]                                        │
│  PO번호 | 프로젝트 | 공급업체 | 상태 | 발주일 | 금액  │
│  PO-001  PRJ-001   텀블러월드  closed  1/05  1.5M   │
│  PO-029  PRJ-022   전자기기도매 partial 3/05  4.5M   │
│                                                     │
│  [+ 신규 발주] 버튼 → 발주 입력 모달                  │
├─────────────────────────────────────────────────────┤
│  [입고 대기 탭]                                      │
│  받아야 할 PO 목록 + [입고 처리] 버튼                 │
├─────────────────────────────────────────────────────┤
│  [검수 탭]                                           │
│  GR별 검수 결과 + 불량 수량 입력                      │
└─────────────────────────────────────────────────────┘
```

#### 핵심 쿼리

**PO 목록:**
```sql
SELECT
  po.po_number,
  p.project_code,
  p.project_name,
  v.vendor_name,
  po.po_status,
  po.order_date,
  SUM(poi.total_amount) AS total_amount
FROM mm.purchase_orders po
JOIN shared.projects p ON p.id = po.project_id
JOIN shared.vendors v ON v.id = po.vendor_id
LEFT JOIN mm.purchase_order_items poi ON poi.po_id = po.id
GROUP BY po.id, p.project_code, p.project_name, v.vendor_name
ORDER BY po.order_date DESC;
```

**입고 대기 (received 아닌 PO만):**
```sql
SELECT
  po.po_number,
  poi.line_number,
  pt.parts_name,
  poi.order_qty,
  COALESCE(poi.received_qty, 0) AS received_qty,
  poi.order_qty - COALESCE(poi.received_qty, 0) AS remaining_qty
FROM mm.purchase_order_items poi
JOIN mm.purchase_orders po ON po.id = poi.po_id
JOIN shared.parts_master pt ON pt.id = poi.parts_id
WHERE po.po_status NOT IN ('closed', 'cancelled')
  AND poi.order_qty > COALESCE(poi.received_qty, 0)
ORDER BY po.order_date;
```

**입고 처리 (INSERT — GR 생성):**
```sql
-- Retool Form → INSERT (불변 원장 원칙: INSERT ONLY)
INSERT INTO mm.goods_receipts (
  id, gr_number, po_id, po_item_id, parts_id,
  storage_bin_id, batch_id, movement_type,
  received_qty, accepted_qty, rejected_qty,
  unit_cost, total_cost,
  receipt_date, posting_date,
  inspection_result, created_by
) VALUES (
  gen_random_uuid(),
  {{ gr_number_input.value }},
  {{ po_select.value }},
  {{ poi_select.value }},
  {{ parts_select.value }},
  {{ bin_select.value }},
  {{ batch_select.value }},
  '101',  -- 표준 입고
  {{ received_qty.value }},
  {{ accepted_qty.value }},
  {{ rejected_qty.value }},
  {{ unit_cost.value }},
  {{ received_qty.value }} * {{ unit_cost.value }},
  CURRENT_DATE,
  CURRENT_DATE,
  {{ inspection_result.value }},
  {{ current_user.id }}
);
```

---

### App 3: 창고/재고 관리

**용도:** 실시간 재고 현황, 재고 이동, 실사 (창고 담당자)

#### 핵심 쿼리

**재고 현황 (품목별 합산):**
```sql
SELECT
  pt.parts_code,
  pt.parts_name,
  w.warehouse_code,
  sb.bin_code,
  q.stock_type,
  q.physical_qty,
  q.reserved_qty,
  q.available_qty,
  b.batch_number,
  b.unit_cost
FROM wms.quants q
JOIN shared.parts_master pt ON pt.id = q.parts_id
JOIN wms.storage_bins sb ON sb.id = q.storage_bin_id
JOIN wms.warehouses w ON w.id = sb.warehouse_id
LEFT JOIN wms.batches b ON b.id = q.batch_id
WHERE q.physical_qty > 0
ORDER BY pt.parts_code, w.warehouse_code;
```

**재고 이동 내역:**
```sql
SELECT
  sm.movement_number,
  sm.movement_type,
  CASE sm.movement_type
    WHEN '101' THEN '입고'
    WHEN '102' THEN '입고취소'
    WHEN '201' THEN '출고(소비)'
    WHEN '261' THEN '생산출고'
    WHEN '301' THEN '창고이전'
    WHEN '601' THEN '납품출고'
    WHEN '161' THEN '고객반품'
    WHEN '701' THEN '실사조정(+)'
    WHEN '702' THEN '실사조정(-)'
  END AS movement_desc,
  pt.parts_name,
  sm.quantity,
  sm.unit_cost_at_movement,
  sm.posting_date,
  sm.status,
  sm.is_reversal
FROM mm.stock_movements sm
JOIN shared.parts_master pt ON pt.id = sm.parts_id
ORDER BY sm.posting_date DESC;
```

**음수 재고 감지 (경고):**
```sql
SELECT
  pt.parts_code,
  pt.parts_name,
  w.warehouse_code,
  q.physical_qty AS current_stock
FROM wms.quants q
JOIN shared.parts_master pt ON pt.id = q.parts_id
JOIN wms.storage_bins sb ON sb.id = q.storage_bin_id
JOIN wms.warehouses w ON w.id = sb.warehouse_id
WHERE q.physical_qty < 0;
```

---

### App 4: 생산/조립 관리

**용도:** 생산지시 → BOM 자재 출고 → 조립 진행 → 완료 보고 (생산 담당자)

#### 핵심 쿼리

**생산 오더 현황:**
```sql
SELECT
  po.order_number,
  p.project_code,
  p.project_name,
  g.goods_name,
  po.status,
  po.planned_start_date,
  po.planned_end_date,
  po.planned_qty,
  po.completed_qty,
  ROUND(po.completed_qty::numeric / NULLIF(po.planned_qty, 0) * 100) AS progress_pct,
  wc.wc_name AS work_center
FROM pp.production_orders po
JOIN shared.projects p ON p.id = po.project_id
LEFT JOIN shared.goods_master g ON g.id = po.goods_id
LEFT JOIN pp.work_centers wc ON wc.id = po.work_center_id
ORDER BY
  CASE po.status
    WHEN 'in_progress' THEN 1
    WHEN 'released' THEN 2
    WHEN 'planned' THEN 3
    WHEN 'completed' THEN 4
  END;
```

**BOM 자재 소요 (선택한 생산오더의 구성품):**
```sql
SELECT
  bi.component_qty AS required_per_unit,
  bi.component_qty * po.planned_qty AS total_required,
  pt.parts_name,
  pt.parts_code,
  COALESCE(poc.issued_qty, 0) AS issued,
  bi.component_qty * po.planned_qty - COALESCE(poc.issued_qty, 0) AS remaining
FROM pp.bom_items bi
JOIN shared.parts_master pt ON pt.id = bi.parts_id
JOIN pp.production_orders po ON po.bom_id = bi.bom_id
LEFT JOIN pp.production_order_components poc
  ON poc.production_order_id = po.id AND poc.parts_id = bi.parts_id
WHERE po.id = {{ production_table.selectedRow.data.id }};
```

---

### App 5: 배송/물류 관리

**용도:** 배송 요청 → 배차 → 출고 → 배송 추적 (물류 담당자)

#### 핵심 쿼리

**배송 현황 전체:**
```sql
SELECT
  tr.tr_number,
  p.project_code,
  p.project_name,
  tr.delivery_type,
  tr.recipient_name,
  tr.delivery_address,
  tr.status AS request_status,
  fo.fo_number,
  fo.shipping_status,
  cr.carrier_name,
  fo.actual_departure,
  fo.actual_arrival,
  fo.total_freight_cost
FROM tms.transportation_requirements tr
JOIN shared.projects p ON p.id = tr.project_id
LEFT JOIN tms.freight_orders fo ON fo.tr_id = tr.id
LEFT JOIN tms.carriers cr ON cr.id = fo.carrier_id
ORDER BY tr.required_date DESC;
```

**배차 일정:**
```sql
SELECT
  ds.schedule_date,
  cr.carrier_name,
  cr.carrier_type,
  ds.is_overbooked,
  COUNT(fo.id) AS assigned_orders
FROM tms.dispatch_schedules ds
JOIN tms.carriers cr ON cr.id = ds.carrier_id
LEFT JOIN tms.freight_orders fo
  ON fo.carrier_id = ds.carrier_id
  AND fo.planned_departure::date = ds.schedule_date
WHERE ds.schedule_date >= CURRENT_DATE
GROUP BY ds.id, cr.carrier_name, cr.carrier_type
ORDER BY ds.schedule_date;
```

---

### App 6: 회계 조회

**용도:** 분개 내역 조회 + 더존 동기화 상태 확인 (경리/회계 담당자)

#### 핵심 쿼리

**분개 내역:**
```sql
SELECT
  ae.entry_number,
  ae.entry_date,
  ae.entry_type,
  da.account_code AS debit_code,
  da.account_name AS debit_name,
  ca.account_code AS credit_code,
  ca.account_name AS credit_name,
  ae.amount,
  ae.status,
  ae.douzone_slip_no,
  ae.is_reversal
FROM finance.accounting_entries ae
JOIN shared.gl_accounts da ON da.id = ae.debit_account_id
JOIN shared.gl_accounts ca ON ca.id = ae.credit_account_id
ORDER BY ae.entry_date DESC, ae.entry_number DESC;
```

**더존 동기화 현황:**
```sql
SELECT
  ae.entry_number,
  ae.entry_type,
  ae.amount,
  dsl.sync_status,
  dsl.douzone_slip_no,
  dsl.synced_at,
  dsl.error_message
FROM finance.douzone_sync_log dsl
JOIN finance.accounting_entries ae ON ae.id = dsl.entry_id
ORDER BY dsl.created_at DESC;
```

**기간 마감 현황:**
```sql
SELECT
  pc.period,
  pt.parts_name,
  w.warehouse_code,
  pc.closing_qty,
  pc.closing_value,
  pc.unit_cost,
  pc.is_closed
FROM finance.period_closes pc
JOIN shared.parts_master pt ON pt.id = pc.parts_id
JOIN wms.warehouses w ON w.id = pc.warehouse_id
ORDER BY pc.period DESC, pt.parts_code;
```

---

### App 7: 마스터 데이터 관리

**용도:** 고객/공급업체/품목/BOM 조회 및 신규 등록 (관리자)

#### 핵심 쿼리

**고객 목록:**
```sql
SELECT client_code, client_name, business_reg_number,
       contact_person, contact_email, status
FROM shared.clients ORDER BY client_code;
```

**공급업체 목록:**
```sql
SELECT vendor_code, vendor_name, vendor_type,
       douzone_vendor_code, is_stock_vendor, status
FROM shared.vendors ORDER BY vendor_code;
```

**품목 3단계 (Goods → Items → Parts):**
```sql
-- 완제품 (FERT)
SELECT goods_code, goods_name, material_type_id FROM shared.goods_master;

-- 반제품 (HALB)
SELECT item_code, item_name, production_type FROM shared.item_master;

-- 원자재/포장재 (ROH/VERP)
SELECT parts_code, parts_name, vendor_id,
       reorder_point, min_order_qty, status
FROM shared.parts_master ORDER BY parts_code;
```

**BOM 구성 조회:**
```sql
SELECT
  bh.bom_code,
  g.goods_name,
  bh.bom_type,
  bi.component_qty,
  pt.parts_code,
  pt.parts_name,
  bi.item_category
FROM pp.bom_headers bh
LEFT JOIN shared.goods_master g ON g.id = bh.goods_id
JOIN pp.bom_items bi ON bi.bom_id = bh.id
JOIN shared.parts_master pt ON pt.id = bi.parts_id
ORDER BY bh.bom_code, bi.id;
```

---

## 4. 권한/보안 설계

### Retool 사용자 그룹

| 그룹 | 접근 앱 | 권한 수준 |
|------|---------|----------|
| **관리자** (지수) | 전체 | READ + WRITE (INSERT) |
| **CX 담당** (채효경, 송지영 등) | App 1, 5 | READ + 배송 상태 UPDATE |
| **구매 담당** | App 1, 2, 7 | READ + PO/GR INSERT |
| **창고 담당** | App 3, 4 | READ + 재고이동/생산확인 INSERT |
| **경리/회계** | App 6 | READ ONLY |
| **경영진** | App 1 대시보드 | READ ONLY |

### Supabase RLS (Row Level Security)

이미 마이그레이션 017에 RLS 정책이 정의되어 있으므로, Retool에서는 **service_role** 키로 접속하되 앱 레벨에서 권한을 제어합니다.

> **선택지:**
> - **Option A (간편):** Retool에서 `service_role` 키 사용 → Retool 그룹 권한으로 제어
> - **Option B (엄격):** Supabase `anon` 키 + RLS → DB 레벨 보안 (추후 전환)

초기에는 **Option A** 권장 (빠른 셋업).

---

## 5. 쓰기 작업 원칙

### INSERT 가능 (Retool Form → SQL)

| 대상 테이블 | 용도 | SAP 이동유형 |
|------------|------|-------------|
| mm.purchase_orders + items | 신규 발주 생성 | — |
| mm.goods_receipts | 입고 처리 | 101 |
| mm.stock_movements | 재고 이동/조정 | 261/301/701 |
| mm.return_orders | 반품 처리 | 122/161 |
| pp.production_orders | 생산지시 생성 | — |
| pp.production_confirmations | 생산 완료 보고 | — |
| tms.transportation_requirements | 배송 요청 | — |
| tms.freight_orders | 배차 실행 | — |
| finance.accounting_entries | 분개 생성 (draft) | — |

### UPDATE 가능 (상태 변경만)

| 대상 테이블 | 허용 필드 |
|------------|----------|
| mm.purchase_orders | po_status |
| pp.production_orders | status, completed_qty |
| tms.freight_orders | shipping_status |
| finance.accounting_entries | status (draft→reviewed→posted) |

### UPDATE/DELETE 절대 금지

| 대상 테이블 | 이유 |
|------------|------|
| mm.goods_receipts | 불변 원장 |
| mm.stock_movements | 불변 원장 — Storno(역분개)로 정정 |
| finance.period_closes (is_closed=TRUE) | 기간 마감 후 수정 불가 |
| wms.quants | 트리거로만 변경 (직접 수정 금지) |

---

## 6. 셋업 체크리스트

### Phase 1: 연결 확인 (30분)
- [ ] Retool 가입 (Free tier)
- [ ] PostgreSQL Resource 생성 (pooler:6543)
- [ ] Test Connection 성공
- [ ] `SELECT COUNT(*) FROM shared.projects;` → 25건 확인

### Phase 2: 대시보드 앱 (1시간)
- [ ] App 1 생성: 프로젝트 대시보드
- [ ] 프로젝트 목록 테이블 + 상태 필터
- [ ] KPI 카드 (상태별 집계)
- [ ] 프로젝트 클릭 → 상세 패널

### Phase 3: 운영 앱 (각 1시간)
- [ ] App 2: 구매/발주 (PO CRUD + GR INSERT)
- [ ] App 3: 창고/재고 (재고 조회 + 이동 내역)
- [ ] App 4: 생산/조립 (생산오더 + BOM)
- [ ] App 5: 배송/물류 (TR + FO)
- [ ] App 6: 회계 조회 (분개 + 더존 동기화)
- [ ] App 7: 마스터 데이터 (고객/업체/품목)

### Phase 4: 권한/배포
- [ ] 사용자 그룹 설정
- [ ] 앱별 접근 권한 설정
- [ ] 팀원 초대

---

## 7. Retool vs 기존 도구 비교

| 기능 | Airtable | NocoDB | Metabase | Retool |
|------|----------|--------|----------|--------|
| 역할 | 운영 입력 (AS-IS) | 테이블 탐색 | 차트/대시보드 | **운영 UI (TO-BE)** |
| 데이터 편집 | ✅ 직접 | ✅ 직접 | ❌ 조회만 | ✅ Form/Button |
| 커스텀 UI | ❌ 제한적 | ❌ 제한적 | ❌ 차트만 | ✅ 자유 설계 |
| 워크플로우 | ❌ | ❌ | ❌ | ✅ (버튼 → 여러 쿼리 체인) |
| 권한 제어 | 기본 | 기본 | 기본 | ✅ 세밀한 그룹 권한 |
| 비용 | 유료 | 무료 | 무료 | Free 5명 / 유료 확장 |

### 전환 로드맵에서의 위치

```
Airtable (운영 입력)  ──webhook──→  NestJS  ──→  Supabase (원장)
                                                    ↑
                                              Retool (운영 UI)
                                              NocoDB (탐색)
                                              Metabase (차트)
```

**최종 목표:** Airtable 입력을 Retool로 대체 → Retool이 유일한 운영 UI
