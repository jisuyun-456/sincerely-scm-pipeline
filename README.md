# Sincerely SCM — Airtable → Supabase → NocoDB/Metabase 파이프라인

## 개요

Airtable Sync 베이스(`자재테스트_지수`)의 재고·이동·주문 데이터를 Supabase(PostgreSQL)에 적재하고,
NocoDB로 테이블 탐색/편집, Metabase로 대시보드·KPI 시각화하는 SCM 데이터 파이프라인.

## 워크플로우

```
┌─ 데이터 소스 ─────────────────────────────────────────────────────┐
│                                                                   │
│  Airtable (WMS+TMS Base)                                          │
│  ├── material_stock (재고 원장)                                     │
│  ├── movement (이동 트랜잭션)                                       │
│  ├── order (주문/발주)                                              │
│  └── project (프로젝트 마스터)                                      │
│                                                                   │
└───────┬───────────────────────────────────────────────────────────┘
        │
        │  ① GitHub Actions (매일 09:00 KST)
        │     snapshot.yml → pipeline.py
        │     Extract → Transform → Load
        │
        ▼
┌─ 불변 원장 (Supabase PostgreSQL) ─────────────────────────────────┐
│                                                                   │
│  스냅샷 테이블          │  Generated Columns     │  Analysis Views │
│  ├── material_stock     │  calc_system_qty       │  v_latest_stock │
│  ├── movement           │  system_qty_mismatch   │  v_stock_trend  │
│  ├── orders             │                        │  v_stock_summary│
│  ├── project            │                        │                 │
│  └── snapshot_log       │                        │                 │
│                                                                   │
│  TO-BE: 6 Schema 51 Tables (shared/mm/wms/tms/pp/finance)        │
│                                                                   │
└───────┬──────────────────────────┬────────────────────────────────┘
        │                          │
        │  ② NocoDB 연결            │  ③ Metabase 연결
        │     Supabase Direct       │     Supabase Direct
        │                          │
        ▼                          ▼
┌─ 테이블 탐색/편집 ──┐    ┌─ 대시보드/KPI ──────────┐
│                     │    │                         │
│  NocoDB             │    │  Metabase               │
│  (localhost:8080)   │    │  (localhost:3000)        │
│                     │    │                         │
│  • 테이블 CRUD      │    │  • 재고 현황 대시보드    │
│  • 필터/정렬/뷰     │    │  • 이동유형별 추이 차트  │
│  • Airtable 대체    │    │  • 전산재고 불일치 알림  │
│                     │    │  • OTIF KPI 시각화      │
└─────────────────────┘    └─────────────────────────┘
```

## 설정

### 1. Supabase 스키마 생성
Supabase SQL Editor에서 `sql/001_create_schema.sql` 실행

### 2. GitHub Secrets 설정
Repository → Settings → Secrets and variables → Actions → **New repository secret**:

| Secret Name | 값 |
|---|---|
| `AIRTABLE_PAT` | `pat_xxxxx` (Airtable Personal Access Token) |
| `SUPABASE_DB_URL` | `postgresql://postgres:비밀번호@db.xxx.supabase.co:5432/postgres` |

### 3. GitHub Actions 파이프라인

| Workflow | 스케줄 | 용도 |
|---|---|---|
| `snapshot.yml` | 매일 09:00 KST | Airtable → Supabase 스냅샷 |
| `wms_weekly_report.yml` | 매주 월요일 | 주간 WMS 리포트 |
| `wms_monthly_report.yml` | 매월 1일 | 월간 WMS 리포트 |
| `generate_pdf.yml` | Make webhook | 출고확인서/거래명세서 PDF |
| `deploy_pages.yml` | 수동/자동 | 대시보드 GitHub Pages 배포 |

### 4. NocoDB + Metabase (Docker)
```bash
cd /c/Users/yjisu/Desktop/SCM_WORK
docker compose up -d
```

