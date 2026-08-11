# WMS_ItemMaster 재적재 — upsert 리팩터 (설계)

> ## ⛔ SUPERSEDED (2026-08-11, 실행 전 폐기) — 착수 금지
>
> **본 설계의 전제가 검증 단계에서 반증됐다.** 후속 설계:
> `2026-08-11-shipment-cbm-parse-match-design.md`
>
> **반증된 전제**: §1은 "`build_kit_lookup()`이 이 테이블을 읽는다"를 근거로 굿즈행 갱신 가치를 주장했다.
> 테이블을 읽는 것은 맞으나 **PT행만** 읽는다. ItemMaster 소비처 4곳
> (`replay_outbound_cbm.build_kit_lookup` / `order_cascade.py:136` / `capacity_snapshot_run.py:137-140`
> / `storage_occupied.py:63-66`)은 전부 PT코드로만 조인한다 — 앞의 둘은 `WMS_BOM.소품목_PT`(항상 `PT####`),
> 뒤의 둘은 `parse_pt_from_ledger_key(품목키)`로 명시 필터. **굿즈행(품목키=한글 굿즈명)은 PT 정규식에
> 영원히 매칭되지 않는다.** 직접 굿즈 CBM 경로는 ItemMaster가 아니라 TMS Product를
> `load_product_lookup()`으로 읽는다. → 굿즈행 재적재는 다운스트림 출력을 **하나도** 바꾸지 못한다.
>
> **그런데 유일한 실효는 부수피해였다**: 재적재 시 351개 파츠행이 `출처` 치수파싱→수기로 뒤집힌다
> (`build_item_rows`가 파츠를 CBM 없이 `출처="수기"`로 방출). 그 결과 ① `part_cbm_backfill.py:130-132`
> 스코프(`CBM<=0 OR 출처∈{치수파싱,QC버킷}`)에서 영구 제외 → 파서 개선이 영원히 도달 불가,
> ② P3' 문서의 롤백 핸들(`출처='치수파싱'` 필터) 소멸, ③ kit 신뢰도 0.55→0.7 묵시 인플레.
> (단, "CBM 값이 지워진다"는 초기 우려는 **오판** — Airtable PATCH는 부분 갱신이라 누락 필드는 보존된다.)
>
> §6-4의 통과조건("파츠 diff 0건이어야 함")도 오류다 — diff는 351건이며 이는 `build_item_rows` 버그가
> 아니라 upsert가 정당한 백필 데이터를 덮는 것이다. 그대로 따르면 오진한다.
>
> 실측 근거는 후속 설계 §2 참조. 본 문서는 audit trail로 보존한다.

- **일자**: 2026-08-11
- **Chain**: bridge-cbm-ssot (P1) — **폐기됨**
- **선행**: 2026-08-11 세션 — Product 백필(신규 6굿즈+빈필드 28행)·dedup(30행 삭제)·`match_product` 공백무시 매칭 fix (커밋 8409485, 802f8cc @ feat/weekly-report-archive)

## 1. 배경 (Why now)

당초 P0는 "굿즈↔TMS Product 브릿지 테이블 신규 설계"로 스코프됐으나, 브레인스토밍 중 확인한 결과:

- **`WMS_KeyCrosswalk`**(67행, WMS 베이스 `tblJK5eyQGGx5X1oH`)는 이미 6월 `cbm-capacity-backbone` chain에서 만든 굿즈↔TMS_견적코드 브릿지지만, `cascade.py`/`item_master_sync.py`/`replay_outbound_cbm.py` 어디서도 읽지 않는다(grep 확인) — 실질 소비처가 없는 write-once 감사용 스냅샷.
- **`WMS_ItemMaster`**(1,309행, `tbl5ZGY373D5SCONV`)는 2026-06-09 단 1분 만에 생성되고 이후 갱신 이력이 없다(`createdTime` 전부 06-09 03:56대). `replay_outbound_cbm.py`의 `build_kit_lookup()`(kit-CBM 폴백)이 **실제로 이 테이블을 읽는다.** 현재 굿즈 472건 중 218건만 `출처=TMS_Product`, 254건 `미등록`.
- `cascade.py`·TMS settlement/`cbm_estimator.py`는 `match_product`/`load_product_lookup`을 **매 실행 시 새로 호출**하므로 이미 커밋된 오늘의 Product 정리+매칭 fix를 자동으로 반영 중 — 추가 조치 불필요.

