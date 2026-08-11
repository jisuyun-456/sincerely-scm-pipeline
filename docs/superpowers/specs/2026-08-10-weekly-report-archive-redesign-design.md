# 물류 운영 리포트 — 랜딩 교체 + 주차 아카이브 사이드바 (설계)

- **일자**: 2026-08-10
- **레포**: sincerely-scm-pipeline (GitHub Pages)
- **선행**: pages-weekly-report-port (PR #6 — 크림+클레이 주간 리포트 렌더러)

## 1. 목표 (Goal)

GitHub Pages 대시보드의 **랜딩페이지를 크림+클레이 "운영 KPI 리포트" 디자인으로 전면 교체**하고,
**좌측 사이드바에 주차별 리포트를 누적**해 클릭으로 과거 주(W31, W32, …)를 열람한다.

- 초기 시드: **W31 (2026-07-27 월 ~ 07-31 금)**, **W32 (2026-08-03 월 ~ 08-07 금)**.
- 이후: 매주 배포 시 그 주 리포트가 사이드바에 자동 누적.

## 2. 비목표 (Non-Goals)

- 부드러운 SPA 전환(클라이언트 재렌더) — 정적 페이지 이동으로 충분 (YAGNI).
- 옛 4탭 대시보드(`pages/dashboard.html`) 유지 — **완전 은퇴**.
- 전환 KPI(CBM·M/H 완결성) 자동화 — 반정적 상수 유지(기존과 동일).
- 과거 대량 백필 — 초기엔 W31·W32만, 이후 forward-only 누적.

## 3. 아키텍처

**A. compute / render 분리 (핵심 리팩터)**
- 현재: `render(week)` 내부에서 `compute(week)`[Airtable 라이브] → HTML 일괄.
- 변경:
  - `compute(week) → dict` : Airtable 수집 (기존 로직 유지).
  - **프리즈**: dict → `history/reports/<week>.json` 저장 (그 주 숫자 동결).
  - `render(dict) → HTML` : dict만으로 HTML 생성 (Airtable 미접근).
- 데이터를 얼리는 이유: **디자인을 나중에 또 바꿔도 과거 주 전부 새 디자인으로 자동 재렌더**(표현은 매 배포 생성, 데이터만 동결).

**B. 정적 주차 페이지 + 사이드바**
- 배포마다: 이번 주만 `compute`→프리즈, 그다음 **아카이브의 모든 주를 각 JSON에서 `render`**(API 0회) → `site/weekly-report-<week>.html`.
- **사이드바**(주차 목록, 최신 위, 현재 하이라이트)를 렌더러가 각 페이지에 정적으로 삽입 — 매 배포 전 주 재렌더하므로 항상 최신.
- **`index.html` = 최신 주** (deploy_pages.yml의 `cp pages/dashboard.html site/index.html` → 최신 주 리포트로 교체).

**C. 아카이브 인덱스**
- `history/reports/index.json` : `[{week_id, label, range, file, generated_at}]` (사이드바 소스). 렌더러가 프리즈 JSON들로부터 매번 재생성.

## 4. 컴포넌트 변경

| 파일 | 변경 |
|---|---|
| `pages/weekly_report_data.py` | `compute()` 반환 dict를 **JSON 직렬화 가능하게** 보정 (Counter→dict, date→str). |
| `pages/render_weekly_report.py` | `compute`/`render` 분리 · `freeze_week()` · `render_from_json()` · `render_all_archive()` · **사이드바 빌더** · 인덱스 재생성. |
| `pages/weekly_report.template.html` | 좌측 **사이드바 마크업/CSS** 추가 (레이아웃 2컬럼). |
| `.github/workflows/deploy_pages.yml` | 렌더 스텝을 **전 주 렌더 루프**로 · `index.html`=최신 주 · `cp dashboard.html` 제거. |
| `history/reports/` (신규) | `<week>.json` 프리즈 스냅샷 + `index.json`. |
| `pages/dashboard.html` | site 배포에서 제외 (파일은 남기되 랜딩 아님). |

## 5. 데이터 흐름 (배포 1회)

```
compute(current_week) ──Airtable──> dict ──freeze──> history/reports/<week>.json
                                                          │
history/reports/*.json (전 주) ──load──> render_from_json ──> site/weekly-report-<week>.html (전 주)
                                                          │
                          index.json 재생성 ─> 사이드바(전 페이지 정적 주입)
                                                          │
                          최신 주 ─copy─> site/index.html
```

## 6. 지속성 (Persistence) — 의존성

프리즈 JSON은 배포 간 살아남아야 하므로 **repo 커밋 필요**.
- **초기 W31·W32**: 리디자인과 **같은 PR(사람 머지)**로 커밋 → 봇 이슈 없음.
- **forward 자동 누적**: 배포 봇이 새 주 JSON을 push해야 하는데 **main 브랜치 보호가 봇 push 차단(GH006)**.
  - 해법 (택1, 사용자 결정): **(a)** `github-actions[bot]`을 브랜치보호 우회 목록에 추가, 또는 **(b)** 아카이브 전용 비보호 브랜치에 push 후 배포 시 read.
  - 미해결 시: 그 배포 회차엔 렌더되나 다음 배포에 새 주가 누락 → 자동 누적만 실패(초기 시드는 무관).

## 7. 엣지케이스 / 에러 처리

1. **90일 롤링 지표** — 시드 W31은 롤링(클레임·사이클타임·출하단가·QC)이 '지금' 기준 → **프리즈로 동결**, 이후 안 변함. 초기 W31만 미세 드리프트(허용, 각주 옵션).
2. **compute 실패(Airtable 끊김)** — 기존 프리즈 JSON **덮어쓰지 않음**(마지막 정상값 유지). 나머지 주는 JSON에서 계속 렌더. 렌더 스텝 `continue-on-error` 유지.
3. **깨진/누락 주 JSON** — 해당 주만 skip+로그, 전체 빌드 유지.
4. **빈 아카이브(첫 실행)** — 최소 현재 주 렌더, `index.html`=현재 주.
5. **같은 주 재실행(수동 dispatch)** — 그 주 JSON 멱등 덮어쓰기(최신 compute 승).
6. **JSON 직렬화 실패** — plain 타입 변환으로 방지 + round-trip 테스트.

## 8. 검증 (구현 후)

- 로컬: W31·W32 각각 `compute→freeze→render` → `weekly-report-W31/W32.html` 생성, **사이드바 2주·현재 하이라이트**, `index.html`=최신.
- **div 밸런스/구조 체크**(기존 렌더러 방식) — 깨진 HTML 방지.
- **round-trip 동치**: `compute→dump→load→render` == 직접 `render`.
- 옛 `dashboard.html`이 site에서 제외 + `index`=리포트 확인.
- 배포 dry-run: 렌더 루프+cp가 site/에 전 주 + index 생성.

## 9. 성공 기준

1. 배포된 랜딩(`…/sincerely-scm-pipeline/`)이 크림+클레이 운영 KPI 리포트(최신 주)로 표시.
2. 좌측 사이드바에 W31·W32가 뜨고, 클릭 시 해당 주 리포트로 이동.
3. W31=7/27~31, W32=8/3~7 주간 데이터가 각각 정확히 표시.
4. 다음 주 배포 시 사이드바에 새 주 자동 추가(지속성 해법 적용 시).
