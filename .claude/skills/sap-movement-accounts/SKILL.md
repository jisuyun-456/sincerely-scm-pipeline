---
name: sap-movement-accounts
description: Reference for SAP movement type codes (101/201/261/311/601/701/122/551) and K-IFRS / 더존 아마란스10 account mappings. Use when posting movements, validating journal entries, or composing Storno reversals.
allowed-tools: Read
---

# SAP Movement Types & K-IFRS Account Mappings

## Quick Reference

| Movement | Action | Dr | Cr |
|----------|--------|----|----|
| 101 | 입고 (GR) | 재고자산 (1xxx) | 매입채무 (2xxx) |
| 201 | 소비출고 | 소비비용 (5xxx) | 재고자산 (1xxx) |
| 261 | 생산출고 | 재공품 (1xxx) | 재고자산 (1xxx) |
| 311 | 거점 간 이전 | 재고자산(거점B) | 재고자산(거점A) |
| 601 | 납품출고 | 매출원가 (5xxx) | 재고자산 (1xxx) |
| 701 | 재고조정(+) | 재고자산 (1xxx) | 재고평가이익 (4xxx) |
| 702 | 재고조정(-) | 재고평가손실 (5xxx) | 재고자산 (1xxx) |
| 122 | 반품입고 | 재고자산 (1xxx) | 매입환출 (4xxx) |
| 551 | 폐기 | 재고자산평가손실 (5xxx) | 재고자산 (1xxx) |

## 더존 아마란스10 계정코드 체계
- 1xxx — 자산 (재고자산 1400~1499 / 재공품 1410)
- 2xxx — 부채 (매입채무 2100~2199)
- 3xxx — 자본
- 4xxx — 수익 (매출 4000 / 매입환출 4100 / 재고평가이익 4900)
- 5xxx — 비용 (매출원가 5000 / 소비비용 5100 / 재고평가손실 5900)

## Deep Reference
- Full movement type table with SAP T-code mapping → `references/sap-movement-types.md`
- Full K-IFRS account code list (IAS 2 재고자산 기반) → `references/k-ifrs-codes.md`

## Usage Notes
- Storno 역분개: 원 movement 그대로 반대 부호로 INSERT — 절대 UPDATE 금지
- 701/702 조정은 사이클카운팅 확인 후에만 — SK-03 wms-inventory 승인 필수
- 기간마감 전 미결 movement 0건 확인 — D2 tax-accounting-expert 기간마감 체크리스트 참조
