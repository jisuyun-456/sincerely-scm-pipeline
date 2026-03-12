# Sincerely SCM — Airtable → Supabase 재고 스냅샷 파이프라인

## 개요

Airtable Sync 베이스(`자재테스트_지수`)의 재고 데이터를 Supabase(PostgreSQL)에 일일 스냅샷으로 적재하는 파이프라인.  
재고 로직 분석 결과 발견된 **전산재고 불일치, Automation 계산 오차, 실사 gap**을 SQL로 체계적으로 검출.

## 아키텍처

```
Airtable (Sync Base)          Supabase (PostgreSQL)
┌─────────────────┐           ┌─────────────────────┐
│ material_stock   │──Extract──│ material_stock        │
│ movement        │──Transform│ movement             │
│ order           │──Load────▶│ orders               │
│ project         │           │ project              │
└─────────────────┘           │ snapshot_log         │
                              │                     │
                              │ + Generated Columns │
                              │   calc_system_qty   │
                              │   system_qty_mismatch│
                              │                     │
                              │ + Analysis Views    │
                              │   v_latest_stock_... │
                              └─────────────────────┘
```

## 설정 (GitHub Actions)

### 1. Supabase 스키마 생성
Supabase SQL Editor에서 `sql/001_create_schema.sql` 실행

### 2. GitHub Secrets 설정
Repository → Settings → Secrets and variables → Actions → **New repository secret**:

| Secret Name | 값 |
|---|---|
| `AIRTABLE_PAT` | `pat_xxxxx` (Airtable Personal Access Token) |
| `SUPABASE_DB_URL` | `postgresql://postgres:비밀번호@db.xxx.supabase.co:5432/postgres` |

### 3. 실행
- **자동**: 매일 오전 9시(KST) 자동 실행
- **수동**: Actions 탭 → `SCM Inventory Snapshot Pipeline` → Run workflow

## 로컬 실행 (선택사항)

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
├── pipeline.py                    # 메인 ETL 파이프라인
├── config/
│   └── field_mapping.py           # Airtable↔Supabase 필드 매핑
├── sql/
│   ├── 001_create_schema.sql      # Supabase DDL (테이블+인덱스+뷰)
│   └── 002_analysis_queries.sql   # 분석용 SQL 쿼리 모음
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

→ `system_qty_mismatch != 0`인 레코드가 **Automation 계산 오류 대상**

### Analysis Views
- `v_latest_stock_mismatch`: 최신 스냅샷의 불일치 항목
- `v_latest_stock_summary`: 위치별 재고 총괄
- `v_stock_trend`: 파츠별 일간 재고 추이

## 매핑 테이블 요약

| Airtable 테이블 | Supabase 테이블 | 핵심 필드 수 | 용도 |
|---|---|---|---|
| material(parts-stock) | material_stock | 37개 | 재고 원장 |
| movement | movement | 31개 | 이동 트랜잭션 |
| order | orders | 36개 | 주문/발주 |
| project | project | 11개 | 프로젝트 마스터 |
