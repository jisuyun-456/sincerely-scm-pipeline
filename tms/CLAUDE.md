# TMS — 운송관리 모듈

## 현재 운영 (Airtable 기반)
- 출고확인서/거래명세서 PDF: Make → GitHub Actions → reportlab → GitHub Releases
- CBM 산출: 수동입력 → Product 매칭(83.4%) → 박스파싱 → 미산출 0.0
- Logen 택배 연동: Chrome Extension (logen-tms-extension/)
- OTIF KPI: On Time(약속일 기준) / In Full(요청 대비 실배송)

## TO-BE 방향 (Supabase + NestJS)
- tms 스키마: locations, carriers, freight_orders, dispatch_schedules 등 9테이블
- NestJS TMS 모듈: src/tms/ (shipment/otif/tracking) — TypeORM 연결 후 활성화
- 택배사 API 추상화: CarrierAdapter 패턴 (CJ/한진/로젠/우체국)
- OTIF 자동 계산: Shipment DELIVERED 이벤트 → OtifRecord 자동생성

## 알려진 이슈
- Product 테이블 매칭 실패율 16.6% (변형 표기, 미등록 품목)
- PDF 파이프라인: NestJS 전환 후에도 당분간 현행 유지 (Make+Actions)
