---
source_file: "harness/tms_settlement/main.py"
type: "code"
community: "Cluster 97: assert_week_in_win"
location: "L67"
tags:
  - graphify/code
  - graphify/INFERRED
  - community/Cluster_97_assert_week_in_win
---

# main()

## Connections
- [[IdempotentRunner]] - `calls` [INFERRED]
- [[Notifier]] - `calls` [INFERRED]
- [[SettlementVerifier]] - `calls` [INFERRED]
- [[_parse_args()]] - `calls` [EXTRACTED]
- [[assert_week_in_window()]] - `calls` [INFERRED]
- [[load_cbm_lookup()]] - `calls` [INFERRED]
- [[main.py]] - `contains` [EXTRACTED]
- [[split_by_driver()]] - `calls` [INFERRED]
- [[today_kst()]] - `calls` [INFERRED]
- [[write_batch()]] - `calls` [INFERRED]

#graphify/code #graphify/INFERRED #community/Cluster_97_assert_week_in_win