**결론**: 실제 가치가 있는 것은 `WMS_ItemMaster` 재적재뿐. `WMS_KeyCrosswalk` 재적재는 소비처가 없어 스코프에서 제외(백로그).

## 2. 목표 (Goal)

`item_master_sync.py`가 산출하는 최신 매칭 결과를 **upsert**로 `WMS_ItemMaster`에 반영해, `replay_outbound_cbm.py`의 kit-CBM 폴백이 최신 Product 데이터/매칭 로직 기준으로 동작하게 한다.

## 3. 비목표 (Non-Goals)

- `WMS_KeyCrosswalk` 재적재 — 소비처 없음, 별도 백로그.
- `order_cascade.yml` cron 편입 — 별도 후속 과제(사용자 push 필요, branch protection).
- Product 마스터 잔여 정리(FGPS 코드재사용·dup/junk ②④) — chain의 P2.
- 품질혁신팀 탈-Airtable SSOT 이관 — 현재 프로젝트 정책상 Airtable이 SSOT, 조기 설계 안 함(YAGNI).

## 4. 아키텍처

기존 `harness/backbone/item_master_sync.py`를 확장한다. 새 테이블·새 스크립트 없음.

- `build_item_rows()`: **변경 없음** — 이미 고쳐진 `match_product`/`load_product_lookup`을 그대로 호출하므로 재계산 결과 자체는 이미 옳다.
- 신규: **upsert 레이어**
  1. 기존 `WMS_ItemMaster` 전체 조회 (`품목키` → `{rec_id, fields}`, ~1,309행, 단일 테이블 풀스캔이라 비용 낮음).
  2. `build_item_rows()` 재계산 결과를 `품목키` 기준으로 비교:
     - 기존에 없음 → INSERT 대상.
     - 기존에 있고 필드값 변경(`CBM_개당_m3`/`박스당_제품수`/`박스당_CBM_m3`/`출처`) → PATCH 대상.
     - 기존과 동일 → 스킵 (idempotent).
  3. PATCH는 **10건 batch**로 처리 — `scripts/dispatch/run_cbm_polling.py`의 `batch_patch()` 패턴을 따름 (프로젝트 컨벤션: 단건 PATCH는 10배 느림).
  4. INSERT는 기존 `AirtableClient.create_records`(이미 10-batch 내장) 재사용.

### 검토 후 기각한 대안

| 대안 | 기각 사유 |
|---|---|
| 전체 삭제 후 재생성 | rec_id 전부 churn, API 호출 ~2,600회(upsert 대비 수배) — 이득 없이 비용만 큼 |
| INSERT-only 버저닝(PropagationLedger 방식) | `WMS_ItemMaster`는 스냅샷/참조 테이블이지 거래 원장이 아님(Immutable Ledger 규칙은 movement/mat_document 대상). 버저닝 시 `replay_outbound_cbm.py` 읽기 로직도 "키별 최신행"으로 바꿔야 해 불필요하게 침습적 |

## 5. 데이터 흐름 (1회 실행)

```
load_product_lookup(Product) ──match_product──> build_item_rows() [재계산, 472 굿즈+파츠]
                                                        │
WMS_ItemMaster 전체 조회(품목키 keyed) ──diff──> {신규, 변경, 동일}
                                                        │
                              PATCH(변경, 10건씩) + INSERT(신규, 10건씩)
                                                        │
                                    리포트: 매칭률 전/후, 변경 건수
```

## 6. 검증 계획

1. **Dry-run** (기본, `--write` 없이): 매칭률 전/후(현재 218/472=46.2%) + {신규/변경/동일} 건수 출력.
2. 오늘 세션에서 확인된 공백변형 굿즈명 샘플(다영 케이스 등) 몇 건이 dry-run 결과에서 `TMS_Product`로 전환되는지 스팟체크.
3. `--write` 실행 후 Airtable에서 동일 샘플 재조회로 실제 반영 확인.
4. 파츠(`출처=수기`) 행은 재계산 로직 미변경이라 diff 0건이어야 함 — 0이 아니면 버그 신호.

## 7. 리스크

- `WMS_ItemMaster` PATCH는 `replay_outbound_cbm.py`의 kit-CBM 산출값을 바꾼다 — 이는 의도된 정정(기존 값이 정리 전 Product 데이터/구 매칭 로직 기준이었음)이며 Immutable Ledger 원칙 위반 아님(원장 테이블 아님).
- 풀스캔 후 diff는 메모리 내 처리라 API 부하는 낮음(조회 1,309행 + 쓰기는 변경분만).
