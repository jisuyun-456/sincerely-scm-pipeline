# SCM 배포 가이드 — Supabase → NocoDB → Metabase

> VS Code 사이드 패널용 참조 문서
> 현재 상태: Step 1~3 완료 ✅ | Step 4 진행 중 🔄

---

## 진행 현황

| Step | 내용 | 상태 |
|------|------|------|
| 1 | Supabase 마이그레이션 (51 tables) | ✅ 완료 |
| 2 | Supabase 시드 데이터 (25 projects) | ✅ 완료 |
| 3 | 데이터 검증 쿼리 | ✅ 완료 |
| 4 | Docker 시작 (NocoDB + Metabase) | ✅ 완료 |
| 5 | NocoDB → Supabase 연결 | ✅ 완료 |
| 6 | Metabase → Supabase 연결 | ✅ 완료 |
| 7 | 최종 동작 확인 | ✅ 완료 |

---

## Step 1 — Supabase 마이그레이션 ✅ 완료

파일: `ALL_MIGRATIONS_COMBINED.sql` (202KB, 51 tables, 6 schemas)

생성된 스키마:
- `shared` — Master Data (UoM, GL, BP, 조직, 자재) — 14 tables
- `tms` — Transportation (프로젝트, 발주, 운임, 출고) — 9 tables
- `wms` — Warehouse (재고, 입출고, 실사) — 7 tables
- `mm` — Materials + Quality (GR, 이동, PO) — 10 tables
- `pp` — Production Planning (BOM, 작업지시) — 7 tables
- `finance` — 전표, 원가, 더존 연동 — 4 tables

---

## Step 2 — Supabase 시드 데이터 입력

파일: `ALL_SEEDS_COMBINED.sql` (93KB, PRJ-001~025)

