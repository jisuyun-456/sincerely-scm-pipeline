# SAP Movement Types — Full Reference

## WMS (S/4HANA EWM·MM)

| Code | Korean Name | SAP T-Code | Trigger | Reversal |
|------|------------|-----------|---------|---------|
| 101 | 입고 (Goods Receipt) | MIGO | PO 기반 입고 | 102 |
| 102 | 입고 취소 | MIGO | 101 역분개 | — |
| 122 | 반품입고 (Return to Vendor) | MIGO | 공급사 반품 | 123 |
| 201 | 소비출고 (Goods Issue — Cost Center) | MB1A | 소모품 출고 | 202 |
| 261 | 생산출고 (Goods Issue — Production) | MB1A/CO27 | 생산오더 투입 | 262 |
| 311 | 이전 (Transfer — Same Plant) | MB1B | 거점 간 이동 | 312 |
| 315 | 이전 (Plant to Plant) | MB1B | 플랜트 간 | 316 |
| 551 | 폐기 (Scrapping) | MB1A | 재고 폐기 | 552 |
| 601 | 납품출고 (Goods Issue — Delivery) | VL02N | 고객 납품 | 602 |
| 701 | 재고조정 증가 (Physical Inventory +) | MI07 | 실사 차이(+) | 702 |
| 702 | 재고조정 감소 (Physical Inventory -) | MI07 | 실사 차이(-) | 701 |

## TMS 관련 Storno 패턴

- **601 취소 (602)**: 출고된 납품 건 취소 — CO 모듈 매출원가 역분개 포함
- **반품 흐름**: 601 → 122(반품입고) → 검사 → 701/551
- **거점 이전 완성 조건**: 311(발송창고) + 101(수신창고) 양쪽 INSERT 필수

## Storno 원칙 (Immutable Ledger)

> 모든 정정은 역분개 INSERT로만. UPDATE/DELETE 절대 금지.
> Storno 레코드에 원 movement_id + 사유 필수 기록.
