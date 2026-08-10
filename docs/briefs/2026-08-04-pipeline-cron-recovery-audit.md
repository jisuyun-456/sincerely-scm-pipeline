# 파이프라인·Backfill 재개 현황 — 실측 감사 (2026-08-04)

**작성** 2026-08-04 · **브랜치** `v2-cascade-code-alias` · **선행 브리프** [2026-08-03 전환KPI+운영KPI 핸드오프](2026-08-03-cbm-mh-completeness-synthetic-to-real-handoff.md)
**방법** `gh` CLI + 실제 워크플로 로그 + 코드 직접 확인으로 재검증 (이전 핸드오프 문서를 베끼지 않고 현재 상태를 새로 확인함)

---

## 0. 핵심 발견 — 단일 근본원인이 3개 파이프라인을 막고 있다

`main` 브랜치의 `weekly-full-pipeline.yml` · `scorecard.yml`이 **존재하지 않는 GitHub secret** `AIRTABLE_PAT`을 참조 → 매 실행 즉시 실패. 수정 코드(`AIRTABLE_API_KEY_TMS`로 재매핑 + `permissions: contents: write` + `capacity_snapshot_run.py` 재시도 로직)는 **이미 커밋 `c55f36e`로 작성 완료**되어 있으나, **PR #3에 갇혀 병합 대기 중**.

### PR #3 상태 재확인 — 기존 핸드오프 대비 정정 사항

`gh pr view 3`로 직접 확인한 결과:
- `mergeable=MERGEABLE`, `mergeStateStatus=BLOCKED`, `reviewDecision=REVIEW_REQUIRED`
- 브랜치 보호는 `required_status_checks=null` — 즉 실패 중인 "Golden tests + coverage gate"(5.02% vs 90% 요구)는 **병합을 막지 않는다.**
- **병합을 막는 건 오직 리뷰 승인 누락뿐.**

> ⚠️ 기존 핸드오프 문서는 "`gh pr merge 3 --admin --merge` = 리뷰 게이트 우회"로 프레이밍했는데, 이건 부정확했습니다. 실제로 우회해야 할 건 실패 중인 커버리지 체크가 아니라 **리뷰 승인 그 자체**입니다. 리뷰어가 승인하면 admin 강제병합 없이 정상 병합됩니다.

**PR #3 병합 하나로 해결되는 것**: weekly-full-pipeline.yml, scorecard.yml, capacity_snapshot.yml(부분), `tms_weekly_backfill.py` 8개 모드(배차일지·OTIF·배송이벤트·택배추적로그·운임합계·구간유형·전주평균CBM·상하차비용) 자동 재개, TMS/WMS 주간 리포트 자동 생성 재개 — **전부 연쇄 해결**.

---

## 1. 항목별 현황

