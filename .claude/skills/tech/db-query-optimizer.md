---
name: db-query-optimizer
description: PostgreSQL 쿼리 최적화 — EXPLAIN ANALYZE, 인덱스 전략, 파티셔닝
---

# PostgreSQL 쿼리 최적화 — DBA 전문가 가이드

> **환경:** PostgreSQL 15+
> **대상:** 고용량 테이블: stock_movements, quants, accounting_entries

---

## 1. EXPLAIN ANALYZE 읽는 법

### 기본 명령어
```sql
EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT)
SELECT * FROM mm.stock_movements WHERE parts_id = '...' AND posting_date >= '2026-01-01';
```

### 핵심 지표
| 항목 | 의미 | 기준값 |
|------|------|--------|
| Seq Scan | 전체 테이블 스캔 | 소규모 OK, 10만건+ 위험 |
| Index Scan | 인덱스 활용 스캔 | 항상 선호 |
| Index Only Scan | 인덱스만으로 결과 반환 | 최적 |
| Bitmap Index Scan | OR 조건/다중 인덱스 | 적절 |
| cost | 시작~총 비용 (상대값) | 낮을수록 좋음 |
| rows | 예상 vs 실제 행 수 | 차이 클수록 통계 부정확 |
| actual time | 실행 시간 (ms) | 100ms 이하 권장 |
| Buffers: shared hit | 캐시 적중 | 높을수록 좋음 |
| Buffers: shared read | 디스크 읽기 | 낮을수록 좋음 |

### 위험 신호
```
Sort Method: external merge  → 메모리 부족, work_mem 증가 필요
Hash Join → Nested Loop     → 대규모 조인 시 성능 저하
Rows Removed by Filter: 99% → 인덱스 누락
```

---

## 2. 인덱스 전략

### B-tree (기본)
```sql
-- PK/FK는 자동 생성
-- 자주 필터링하는 상태 컬럼
CREATE INDEX CONCURRENTLY idx_sm_status_date
  ON mm.stock_movements (status, posting_date);

-- 복합 인덱스: 선택도 높은 컬럼을 앞에
CREATE INDEX CONCURRENTLY idx_po_project_status
  ON mm.purchase_orders (project_id, po_status);
```

**복합 인덱스 순서 규칙:**
1. 등호(=) 조건 컬럼 → 앞
2. 범위(BETWEEN, >=) 조건 컬럼 → 뒤
3. 선택도 높은 컬럼 → 앞

### GIN (배열/전문검색)
```sql
-- ARRAY 타입 컬럼 (defect_codes, outbound_zone)
CREATE INDEX CONCURRENTLY idx_qi_defect_codes
  ON mm.quality_inspections USING GIN (defect_codes);

CREATE INDEX CONCURRENTLY idx_tr_outbound_zone
  ON tms.transportation_requirements USING GIN (outbound_zone);

-- 사용 예시
SELECT * FROM mm.quality_inspections
WHERE defect_codes @> ARRAY['cosmetic_damage'];
```

### Partial Index (조건부)
```sql
-- 활성 레코드만 인덱스 (전체의 20%라면 80% 공간 절약)
CREATE INDEX CONCURRENTLY idx_projects_active
  ON shared.projects (project_code)
  WHERE project_status = 'active';

-- 미완료 이동만
CREATE INDEX CONCURRENTLY idx_sm_pending
  ON mm.stock_movements (posting_date, parts_id)
  WHERE status NOT IN ('completed', 'cancelled');
```

### 불필요한 인덱스 탐지
```sql
SELECT
  schemaname, tablename, indexname,
  idx_scan,           -- 0이면 사용 안 됨
  pg_size_pretty(pg_relation_size(indexrelid)) AS index_size
FROM pg_stat_user_indexes
WHERE schemaname IN ('shared', 'mm', 'wms', 'tms', 'pp', 'finance')
  AND idx_scan = 0
ORDER BY pg_relation_size(indexrelid) DESC;
```

---

## 3. 파티셔닝 전략

### stock_movements (월별 RANGE 파티셔닝)
```sql
-- 파티셔닝 테이블 생성 (기존 테이블 교체 시)
CREATE TABLE mm.stock_movements_partitioned (
  LIKE mm.stock_movements INCLUDING ALL
) PARTITION BY RANGE (posting_date);

-- 월별 파티션 생성
CREATE TABLE mm.stock_movements_2026_01
  PARTITION OF mm.stock_movements_partitioned
  FOR VALUES FROM ('2026-01-01') TO ('2026-02-01');

CREATE TABLE mm.stock_movements_2026_02
  PARTITION OF mm.stock_movements_partitioned
  FOR VALUES FROM ('2026-02-01') TO ('2026-03-01');

-- 자동 파티션 생성 (pg_partman 확장 필요)
```

### 파티셔닝 효과
- WHERE posting_date >= '2026-03-01': 해당 파티션만 스캔
- 월별 데이터 삭제: DROP PARTITION (전체 테이블 VACUUM 불필요)
- 인덱스도 파티션별 분리 → 더 작고 빠름

---

## 4. 커넥션 모니터링

