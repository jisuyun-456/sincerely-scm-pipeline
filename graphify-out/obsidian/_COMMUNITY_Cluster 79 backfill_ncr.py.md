---
type: community
cohesion: 0.16
members: 20
---

# Cluster 79: backfill_ncr.py

**Cohesion:** 0.16 - loosely connected
**Members:** 20 nodes

## Members
- [[PT코드 → record_id 맵을 반환한다.      Airtable API는 fields 파라미터에 field ID를 넣어도]] - rationale - _archive/wms/backfill_ncr.py
- [[WMS_NCR Backfill ----------------- movement 테이블에서 '품질 이슈 리포팅' checkbox=TRUE인 건]] - rationale - _archive/wms/backfill_ncr.py
- [[_get()]] - code - _archive/wms/backfill_ncr.py
- [[backfill_ncr.py]] - code - _archive/wms/backfill_ncr.py
- [[batch_post()]] - code - _archive/wms/backfill_ncr.py
- [[build_material_map()]] - code - _archive/wms/backfill_ncr.py
- [[build_ncr_ids()]] - code - _archive/wms/backfill_ncr.py
- [[extract_pt_code()]] - code - _archive/wms/backfill_ncr.py
- [[load_existing_ncr_ids()]] - code - _archive/wms/backfill_ncr.py
- [[load_qc_movements()]] - code - _archive/wms/backfill_ncr.py
- [[main()_57]] - code - _archive/wms/backfill_ncr.py
- [[map_defect_code()]] - code - _archive/wms/backfill_ncr.py
- [[paginate()_6]] - code - _archive/wms/backfill_ncr.py
- [[rows(dict 리스트)를 batch_size 단위로 POST한다. 생성 건수 반환.]] - rationale - _archive/wms/backfill_ncr.py
- [[각 movement에 NCR_ID를 할당한다.      - 날짜별 시퀀스(NNN)는 기존 existing_ids를 포함하여 계산한다.]] - rationale - _archive/wms/backfill_ncr.py
- [[기존 WMS_NCR 레코드의 NCR_ID 집합을 반환한다.      Airtable API 응답 key는 field ID가 아닌 필드명이므로]] - rationale - _archive/wms/backfill_ncr.py
- [[이동물품 텍스트에서 PTd+ 패턴을 추출한다.]] - rationale - _archive/wms/backfill_ncr.py
- [[테이블 전체 레코드를 페이지네이션하여 반환한다.]] - rationale - _archive/wms/backfill_ncr.py
- [[품질 이슈 리포팅=TRUE인 movement 레코드를 반환한다.      Airtable checkbox filter는 버전에 따라 동작이]] - rationale - _archive/wms/backfill_ncr.py
- [[품질이슈내용구분 + 품질이슈내용으로 Defect_Code를 결정한다.]] - rationale - _archive/wms/backfill_ncr.py

## Live Query (requires Dataview plugin)

```dataview
TABLE source_file, type FROM #community/Cluster_79_backfill_ncrpy
SORT file.name ASC
```
