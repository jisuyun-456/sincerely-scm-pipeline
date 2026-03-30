---
description: "TMS 출하·배송 추적 에이전트 (SK-05). Shipment 문서 생성, 택배사(CJ/한진/로젠/우체국) 연동, 배송 이벤트(ShipmentEvent) 추적, POD 배송완료 처리, OTIF 계산 트리거 담당. APICS CLTD, SAP TM Freight Order/Event Management, POD 기반. 출하, 운송장, 택배, 배송 추적, tracking, 배송 완료, 출하 등록, 택배사 연동, SHP 번호, 정시 납품, 배송 이벤트, 택배 집화, 배송 상태 업데이트 관련 내용이 나오면 반드시 이 Skill을 사용할 것."
---
# tms-shipment — TMS 출하·배송 추적 에이전트 (SK-05)

> 참조: CLAUDE.md의 택배사 코드, 설계 원칙을 준수할 것.

---

## 역할 정의

출하 문서(Shipment) 생성, 택배사 연동, 배송 추적 이벤트 관리를 담당하는 전문 에이전트.

**참조 표준**: APICS CLTD · SAP TM Freight Order · SAP TM Event Management · POD (Proof of Delivery)

**커버 태스크**: T-13 (출하 등록·TMS 연동) · T-14 (배송 추적·Event Management)

---

## SAP TM 배송 상태 체계 → NestJS 매핑

```
SAP TM Status          NestJS ShipmentStatus
─────────────────────────────────────────────
Not Started        →   STAGED
In Execution       →   DISPATCHED
In Transit         →   IN_TRANSIT
Out for Delivery   →   OUT_FOR_DELIVERY
Delivered          →   DELIVERED
Exception          →   FAILED | EXCEPTION
```

---

## 출하 표준 흐름

```
PackingRecord.status = COMPLETED (패킹 완료 조건 필수)
    ↓
Shipment 생성 (status: STAGED)
  → carrier_code 선택 (CJ|HANJIN|LOGEN|EPOST)
  → promised_delivery_date 설정 (SLA 기준)
    ↓
택배사 API 연동 (운송장 등록)
  → tracking_number 수신 저장
  → status: STAGED → DISPATCHED
    ↓
ShipmentEvent 수집 (택배사 Webhook 또는 polling)
  → 상태 변화 이벤트 기록
  → ShipmentStatus 자동 업데이트
    ↓
배송 완료 (DELIVERED)
  → actual_delivery_date 기록
  → is_on_time: promised_delivery_date ≥ actual_delivery_date
  → is_in_full: ordered_qty == delivered_qty
  → OTIF 계산 트리거 (Event Emitter)
```

---

## 핵심 도메인 규칙

### Shipment 생성 조건
- `PackingRecord.status = COMPLETED` 상태인 패킹 레코드가 있어야 생성 가능
- `shipment_number` 형식: `SHP-YYYYMMDD-NNN`

### 배송 상태 머신
```
STAGED → DISPATCHED → IN_TRANSIT → OUT_FOR_DELIVERY → DELIVERED
                                                     → FAILED
                                 → EXCEPTION
```
- 상태는 순방향 전진만 허용 (이전 상태로 되돌리기 금지)
- `DELIVERED` 전환 시 `actual_delivery_date` 자동 기록

### OTIF 계산 트리거
- `Shipment.status → DELIVERED` 이벤트에서 자동 계산
- `is_on_time = actual_delivery_date ≤ promised_delivery_date`
- `is_in_full = total_delivered_qty == total_ordered_qty`
- `OtifRecord` 자동 생성 (tms/otif 모듈)

### ShipmentEvent 유형
| event_type | 의미 |
|---|---|
| `PICKUP` | 택배사 집화 완료 |
| `HUB_ARRIVAL` | 허브(터미널) 도착 |
| `HUB_DEPARTURE` | 허브(터미널) 출발 |
| `LOCAL_ARRIVAL` | 배송 지점 도착 |
| `OUT_FOR_DELIVERY` | 배송 출발 |
| `DELIVERED` | 배송 완료 (POD) |
| `EXCEPTION` | 배송 오류 (주소불명, 수취인 없음 등) |
| `RETURNED` | 반송 처리 |

---

## 핵심 Entity 필드

### Shipment
```typescript
@Entity('shipments')
export class Shipment {
  id: string;                         // UUID PK
  shipment_number: string;            // unique — SHP-YYYYMMDD-NNN
  status: ShipmentStatus;             // STAGED|DISPATCHED|IN_TRANSIT|OUT_FOR_DELIVERY|DELIVERED|FAILED|EXCEPTION
  wave_id: string;                    // FK → waves
  packing_record_id: string;          // FK → packing_records
  carrier_code: string;               // CJ|HANJIN|LOGEN|EPOST
  tracking_number: string;            // nullable — 택배사 운송장 번호
  recipient_name: string;
  recipient_address: string;
  recipient_phone: string;
  total_ordered_qty: number;          // decimal(15,3)
  total_delivered_qty: number;        // decimal(15,3) default 0
  total_weight_kg: number;            // nullable decimal(10,2)
  dispatched_at: Date;                // timestamptz — 출하 시각
  promised_delivery_date: Date;       // date — SLA 약속 배송일
  actual_delivery_date: Date;         // nullable timestamptz — 실제 배송 완료
  is_on_time: boolean;                // default false — OTIF OT
  is_in_full: boolean;                // default false — OTIF IF
  notes: string;                      // nullable
  created_at: Date;
  created_by: string;
}
```

### ShipmentEvent
```typescript
@Entity('shipment_events')
export class ShipmentEvent {
  id: string;                         // UUID PK
  shipment_id: string;                // FK → shipments
  event_type: ShipmentEventType;      // PICKUP|HUB_ARRIVAL|HUB_DEPARTURE|LOCAL_ARRIVAL|OUT_FOR_DELIVERY|DELIVERED|EXCEPTION|RETURNED
  event_at: Date;                     // timestamptz — 이벤트 발생 시각
  location_name: string;              // nullable — 이벤트 발생 장소
  carrier_code: string;
  message: string;                    // nullable — 택배사 메시지
  raw_payload: object;                // nullable jsonb — 택배사 원본 응답
  created_at: Date;
  created_by: string;                 // 'SYSTEM' (자동 수집)
}
```

---

## 상태 머신

```
Shipment:
STAGED → DISPATCHED → IN_TRANSIT → OUT_FOR_DELIVERY → DELIVERED
                                                     → FAILED
                    → EXCEPTION
```

---

## 출력 형식 가이드

1. 출하 생성: `POST /tms/shipment` — packing_record_id + carrier_code + recipient 정보 입력
2. 배송 추적 업데이트: `POST /tms/tracking/webhook` — 택배사 Webhook 수신 처리
3. DELIVERED 전환 시: `actual_delivery_date` 자동 기록 → OTIF 계산 이벤트 emit
4. CarrierAdapter 패턴으로 택배사별 API 차이 추상화 (`CjAdapter`, `HanjinAdapter` 등)

---

## 금지 사항

- `PackingRecord.status = COMPLETED` 조건 미충족 시 Shipment 생성 금지
- 배송 상태 역방향 전환 금지 (예: DELIVERED → IN_TRANSIT)
- `promised_delivery_date` 없이 Shipment 생성 금지
- `actual_delivery_date` 수동 역산 입력 금지 (DELIVERED 이벤트 수신 시 자동 기록)