```sql
-- 활성 커넥션 수 확인
SELECT count(*) FROM pg_stat_activity
WHERE state = 'active' AND datname = 'postgres';

-- 장시간 쿼리 확인
SELECT pid, now() - pg_stat_activity.query_start AS duration, query
FROM pg_stat_activity
WHERE state = 'active'
  AND now() - pg_stat_activity.query_start > INTERVAL '30 seconds';
```

---

## 5. 뷰 최적화

### MATERIALIZED VIEW (대시보드용)
```sql
-- 재고 집계 뷰 (자주 조회, 실시간 불필요)
CREATE MATERIALIZED VIEW wms.mv_inventory_summary AS
SELECT
  pt.parts_code, pt.parts_name,
  w.warehouse_code,
  SUM(q.physical_qty) AS total_qty,
  SUM(q.reserved_qty) AS total_reserved,
  SUM(q.available_qty) AS total_available,
  SUM(q.physical_qty * COALESCE(b.unit_cost, 0)) AS total_value
FROM wms.quants q
JOIN shared.parts_master pt ON pt.id = q.parts_id
JOIN wms.storage_bins sb ON sb.id = q.storage_bin_id
JOIN wms.warehouses w ON w.id = sb.warehouse_id
LEFT JOIN wms.batches b ON b.id = q.batch_id
GROUP BY pt.parts_code, pt.parts_name, w.warehouse_code;

-- 인덱스 추가
CREATE UNIQUE INDEX idx_mv_inv_parts_wh
  ON wms.mv_inventory_summary (parts_code, warehouse_code);

-- 리프레시 (stock_movement 트리거에서 호출 또는 크론)
REFRESH MATERIALIZED VIEW CONCURRENTLY wms.mv_inventory_summary;
```

---

## 6. 트리거 성능

### stock_movements → quants 트리거 체인
```
INSERT 1건 → trg_update_quants (quants UPDATE) → trg_create_accounting (entries INSERT)
= 1 INSERT가 실제로 3개 DML 실행
```

### 대량 INSERT 최적화
```sql
-- 방법 1: 트리거 임시 비활성화 (위험 — 수동 정합성 보정 필요)
ALTER TABLE mm.stock_movements DISABLE TRIGGER trg_update_quants;
-- COPY 또는 대량 INSERT 실행
ALTER TABLE mm.stock_movements ENABLE TRIGGER trg_update_quants;
-- 수동으로 quants 재계산 필요

-- 방법 2: 배치 크기 제어 (안전)
-- 1000건씩 나눠서 INSERT → 트리거 부하 분산
-- 각 배치 사이 pg_sleep(0.1) 으로 부하 조절

-- 방법 3: COPY 사용 (가장 빠름, 트리거 실행됨)
COPY mm.stock_movements (movement_number, ...) FROM STDIN WITH CSV;
```

---

## 7. 슬로우 쿼리 진단

### pg_stat_statements (확장 필요)
```sql
SELECT
  calls,
  mean_exec_time::numeric(10,2) AS avg_ms,
  total_exec_time::numeric(10,2) AS total_ms,
  rows,
  LEFT(query, 100) AS query_preview
FROM pg_stat_statements
ORDER BY mean_exec_time DESC
LIMIT 20;
```

### 테이블별 스캔 현황
```sql
SELECT
  schemaname, relname,
  seq_scan,           -- 순차 스캔 횟수
  idx_scan,           -- 인덱스 스캔 횟수
  seq_tup_read,       -- 순차 스캔으로 읽은 행
  idx_tup_fetch,      -- 인덱스로 가져온 행
  n_live_tup,         -- 현재 행 수
  pg_size_pretty(pg_total_relation_size(relid)) AS total_size
FROM pg_stat_user_tables
WHERE schemaname IN ('shared', 'mm', 'wms', 'tms', 'pp', 'finance')
ORDER BY seq_scan DESC
LIMIT 20;
```

### VACUUM/ANALYZE 상태
```sql
SELECT
  schemaname, relname,
  last_vacuum, last_autovacuum,
  last_analyze, last_autoanalyze,
  n_dead_tup,
  n_live_tup
FROM pg_stat_user_tables
WHERE schemaname IN ('shared', 'mm', 'wms', 'tms', 'pp', 'finance')
  AND n_dead_tup > 1000
ORDER BY n_dead_tup DESC;
```

---

## 8. 실전 최적화 사례

### Before: 느린 재고 조회 (3.2초)
```sql
-- Seq Scan on quants + Nested Loop Join
SELECT pt.parts_name, SUM(q.physical_qty)
FROM wms.quants q
JOIN shared.parts_master pt ON pt.id = q.parts_id
JOIN wms.storage_bins sb ON sb.id = q.storage_bin_id
JOIN wms.warehouses w ON w.id = sb.warehouse_id
WHERE w.warehouse_code = 'WH001'
GROUP BY pt.parts_name;
```

### After: 인덱스 추가 후 (45ms)
```sql
-- 1. 복합 인덱스 추가
CREATE INDEX CONCURRENTLY idx_bins_warehouse
  ON wms.storage_bins (warehouse_id);

-- 2. quants에 커버링 인덱스
CREATE INDEX CONCURRENTLY idx_quants_bin_parts
  ON wms.quants (storage_bin_id, parts_id) INCLUDE (physical_qty);

-- 결과: Index Scan + Hash Join으로 전환, 70x 빨라짐
```