1. [https://supabase.com/dashboard](https://supabase.com/dashboard) → 프로젝트 선택
2. 좌측 메뉴 **SQL Editor** → **New query**
3. `ALL_SEEDS_COMBINED.sql` 전체 내용 복사 붙여넣기
   - VS Code에서 파일 열기 → `Ctrl+A` → `Ctrl+C` → SQL Editor에 `Ctrl+V`
4. **Run** (또는 `Ctrl+Enter`)
5. 하단에 **`Success. No rows returned`** 메시지 출력되면 성공
   - (`INSERT 0 N` 형식은 psql 전용 — Supabase SQL Editor에서는 위 메시지로 표시됨)

---

## Step 3 — 데이터 검증 쿼리

Supabase SQL Editor → New query에서 아래 순서대로 실행:

### 3-1. 테이블 수 확인 (기대값: 6개 스키마, 합계 51)
```sql
SELECT table_schema, COUNT(*) AS table_count
FROM information_schema.tables
WHERE table_schema IN ('shared','tms','wms','mm','pp','finance')
  AND table_type = 'BASE TABLE'
GROUP BY table_schema
ORDER BY table_schema;
```

### 3-2. 프로젝트 25건 확인
```sql
SELECT COUNT(*) AS project_count FROM shared.projects;
-- 기대값: 25

SELECT project_code, project_name, project_status
FROM shared.projects
ORDER BY project_code;
-- PRJ-001 ~ PRJ-025 확인
```

### 3-3. 재고(Quants) 확인
```sql
SELECT p.parts_code, p.parts_name, q.system_qty, q.physical_qty, q.unit_of_measure
FROM wms.quants q
JOIN shared.parts_master p ON q.parts_id = p.id
ORDER BY p.parts_code;
```

### 3-4. 음수 재고 확인 (기대값: 1건 -20, PRJ-021)
```sql
SELECT p.parts_code, q.system_qty, q.physical_qty
FROM wms.quants q
JOIN shared.parts_master p ON q.parts_id = p.id
WHERE q.system_qty < 0;
```

### 3-5. 회계 전표 확인
```sql
SELECT entry_number, entry_date, entry_type, amount
FROM finance.accounting_entries
ORDER BY entry_date
LIMIT 20;
```

### 3-6. GL 계정 확인 (기대값: 15건)
```sql
SELECT account_code, account_name, douzone_code, account_type
FROM shared.gl_accounts
ORDER BY account_code;
```

---

## Step 4 — Docker 시작

터미널에서 (SCM_WORK 폴더):
```bash
cd C:\Users\yjisu\Desktop\SCM_WORK
docker compose up -d
```

확인:
```bash
docker compose ps
# scm-nocodb    Up   0.0.0.0:8080->8080/tcp
# scm-metabase  Up   0.0.0.0:3000->3000/tcp
```

- NocoDB: http://localhost:8080
- Metabase: http://localhost:3000

중지 명령:
```bash
docker compose down
```

---

## Step 5 — NocoDB → Supabase 연결

### Supabase 연결 정보 확인 (먼저 필요)
1. Supabase Dashboard → **Settings** → **Database**
2. **Connection parameters** 탭 → Host / Port / Database / User / Password 확인
   - Host: `aws-0-ap-northeast-2.pooler.supabase.com`
   - Port: `6543` (Transaction Pooler 권장)
   - Database: `postgres`
   - Username: `postgres.PROJECT_REF`

### NocoDB 연결 설정
1. http://localhost:8080 접속 → 회원가입 (첫 실행 시)
2. **New Base** → **Connect to External DB**
3. DB 종류: **PostgreSQL**
4. 입력:
   | 항목 | 값 |
   |------|-----|
   | Host | Supabase Pool Host |
   | Port | `6543` |
   | Database | `postgres` |
   | Username | `postgres.PROJECT_REF` |
   | Password | Supabase DB 비밀번호 |
   | Schema | `tms` (또는 보고 싶은 스키마) |
   | SSL | 활성화 |
5. **Test Connection** → 성공 확인 → **Connect**
6. 테이블 목록에서 `projects`, `purchase_orders` 등 선택

> **Tip:** 스키마별로 Base를 따로 만들 수 있음 (shared, tms, wms, mm, pp, finance 각각)

---

## Step 6 — Metabase → Supabase 연결

1. http://localhost:3000 접속 → 초기 설정 완료 (언어/이메일/비밀번호)
2. 초기 설정 중 **"Add your data"** 단계에서:
   - DB 종류: **PostgreSQL**
   - Display name: `SCM_Supabase`
   - Host: Supabase Pool Host
   - Port: `6543`
   - Database name: `postgres`
   - Username: `postgres.PROJECT_REF`
   - Password: Supabase DB 비밀번호
   - **SSL** 활성화
3. **Connect database** → 연결 성공 확인

> 초기 설정을 이미 완료한 경우: **Admin** → **Databases** → **Add database** → 동일하게 입력

### 기본 차트 만들기 (예시)
1. 상단 **+ New** → **Question**
2. 데이터: `SCM_Supabase` → `tms` → `projects`
3. **Summarize** → Count by `status`
4. 차트 타입: **Bar**
5. **Save** → 대시보드에 추가

---

## Step 7 — 최종 동작 확인

### NocoDB 확인 항목
- [ ] tms.projects → 25건 (PRJ-001~PRJ-025) 표시
- [ ] wms.quants → 재고 수량 표시
- [ ] finance.accounting_entries → 회계 전표 표시
- [ ] 필터/정렬/검색 동작

### Metabase 확인 항목
- [ ] 프로젝트 상태별 건수 (completed/in_progress/planning/procurement)
- [ ] 재고 현황 테이블
- [ ] 회계 전표 합계

---

## 트러블슈팅

| 증상 | 원인 | 해결 |
|------|------|------|
| `schema "shared" already exists` | 마이그레이션 재실행 | DROP SCHEMA ... CASCADE 후 재실행 |
| `invalid input syntax for type uuid` | UUID 형식 오류 | ALL_SEEDS_COMBINED.sql UUID 수정 완료됨 |
| `relation "xxx" does not exist` | 시드 실행 순서 오류 | 마이그레이션 → 시드 순서 확인 |
| NocoDB 연결 실패 | SSL 또는 포트 오류 | Port 6543, SSL 활성화 |
| Metabase DB 인식 안됨 | schema 미인식 | Admin → Databases → Sync schemas |
| Docker 컨테이너 안뜸 | 포트 충돌 | `docker compose ps` → 포트 사용 프로세스 확인 |

---

## 파일 위치

| 파일 | 용도 |
|------|------|
| `ALL_MIGRATIONS_COMBINED.sql` | Supabase 스키마 생성 (202KB) |
| `ALL_SEEDS_COMBINED.sql` | 시뮬레이션 데이터 25개 프로젝트 (93KB) |
| `docker-compose.yml` | NocoDB + Metabase Docker 설정 |
| `deployment_guide.md` | 이 파일 |
