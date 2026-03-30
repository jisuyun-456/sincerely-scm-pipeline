# /migrate — Supabase 마이그레이션

## 실행 전 체크
```bash
# 현재 마이그레이션 파일 목록
ls -la supabase/migrations/

# Airtable 연결 확인 (dry-run)
python3 sincerely-scm-pipeline-github/sincerely-scm-pipeline-gh/snapshot/pipeline.py --dry-run
```

## 마이그레이션 순서
shared 스키마 먼저 (마스터 데이터), 이후 의존성 순서대로:
1. 001~005: shared (스키마 + 참조 + 마스터 + 자재 + 평가)
2. 006: tms
3. 007: wms
4. 008: mm
5. 009: pp
6. 010: cross-schema FK
7. 011: finance
8. 012~013: views + indexes
9. 014~016: triggers (quants → reservations → finance)
10. 017: RLS policies

## 실행
```bash
# 개별 마이그레이션 (Supabase SQL Editor 또는 psql)
psql $SUPABASE_DB_URL -f supabase/migrations/001_create_schemas.sql

# 전체 한 번에
psql $SUPABASE_DB_URL -f ALL_MIGRATIONS_COMBINED.sql
```

## Seed 데이터 적재
```bash
# 순서 중요: 참조 → 조직 → 거래처 → 자재 → 창고 → 운영
psql $SUPABASE_DB_URL -f supabase/seed/001_reference_data.sql
psql $SUPABASE_DB_URL -f supabase/seed/002_organizations_users.sql
psql $SUPABASE_DB_URL -f supabase/seed/003_business_partners.sql
psql $SUPABASE_DB_URL -f supabase/seed/004_material_master.sql
psql $SUPABASE_DB_URL -f supabase/seed/005_warehouse_setup.sql
psql $SUPABASE_DB_URL -f supabase/seed/006_operational_data.sql
```

## 완료 후
- feature_list.json 해당 태스크 passes: true 업데이트
- git commit with migration tag
- claude-progress.txt 기록
