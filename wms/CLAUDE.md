# WMS — 창고관리 모듈

## 창고
에이원지식산업센터 (주 창고), 베스트원. 위치 체계: 구역-로-열-층 (예: A-01-03-2)

## SAP 이동유형 매핑
101 입고 / 102 입고취소 / 201 비용출고 / 261 생산출고 / 311 창고간이전 / 501 기초재고 / 601 고객납품 / 701 재고조정

## 핵심 프로세스
- 입고: Airtable 등록 → pipeline/webhook → mat_document(101) → stock_balance UPSERT
- 출고: 동일 흐름, 방향 반전(201/261/601)
- 반품: 역방향 이동유형(102/202)
- 실사: MI01(문서생성) → MI04(카운트) → MI07(클로징) — 설계 완료, 파이프라인 미완성

## 미완료 작업
- rack 적재율 heatmap: item CBM 데이터 연결 필요
- location_stock 뷰 미생성
- location rollup isValid: false 이슈 (Airtable rollup 정합성)
- NestJS WMS 모듈: src/wms/ 존재하나 app.module.ts에서 비활성화
