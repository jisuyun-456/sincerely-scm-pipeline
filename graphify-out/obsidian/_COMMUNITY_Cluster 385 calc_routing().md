---
type: community
cohesion: 0.50
members: 5
---

# Cluster 385: calc_routing()

**Cohesion:** 0.50 - moderately connected
**Members:** 5 nodes

## Members
- [[_geocode()]] - code - pages/generate_scm_report.py
- [[_kakao_headers()]] - code - pages/generate_scm_report.py
- [[_route_km()]] - code - pages/generate_scm_report.py
- [[calc_routing()]] - code - pages/generate_scm_report.py
- [[카카오 길찾기 API - (km, minutes) 튜플 반환. 실패시 (0.0, 0).]] - rationale - pages/generate_scm_report.py

## Live Query (requires Dataview plugin)

```dataview
TABLE source_file, type FROM #community/Cluster_385_calc_routing
SORT file.name ASC
```

## Connections to other communities
- 6 edges to [[_COMMUNITY_WMS TMS Analysis Functions]]

## Top bridge nodes
- [[calc_routing()]] - degree 5, connects to 1 community
- [[_route_km()]] - degree 4, connects to 1 community
- [[_geocode()]] - degree 3, connects to 1 community
- [[_kakao_headers()]] - degree 3, connects to 1 community