| 서비스 | URL | 역할 |
|---|---|---|
| NocoDB | `http://localhost:8080` | 테이블 탐색/편집 (Airtable 대체) |
| Metabase | `http://localhost:3000` | 대시보드/KPI 시각화 |

Supabase 연결: 각 서비스에서 PostgreSQL Direct Connection 설정

## 로컬 실행

```bash
cp .env.example .env  # 환경변수 설정
pip install -r requirements.txt
python pipeline.py --dry-run        # 테스트
python pipeline.py                  # 전체 스냅샷
python pipeline.py --table material # 특정 테이블만
```

## 파일 구조

```
sincerely-scm-pipeline/
├── .github/workflows/
│   ├── snapshot.yml               # Airtable→Supabase 일일 스냅샷
│   ├── wms_weekly_report.yml      # 주간 리포트
│   ├── wms_monthly_report.yml     # 월간 리포트
│   ├── generate_pdf.yml           # PDF 생성 (Make webhook)
│   └── deploy_pages.yml           # GitHub Pages 배포
├── snapshot/
│   ├── pipeline.py                # 메인 ETL 파이프라인
│   ├── config/
│   │   └── field_mapping.py       # Airtable↔Supabase 필드 매핑
│   └── sql/
│       ├── 001_create_schema.sql  # Supabase DDL
│       └── 002_analysis_queries.sql
├── pages/
│   ├── dashboard.html             # 출하 탭 대시보드 (Chart.js)
│   └── generate_scm_report.py     # 리포트 생성
├── pdf/
│   └── generate_pdf.py            # reportlab PDF 렌더링
├── tms/
│   └── delivery_routing.py        # 배송 라우팅
├── wms/
│   └── sincerely_wms_weekly_report.py
├── requirements.txt
├── .env.example
└── README.md
```

## 핵심 기능

### Generated Column — 자동 검증
`material_stock` 테이블에 PostgreSQL Generated Column 2개가 자동 계산됨:

- **`calc_system_qty`**: 구성요소로부터 전산재고를 역산
  `= 구매조달 + 생산산출 + 조립산출 + 이동입고 + 조정입고 − 생산투입 − 조립투입 − 이동출고 − 고객납품 − 조정출고`

- **`system_qty_mismatch`**: Airtable 전산재고 vs 공식계산 차이
  `= system_qty − calc_system_qty`

> `system_qty_mismatch != 0`인 레코드가 **Automation 계산 오류 대상**

### Analysis Views
- `v_latest_stock_mismatch`: 최신 스냅샷의 불일치 항목
- `v_latest_stock_summary`: 위치별 재고 총괄
- `v_stock_trend`: 파츠별 일간 재고 추이

### NocoDB 활용
- Airtable과 동일한 스프레드시트 UI로 Supabase 테이블 직접 탐색
- 뷰·필터·정렬 생성으로 운영 데이터 즉시 확인
- Airtable 의존도 점진적 제거

### Metabase 활용
- 재고 현황 대시보드 (위치별·품목별)
- 이동유형별 트렌드 차트 (일별/주별/월별)
- 전산재고 불일치 자동 알림 (SQL Alert)
- OTIF KPI 시각화

## 매핑 테이블 요약

| Airtable 테이블 | Supabase 테이블 | 핵심 필드 수 | 용도 |
|---|---|---|---|
| material(parts-stock) | material_stock | 37개 | 재고 원장 |
| movement | movement | 31개 | 이동 트랜잭션 |
| order | orders | 36개 | 주문/발주 |
| project | project | 11개 | 프로젝트 마스터 |

## 전환 로드맵

```
현재: Airtable → GitHub Actions → Supabase (스냅샷)
                                      ↓
                              NocoDB (테이블 탐색)
                              Metabase (대시보드)

향후: Airtable → NestJS 백엔드 → Supabase 6스키마 51테이블
                                      ↓
                              NocoDB + Metabase
                              더존 아마란스10 연계
```
