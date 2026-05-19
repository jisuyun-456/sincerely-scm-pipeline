---
type: community
cohesion: 0.15
members: 23
---

# Cluster 68: delivery_routing.p

**Cohesion:** 0.15 - loosely connected
**Members:** 23 nodes

## Members
- [[_get_coords()]] - code - _archive/tms/delivery_routing.py
- [[_haversine()]] - code - _archive/tms/delivery_routing.py
- [[_haversine_total()]] - code - _archive/tms/delivery_routing.py
- [[_is_dayoung_departure()]] - code - _archive/tms/delivery_routing.py
- [[_kakao_headers()_2]] - code - _archive/tms/delivery_routing.py
- [[_parse_address()]] - code - _archive/tms/delivery_routing.py
- [[_parse_departure()]] - code - _archive/tms/delivery_routing.py
- [[_parse_slot()]] - code - _archive/tms/delivery_routing.py
- [[_parse_time_minutes()]] - code - _archive/tms/delivery_routing.py
- [[_parse_wish_time()]] - code - _archive/tms/delivery_routing.py
- [[build_route_order()]] - code - _archive/tms/delivery_routing.py
- [[calc_daily_route()]] - code - _archive/tms/delivery_routing.py
- [[calc_driver_routing()]] - code - _archive/tms/delivery_routing.py
- [[delivery_routing.py]] - code - _archive/tms/delivery_routing.py
- [[enrich_with_routing()]] - code - _archive/tms/delivery_routing.py
- [[fetch_routing_records()]] - code - _archive/tms/delivery_routing.py
- [[format_routing_log()]] - code - _archive/tms/delivery_routing.py
- [[geocode_kakao()_1]] - code - _archive/tms/delivery_routing.py
- [[route_distance_kakao()]] - code - _archive/tms/delivery_routing.py
- [[routing_to_json()]] - code - _archive/tms/delivery_routing.py
- [[경유지 포함 총 주행거리 계산 (카카오 모빌리티 다중경유 API)     coords (lat, lng), ... - 출발지 포함, 순서]] - rationale - _archive/tms/delivery_routing.py
- [[배송슬롯 + 수령인주소 + 희망시간 + 배송파트너 + 출하장소명 조회]] - rationale - _archive/tms/delivery_routing.py
- [[오전 → 무관 → 오후, 슬롯 내 희망시간 빠른 순]] - rationale - _archive/tms/delivery_routing.py

## Live Query (requires Dataview plugin)

```dataview
TABLE source_file, type FROM #community/Cluster_68_delivery_routingp
SORT file.name ASC
```
