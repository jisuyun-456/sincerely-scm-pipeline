# Sincerely SCM — Airtable WMS + TMS 운영 시스템

신시어리 포장재 물류팀 SCM 시스템. Airtable을 운영 입력 레이어로, Fly.io Flask API + GitHub Actions로 PDF 자동 생성 및 주간 KPI 분석을 수행한다.

## 시스템 구성

```
┌─ 운영 입력 레이어 ────────────────────────────────────────────────┐
│                                                                  │
│  Airtable WMS Base (appLui4ZR5HWcQRri)                          │
│  ├── movement (입출고 트랜잭션 — INSERT ONLY)                      │
│  ├── material_stock (재고 원장)                                    │
│  ├── order / order_item (발주·입고)                                │
│  └── logistics_release (출고지시 + 출고서류 PDF 트리거)             │
│                                                                  │
│  Airtable TMS Base (app4x70a8mOrIKsMf)                          │
│  ├── shipment (배차·배송)                                         │
│  ├── delivery_event (배송 이벤트 로그)                             │
│  └──배송SLA / 배차일지 / 클레임 / ...                              │
│                                                                  │
│  Airtable Barcode Base (app4LvuNIDiqTmhnv)                       │
│  └── picking_docs / pkg_schedule / ... (라벨·피킹리스트)           │
│                                                                  │
└──────────────────────┬───────────────────────────────────────────┘
                       │
          Airtable Interface "Open URL" 버튼
                       │
                       ▼
┌─ PDF 생성 서버 (Fly.io) ──────────────────────────────────────────┐
│                                                                  │
│  sincerely-pdf-delicate-glade-4880.fly.dev                       │
│  api/app.py (Flask)                                              │
│                                                                  │
│  POST /generate-tms-pdf        출고확인서 (TMS)                   │
│  POST /generate-wms-pdf        출고서류 3종 (WMS)                  │
│  POST /generate-barcode-pdf    바코드 라벨                         │
│  POST /generate-pkg-label      투입자재 라벨                       │
│                                                                  │
│  GET  /trigger-wms-pdf         WMS 출고서류 Interface 버튼용        │
│  GET  /trigger-tms-pdf         TMS 출고확인서 Interface 버튼용      │
│  GET  /trigger-pkg-label       투입자재 라벨 Interface 버튼용        │
│  GET  /trigger-customer-goods-label  고객물품 라벨                  │
│  GET  /trigger-inbound-label   입고 라벨                           │
│  GET  /trigger-pkg-return-sheet  반품 구분표                       │
│  GET  /trigger-barcode-출고확인서 / 피킹리스트 / 라벨지             │
│  GET  /health                                                    │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘

┌─ 주간 자동 분석 (GitHub Actions) ────────────────────────────────┐
│                                                                  │
│  weekly-full-pipeline.yml (매주 월 08:30 KST)                    │
│  1. TMS 주간 백필 (약속납기일, 구간유형 등)                          │
│  2. TMS AutoResearch → _AutoResearch/SCM/outputs/TMS-YYYY-Wxx   │
│  3. WMS SAP 이동유형 백필                                          │
│  4. WMS AutoResearch → _AutoResearch/SCM/outputs/WMS-YYYY-Wxx   │
│  5. Git commit & push                                            │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

## 레포 구조

```
SCM_WORK/
├── api/                        # Fly.io Flask PDF 생성 서버
│   ├── app.py                  # 엔드포인트 정의
│   └── requirements.txt
├── scripts/                    # 운영 Python 스크립트
│   ├── backfill/               # 일회성 백필 스크립트
│   ├── combined_outbound_label.py   # 통합 라벨 V3140 (쉬핑마크+외박스)
│   ├── outer_box_label.py      # 외박스 라벨
│   ├── packing_list.py         # 패킹리스트
│   ├── shipping_mark.py        # 쉬핑마크
│   ├── customer_goods_label.py # 고객물품 라벨
│   ├── inbound_label.py        # 입고 라벨
│   ├── pkg_schedule_label.py   # 투입자재 라벨
│   ├── pkg_return_sheet.py     # 반품 구분표
│   ├── barcode_label.py        # 바코드 라벨 (피킹리스트)
│   ├── 출고확인서_pdf.py        # 출고확인서
│   ├── picking_list_pdf.py     # 피킹리스트 PDF
│   ├── tms_weekly_runner.py    # TMS 주간 AutoResearch
│   ├── wms_weekly_runner.py    # WMS 주간 AutoResearch
│   ├── tms_weekly_backfill.py  # TMS 주간 백필
│   ├── wms_sap_weekly.py       # WMS SAP 이동유형 주간 백필
│   └── zone_classify.py        # 구간유형 분류
├── scm_mcp/                    # Claude Code용 Airtable MCP 서버
├── _AutoResearch/SCM/          # 주간 분석 자동 산출물 (GitHub Actions commit)
│   ├── outputs/                # TMS-YYYY-Wxx.md, WMS-YYYY-Wxx.md
│   └── wiki/                   # log.md, index.md
├── sincerely-meeting-notes/    # 주간 운영 회의록 (GitHub Pages 배포)
├── pages/                      # TMS 대시보드 정적 사이트
├── history/                    # 주간 JSON 데이터 (Pages 참조)
├── docs/                       # Airtable 스키마, 컨텍스트 문서
├── pdf/                        # 비상용 PDF 생성 스크립트 (백업)
├── _archive/                   # 완료된 레거시 (tms/, wms/ Phase0 백필)
├── .github/workflows/
│   ├── weekly-full-pipeline.yml     # TMS+WMS 주간 파이프라인
│   ├── deploy_meeting_notes.yml     # 회의록 GitHub Pages 배포
│   ├── generate_pdf.yml             # 출고확인서 비상 수동 실행
│   └── generate-barcode-pdf.yml     # 바코드 PDF 비상 수동 실행
├── Dockerfile                  # Fly.io 배포용
├── fly.toml                    # Fly.io 설정
└── requirements-autoresearch.txt
```

## 배포

### Fly.io (PDF 서버)
```bash
fly deploy
```

### GitHub Pages (회의록 + 대시보드)
`sincerely-meeting-notes/` 또는 `pages/` 변경 → push → 자동 배포

## 환경 변수

```bash
cp .env.example .env
```

| 변수 | 용도 |
|------|------|
| `AIRTABLE_PAT` | TMS Airtable PAT |
| `AIRTABLE_API_KEY_WMS` | WMS Airtable PAT |
| `AIRTABLE_API_KEY` | Barcode Airtable PAT |
| `WEBHOOK_SECRET` | Fly.io Interface 버튼 인증 토큰 |

## Airtable Interface 버튼 URL 패턴

```
https://sincerely-pdf-delicate-glade-4880.fly.dev/{endpoint}?record_id={RECORD_ID()}&token={WEBHOOK_SECRET}
```

예) 출고서류 3종:
```
"https://sincerely-pdf-delicate-glade-4880.fly.dev/trigger-wms-pdf?record_id=" & RECORD_ID() & "&token=SECRET"
```

## 데이터 정합성 원칙

- **Immutable Ledger**: `movement` / `mat_document` INSERT ONLY, UPDATE/DELETE 금지
- 정정 = Storno(역분개) 또는 보정 레코드
- SAP 이동유형: 101입고 / 201출고 / 261생산출고 / 311이전 / 601납품 / 551폐기 / 122반품입고 / 701조정

## GitHub Actions Secrets

| Secret | 값 |
|--------|---|
| `AIRTABLE_PAT` | TMS 베이스 PAT |
| `AIRTABLE_API_KEY_WMS` | WMS 베이스 PAT |
| `AIRTABLE_API_KEY_TMS` | TMS 출고확인서 PAT |
| `AIRTABLE_barcode_PAT` | Barcode 베이스 PAT |
