# Supabase — DB 원장 레이어

## 현재 운영 (sap 스키마)
mat_master(parts_code UNIQUE), mat_document(INSERT ONLY 불변 원장), stock_balance(PK: parts_code+location+period), period_close

## TO-BE 설계 (6 스키마, 51 테이블)
shared(마스터 14), mm(구매/QM 10), wms(창고 6), tms(운송 9), pp(생산 6), finance(회계 4)
마이그레이션: migrations/001~017, seed: seed/001~006

## 주요 뷰 (012_views.sql)
wms.v_quant_summary(재고집계), shared.v_available_qty(가용재고), finance 뷰

## 트리거 (014~016)
stock_movements → quants 자동갱신, reservations → reserved_qty, stock_movements → accounting_entries 자동전표

## 알려진 이슈
- 운영 DB(sap 스키마)와 TO-BE(6스키마) 병존 — 전환 시점 미정
- RLS 정책 파일(017) 존재하나 실적용 미확인
- location_stock 뷰 미생성 (feature_list 참조)
