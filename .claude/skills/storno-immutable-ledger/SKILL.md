---
name: storno-immutable-ledger
description: Reference for Storno (역분개) reversal pattern and Immutable Ledger rules. Use when correcting posted movements, reversing journal entries, or advising on inventory adjustment corrections.
allowed-tools: Read
---

# Storno & Immutable Ledger

## Core Principle

**All operational tables are INSERT-ONLY.**
`movement`, `mat_document`, `tms_otif`: no UPDATE, no DELETE — ever.

Corrections = new counter-records only.

## Storno Pattern (역분개 INSERT)

```
원 분개:   Dr. A  /  Cr. B  (movement_id: M001, qty: +100)
Storno:    Dr. B  /  Cr. A  (movement_id: M002, ref: M001, qty: -100, reason: "...")

필수 필드:
  - movement_type: 원 코드 + "R" suffix (e.g. 101 → 102, 601 → 602)
  - ref_movement_id: 원 movement_id
  - storno_reason: 사유 (법적 의무 — 더존 전표 참조번호)
  - storno_date: 정정 일자
  - created_by: 처리자
```

## SAP Standard Reversal Movement Types

| Original | Reversal | Description |
|---------|---------|-------------|
| 101 | 102 | 입고 취소 |
| 601 | 602 | 납품 취소 |
| 201 | 202 | 소비출고 취소 |
| 261 | 262 | 생산출고 취소 |
| 311 | 312 | 이전 취소 |
| 551 | 552 | 폐기 취소 (드물게) |

Account codes → cross-reference `sap-movement-accounts` Skill

## When to Use Storno vs ADJUST

| Situation | Correct Action |
|-----------|---------------|
| 이동유형/수량 오기 (당일) | Storno (102/602 etc.) |
| 이동유형/수량 오기 (이후 기간) | Storno + 재기표 (새 101/601) |
| 사이클카운팅 실사 차이 | ADJUST (701/702) — SK-03 승인 |
| 폐기 후 재판매 가능 판정 | 552 취소 + 재입고 movement |

## Prohibition Checklist

- [ ] movement UPDATE → 금지. Storno만.
- [ ] movement DELETE → 금지. Storno만.
- [ ] 마감된 기간(전기) Storno → D2 tax-accounting-expert 승인 필수
- [ ] 사유 없는 Storno → 금지. 더존 참조번호 + 사유 필수.
- [ ] Supabase WMS/TMS 운영 테이블 write → 금지 (Airtable만)

## Immutable Ledger Audit Trail

Every Storno must be traceable:
`M002.ref_movement_id = M001` + `M002.storno_reason` + `M002.created_by`

This enables: month-end reconciliation, auditor query, KPI backfill accuracy.
