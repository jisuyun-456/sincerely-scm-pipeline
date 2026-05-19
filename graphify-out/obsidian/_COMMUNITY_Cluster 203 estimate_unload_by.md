---
type: community
cohesion: 0.26
members: 13
---

# Cluster 203: estimate_unload_by

**Cohesion:** 0.26 - loosely connected
**Members:** 13 nodes

## Members
- [[_str()_1]] - code - harness/settlement/estimate_unload_by_product.py
- [[build_lookup()]] - code - harness/settlement/estimate_unload_by_product.py
- [[estimate_unload_by_product.py]] - code - harness/settlement/estimate_unload_by_product.py
- [[fetch_all()]] - code - harness/settlement/estimate_unload_by_product.py
- [[find_best_match()]] - code - harness/settlement/estimate_unload_by_product.py
- [[jaccard()]] - code - harness/settlement/estimate_unload_by_product.py
- [[main()_5]] - code - harness/settlement/estimate_unload_by_product.py
- [[parse_unload()_1]] - code - harness/settlement/estimate_unload_by_product.py
- [[tokenize()]] - code - harness/settlement/estimate_unload_by_product.py
- [[룩업 테이블에서 가장 유사한 품목 찾기.     Returns (matched_product_key, best_box_text, score)]] - rationale - harness/settlement/estimate_unload_by_product.py
- [[품목 매칭 기반 하차비 추정 — 다영기획 출발 박종성 (2026-01~05-12)  전략   1. 2024-01-01~현재 전체 Ship]] - rationale - harness/settlement/estimate_unload_by_product.py
- [[품목 텍스트 → Counter({box_text count}) 룩업 테이블 빌드     같은 품목에 여러 박스 구성이 있으면 가장 많이 쓰인]] - rationale - harness/settlement/estimate_unload_by_product.py
- [[품목 텍스트를 토큰 집합으로 — 숫자기호 제거, 2자 이상 한국어영어만 유지]] - rationale - harness/settlement/estimate_unload_by_product.py

## Live Query (requires Dataview plugin)

```dataview
TABLE source_file, type FROM #community/Cluster_203_estimate_unload_by
SORT file.name ASC
```
