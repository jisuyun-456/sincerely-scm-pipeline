---
description: "WMS 마스터 데이터 관리 에이전트 (SK-01). 품목(Item)·로케이션(Location)·공급사(Supplier) 마스터 데이터의 등록·수정·조회·비활성화를 담당. GS1 GTIN/EAN-13/GLN, APICS CPIM ABC 분류, SAP MM/EWM/SRM 기반 설계. 품목 코드 만들어줘, 로케이션 추가, 공급사 등록, 바코드 형식, 안전재고 설정, 재주문점(ROP) 계산, ABC 등급, PKG/PRD/ASM 품목코드 체계, WH01-ZONE-AISLE 로케이션 ID 체계 관련 내용이 나오면 반드시 이 Skill을 사용할 것. 마스터 데이터 변경 요청이 있을 때도 반드시 사용할 것."
---
# wms-master-data — WMS 마스터 데이터 관리 에이전트 (SK-01)

> 참조: CLAUDE.md의 로케이션 ID 체계, 설계 원칙을 준수할 것.

---

## 역할 정의

품목 마스터(Item), 로케이션 마스터(Location), 공급사 마스터(Supplier/SRM)를 관리하는 전문 에이전트.

**참조 표준**: GS1 GTIN/EAN-13/GLN · APICS CPIM (ABC 분류 · Safety Stock · EOQ) · SAP MM Material Master (MM60) · SAP EWM Storage Bin Master · SAP SRM Vendor Master

**커버 태스크**: T-01 (품목 마스터) · T-02 (로케이션 마스터) · T-03 (공급사 마스터/SRM)

---

## 핵심 도메인 규칙

### 품목 마스터 (Item)
- `item_code` 형식: `{CATEGORY}-{SEQ}` (예: `PKG-001`, `PRD-001`, `ASM-001`)
  - CATEGORY: `PKG`(패키징), `PRD`(생산품), `ASM`(조립품), `RAW`(원자재)
- `barcode`: GS1 EAN-13 (13자리) 또는 QR 형식
- `gtin`: Global Trade Item Number (완성 굿즈 제품만 해당)
- `unit_of_measure`: `PCS` | `BOX` | `ROLL` | `KG` | `SET`
- `abc_class`: 사이클 카운팅 빈도 결정 (A=월2회, B=월1회, C=분기1회) — wms-inventory Sub-agent 3 기준
- `is_fefo`: true면 FEFO 피킹 전략 적용 (유통기한 품목)
- `safety_stock`, `reorder_point`: APICS CPIM 산식 기반으로 SCM팀이 설정

### 로케이션 마스터 (Location)
- `location_id` 형식: `{WH}-{ZONE}-{AISLE}-{RACK}-{LEVEL}-{BIN}`
  - 예: `WH01-STORAGE-A03-R02-L2-B04`
- `zone_type` 5종:
  - `INBOUND_STAGING`: 입하 검수 대기
  - `QC_HOLD`: 불량·검수 중 격리
  - `STORAGE`: 일반 보관
  - `ASSEMBLY`: 굿즈 조립
  - `OUTBOUND_STAGING`: 출하 대기
- `is_active: false` 로케이션은 입고 배정 대상에서 자동 제외
- `gln`: GS1 GLN — 창고/로케이션 글로벌 식별 코드

### 공급사 마스터 (Supplier / SRM)
- `supplier_grade`: A / B / C (SRM 공급사 평가 등급)
  - A: 우수 공급사, B: 일반 공급사, C: 관리 대상
- `defect_rate`: QC 결과 누적 불량률 (QcRecord에서 자동 갱신)
- `lead_time_days`: 발주 → 입하 평균 리드타임 (일)
- `on_time_delivery_rate`: 정시 납품률 (납품 이력에서 자동 갱신)

---

## 핵심 Entity 필드

### Item
```typescript
@Entity('items')
export class Item {
  id: string;                         // UUID PK
  item_code: string;                  // unique — PKG-001, PRD-001
  item_name: string;
  item_type: ItemType;                // RAW_MATERIAL|PACKAGING|FINISHED_GOODS|ASSEMBLY
  barcode: string;                    // nullable — GS1 EAN-13 or QR
  gtin: string;                       // nullable — Global Trade Item Number
  unit_of_measure: string;            // PCS|BOX|ROLL|KG|SET
  safety_stock: number;               // decimal(15,3) — SS = Z × σ × √LT
  reorder_point: number;              // decimal(15,3) — ROP = (일수요 × LT) + SS
  min_order_qty: number;              // decimal(15,3) — EOQ 기반 최소 발주량
  lead_time_days: number;             // int — 조달 리드타임
  abc_class: AbcClass;                // A|B|C
  default_supplier_id: string;        // nullable FK → suppliers
  is_fefo: boolean;                   // default false — FEFO 피킹 적용 여부
  unit_weight_kg: number;             // nullable decimal(10,3)
  unit_volume_cm3: number;            // nullable decimal(10,2)
  is_active: boolean;                 // default true
  created_at: Date;
  updated_at: Date;
  created_by: string;
}
```

### Location
```typescript
@Entity('locations')
export class Location {
  id: string;                         // UUID PK
  location_id: string;                // unique — WH01-STORAGE-A03-R02-L2-B04
  warehouse_code: string;             // WH01
  zone_type: ZoneType;                // INBOUND_STAGING|QC_HOLD|STORAGE|ASSEMBLY|OUTBOUND_STAGING
  zone: string;                       // nullable — A, B, C
  aisle: string;                      // nullable — A01, A02
  rack: string;                       // nullable — R01, R02
  level: string;                      // nullable — L1, L2, L3
  bin: string;                        // nullable — B01, B02
  max_weight_kg: number;              // nullable decimal(10,2)
  max_volume_cm3: number;             // nullable decimal(10,2)
  gln: string;                        // nullable — GS1 GLN
  is_active: boolean;                 // default true
  created_at: Date;
  created_by: string;
}
```

### Supplier
```typescript
@Entity('suppliers')
export class Supplier {
  id: string;                         // UUID PK
  supplier_code: string;              // unique — SUP-001
  supplier_name: string;
  supplier_grade: SupplierGrade;      // A|B|C
  contact_name: string;               // nullable
  contact_email: string;              // nullable
  contact_phone: string;              // nullable
  lead_time_days: number;             // int
  defect_rate: number;                // decimal(5,2) — 누적 불량률 %
  on_time_delivery_rate: number;      // decimal(5,2) — 정시 납품률 %
  country: string;                    // nullable
  is_active: boolean;                 // default true
  created_at: Date;
  updated_at: Date;
  created_by: string;
}
```

---

## 출력 형식 가이드

1. 품목 등록 시: `item_code` 중복 체크 후 생성. `abc_class` 초기값 `C`로 설정
2. 로케이션 등록 시: `location_id` 파싱하여 warehouse_code, zone_type 등 자동 분리
3. 공급사 평가 갱신: QC 불량률 변경 시 `Supplier.defect_rate` 자동 업데이트
4. 비활성화: `is_active = false` 처리 (DELETE 금지 — 이력 데이터 보존)

---

## 금지 사항

- 마스터 데이터 DELETE 금지 (is_active = false로 비활성화)
- `item_code` 형식 규칙 위반 금지
- `location_id` 형식 규칙 위반 금지
- 비활성 로케이션(`is_active = false`)에 입고 배정 금지
