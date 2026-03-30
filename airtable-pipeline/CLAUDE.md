# Airtable Pipeline — 데이터 수집 레이어

## 역할
Airtable(비정규화 운영 데이터) → Supabase(정규화 원장) 동기화

## 핵심 파일 (sincerely-scm-pipeline-github/ 레포)
- snapshot/pipeline.py: Airtable REST API → 정규화 → Supabase upsert (psycopg2)
- snapshot/config/field_mapping.py: 테이블 ID + 필드 매핑 정의
- pages/dashboard.html: 출하 탭 대시보드 (Chart.js)
- pages/generate_scm_report.py: 주간/월간 리포트 생성

## GitHub Actions (3개)
wms_weekly_report.yml, wms_monthly_report.yml, generate_pdf.yml
(삭제: snapshot.yml → NestJS webhook으로 대체, deploy_pages.yml → 미사용)

## 주의사항
- Airtable 테이블은 display name 아닌 table ID 사용 (변경 안전)
- 이모지 포함 필드명 → NULL 반환됨, field ID로 접근 필수
- upsert 시 ?on_conflict= 파라미터 필수
- generate_scm_report.py에 silent except pass 6곳 — 데이터 오류 은폐 위험
- 토큰: GitHub Secrets 관리 (하드코딩 금지)
