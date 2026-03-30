# NestJS Backend — 웹훅 수신 + Shadow Ledger

## 현재 상태
- 런타임: PM2 (sincerely-scm) + ngrok 터널 → Railway 전환 예정
- 활성 모듈: SupabaseModule, InventoryModule (webhook 수신 + 불변 원장)
- 비활성 모듈: Master, WMS, TMS, Return, Analytics (TypeORM 미연결)

## 핵심 엔드포인트
- POST /inventory/movement — 에어테이블 webhook → mat_document INSERT + stock_balance UPSERT
- POST /inventory/storno — 취소 전표 역분개 처리

## 프로젝트 경로
테스트/sincerely-scm/src/ (inventory/, wms/, tms/, master/, return/, analytics/)

## 알려진 이슈
- app.module.ts: TypeORM 주석 처리됨 (Supabase Connection Pooler URL 미확보)
- Storno 시 원본 전표 status UPDATE → INSERT ONLY 원칙 위반 가능성 검토 필요
- MOVEMENT_TYPE_MAP에 '생산샘플' 미등록 → skipped_unknown_type 발생

## 향후 방향
Railway 배포 → 백필 에러 해결 → mat_master 자동등록 → TypeORM 연결 → 전체 모듈 활성화