| # | 항목 | 카테고리 | 현재 상태 | 막힌 이유 | 다음 액션 | 담당 |
|---|---|---|---|---|---|---|
| 1 | `weekly-full-pipeline.yml` | 🧑 사용자결정 | 최근 5/5 실패 (AIRTABLE_PAT 빈값) | PR#3 리뷰 대기 | PR#3 리뷰 승인 → 병합 | 사용자 |
| 2 | `scorecard.yml` | 🧑 사용자결정 | 최근 4회 중 3회 실패 | 동일(같은 secret) | 동일 | 사용자 |
| 3 | `capacity_snapshot.yml` | 🧑 사용자결정 | 최근 5회 중 4회 ReadTimeout 실패 | 재시도 코드가 PR#3에 갇힘 | 동일 (완전 해소는 아닐 수 있음, 감소 기대) | 사용자 |
| 4 | `tms_weekly_backfill.py` 8모드<br>(배차일지·OTIF·배송이벤트·택배추적로그·운임합계·구간유형·전주평균CBM·상하차비용) | 🧑 사용자결정(연쇄) | weekly-full-pipeline.yml Step1에 **cron 연결은 확인됨**, 단 #1이 그 앞에서 죽어서 실행 자체가 안 됨 | #1과 동일 | #1 해결 시 자동 재개 — 별도 작업 불필요 | 사용자(연쇄) |
| 5 | `mh-backfill.yml` | 🔑 시크릿 등록 | 5/5 매일 실패 | `AIRTABLE_IBSA_PAT` · `AIRTABLE_WMS_PAT` 시크릿이 레포에 **아예 등록된 적 없음** (PR#3과 무관한 별개 원인) | `gh secret set AIRTABLE_IBSA_PAT` / `AIRTABLE_WMS_PAT` 실제 크리덴셜 값으로 등록 | 사용자 |
| 6 | `deploy_pages.yml` | 💻 코드 | 5/5 실패 — 원인 2가지: (a) GH006 보호브랜치 push 거부 (b) `pages/generate_scm_report.py`에 Airtable fetch 재시도 로직 없음 | 코드 미작성 (side-branch 패턴 미적용) | `capacity-data` 패턴처럼 side-branch(`pages-history`) 이식 + retry 이식 | 코드 |
| 7 | `wms_sap_weekly.py` Phase 2 | 💻 코드 | `import random` 등 합성 생성 코드 **100% 그대로 존재** (직접 열어서 재확인) | 미착수 (이번 세션 코드 작업 시작 전) | Dock-to-Stock·공급사납기·QC 실측 소스 교체 (핸드오프 1순위, 아직 미착수) | 코드 |
| 8 | **배차일지 현장입력** ⚠️신규 | 📋 운영 | **2026-05-22 이후 이장훈·조희선·박종성 3명 전원 신규 기록 0건 — 2.4개월 공백** | 현장 미입력, 예상보다 훨씬 심각(기존엔 "재개 필요" 정도로만 알려짐) | **즉시 현장 재개 요청** — 단순 습관 재개가 아니라 장기 중단 상태였음을 팀에 공유 필요 | 운영 |
| 9 | **협력사(외주) CBM 미기재** ⚠️신규 | 📋 운영/확인 | 베스트원·로지비·제작협력사 W31 12건 전부 `Total_CBM` 필드 **자체가 비어있음**(0이 아니라 미기재) | 운영 입력 누락 추정 | CBM 완결성(전환 KPI Ⅰ, P1/P2/P3)과 같은 근본원인인지 확인 필요 | 운영/확인 |
| 10 | `order_cascade.yml` / `tms_settlement.yml` | ✅ 정상 | 최근 5/5 성공 | — | 없음 | — |
| — | `scm_mcp/scm_mcp/tms.py` · `harness/_core/geo.py` (미커밋) | 무관 | 각 1줄 변경, 파이프라인 이슈와 무관 확인됨(별도 작업) | — | 이 감사 범위 밖 — 별도 결정 | — |

---

## 2. 우선순위 제안

1. **PR #3 리뷰 승인 → 병합** — 최고 레버리지, 3개 파이프라인 + 8개 backfill 모드 동시 해결
2. **`mh-backfill.yml` 시크릿 2개 등록** — PR#3과 독립적, 바로 실행 가능
3. **배차일지 현장 재개 긴급 공유** — 2.4개월 공백은 팀 차원에서 인지 필요한 사안
4. **`deploy_pages.yml` 코드 수정** — side-branch 패턴 이식 (신규 코드 작업)
5. **`wms_sap_weekly.py` Phase 2** — 합성→실측 전환 (기존 핸드오프 1순위, 계속 대기 중)

---

## 3. 열린 결정 — 사용자 확인 필요

1. **PR #3 리뷰 승인** — 누가 승인할지(본인 세컨드 계정 또는 협업자 지정). Admin 강제병합은 불필요할 가능성 높음(리뷰만 받으면 정상 병합).
2. **`mh-backfill.yml` 시크릿 값** — 실제 크리덴셜이 필요해서 대신 등록해드릴 수 없습니다. `AIRTABLE_IBSA_PAT`는 로컬 `.env`의 `AIRTABLE_INBOUND_PAT`(입하검수입고 베이스)와 동일 값으로 보이고, `AIRTABLE_WMS_PAT`는 기존 `AIRTABLE_API_KEY_WMS`를 재사용하거나 YAML에서 직접 그 이름을 쓰도록 고치는 것도 가능합니다.
3. **`deploy_pages.yml` 코드 수정 착수 여부** — `pages-history` side-branch 신설은 장기 운영 브랜치가 하나 더 느는 것(기존 핸드오프의 열린 리스크 항목과 동일).
4. **협력사 CBM 미기재 원인** — 시스템 문제가 아니라 단순 미입력인지, 확인 후 운영팀 공유 필요.

---

## 4. 참고 — 이번 감사에서 함께 확인된 TMS W31 실측 (교차 참조)

같은 감사 세션에서 W31 CBM 채널별·배송방식별 breakdown도 재계산함 (상세는 `_AutoResearch/SCM/outputs/WeeklyReport-물류파트-2026-W32.html` 참조):

- **박종성 W31 상태**: Shipment 배정 0건 + 배차일지 0건 → **실제 무배차 확정** (미입력 아님)
- **기존 "차량 적재율 18.0%/27.8%"**: 재검증 결과 어떤 계산 정의로도 재현 안 됨 → **폐기**
- CBM 채널: 신시어리 내부기사 46.6%(조희선 33.7%·이장훈 12.9%·박종성 0%) · 신시어리(로젠) 42.4% · 고객직접 9.5% · 고고엑스 1.6% · 협력사(외주 12건, CBM 미기재)
- 배송방식: 퀵(수도권) 22건/9.09m³ · 택배 17건/7.99m³ · 협력사(퀵+택배) 12건(CBM 미기재) · 기타 3건/1.79m³

이 두 발견(배차일지 2.4개월 공백, 협력사 CBM 미기재)은 §1의 항목 8·9와 동일 이슈입니다.
