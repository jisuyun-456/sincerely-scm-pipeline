# 물류 운영 컨트롤타워 — Demo (예시)

`order_cascade` 진행 보드(PropagationLedger 집계) + `capacity_series` 스냅샷을 읽어
**통합운영 / 생산(MES) / 임가공 / WMS / TMS** 를 보여주는 단독 HTML 예시.
글로벌 컨트롤타워(project44 / FourKites / SAP IBP Control Tower) IA 참고.

## 실행
```bash
# 1) 데이터 준비 (gitignore — 로컬 생성)
cp data/order_cascade/report_<run_id>.json  dashboard_demo/report.json
cp data/capacity_series.json                dashboard_demo/capacity_series.json
# 2) 서빙 (file:// 직접 열기는 fetch CORS로 불가)
python -m http.server 8787 --directory dashboard_demo
# 3) 브라우저
#    http://localhost:8787/
```
report.json 재생성: `python scripts/backbone/order_cascade.py --window <days>`
capacity_series.json 재생성: `python scripts/backbone/capacity_snapshot_run.py`

## 구성
- **통합운영**: 이번주 스트립 · KPI · RAG 예외 알림 · 주간 통합 부하(입하 vs 출하) · 프로젝트 진행 보드 (**행 클릭 → 굿즈별 S2~S6 트레이스 모달**)
- **생산(MES) / 임가공**: `설계만 v2` — 실데이터는 forecast CBM / kit CBM 뿐. 진행률·M-H·작업률·예정일은 소스(MES `[sync]파츠별_자재이동`, SERPA `appkRWtF2j99XgBTq`) 적재 후
- **WMS / TMS**: 주간 부하 · 가동률 게이지 · WMS M/H · 부족자재 발주 · 출하 미산출
- **주간 horizon 토글**: 전체 / 이번주 / +1주 / +2~3주

## 주의 (정직 표기)
- 운임은 거리/일당 정산 — **CBM 무관** (박종성 상하차비 fallback만). CBM은 적재 feasibility·창고 capa 용도.
- 데이터 커버리지(입하·출하·MES join)는 각 패널 캡션에 % 표기 — 미커버 과소표현 주의.
- form factor: 향후 `sincerely-scm-dashboard`(React/Vercel/Supabase)로 이식 (CLAUDE.md Supabase 정책 = 대시보드 스냅샷 한정 허용).
