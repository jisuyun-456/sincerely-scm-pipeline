# Supabase — DB 원장 레이어

## 현재 운영 (sap 스키마)
mat_master(parts_code UNIQUE), mat_document(INSERT ONLY 불변 원장), stock_balance(PK: parts_code+location+period), period_close

## TO-BE 설계 (6 스키마, 55 테이블)
shared(마스터 14), mm(구매/QM 13), wms(창고 7), tms(운송 10), pp(생산 7), finance(회계 4)
마이그레이션: migrations/001~018, seed: seed/001~006

## 주요 뷰 (012_views.sql + 018)
wms.v_quant_summary(재고집계), shared.v_available_qty(가용재고), finance 뷰
mm.v_qc_defect_trend(QC불량률 트렌드), mm.v_defect_pareto(파레토분석)
tms.v_otif_trend(OTIF 성과 트렌드), shared.v_reorder_alerts(안전재고 알림)
mm.v_current_prices(현재 유효 단가), mm.v_parts_without_prices(단가 미입력 자재)

## 트리거 (014~016)
stock_movements → quants 자동갱신, reservations → reserved_qty, stock_movements → accounting_entries 자동전표

## 알려진 이슈
- 운영 DB(sap 스키마)와 TO-BE(6스키마) 병존 — 전환 시점 미정
- RLS 정책 파일(017) 존재하나 실적용 미확인
- location_stock 뷰 미생성 (feature_list 참조)
