# CBM-driven TMS analytics — dashboard widgets + GitHub auto-KPI catalog

**Date**: 2026-05-12
**Status**: design (post-brainstorm)
**Author**: yjisu + Claude

## Context

After today's Phase 0 fix:

- TMS `Product` table now has **337 records**, all 5 missing PDF items inserted (`NFCA, AWTW, SOLE, SORB, FANB, FANC, USLB, HHTW, HHTK, ATSS`).
- `박스사이즈` backfilled on **321 records** that previously had it blank.
- `harness/settlement/cbm_calc.py` now uses a `BOX_TYPE_TO_CBM_M3` fallback when the Airtable formula returns 0, so `total_cbm` and `unload_fee` resolve correctly for all 5 box types (`극소형 / 중형 / 중대형 / 대형 / 특대형`) even where the Airtable formula is incomplete.
- Shipment `Total_CBM` re-backfilled with the corrected calc.

This unblocks the question the user actually asked: with CBM mastered, what's worth surfacing in the Vercel dashboard and/or as a GitHub auto-KPI in AutoResearch?

## Mental model — what CBM unlocks

Today's dashboard/AutoResearch treat every shipment as 1 unit of "volume." A 1-box order and a 30-box order look identical. CBM (m³) is the standard SAP-TM/MM way to:

1. Size trucks → **capacity planning** (TM)
2. Cost freight → **standard rate × CBM** vs actual (MM 운임 표준원가)
3. Forecast carton/labor → **box-mix prediction** (WM)
4. Profile customers → **CBM per order** (CRM/Sales)
5. Audit billing → **CBM-weighted variance** (FI-CO)

Every catalog item below is "what does adding CBM change vs today's count-based view?"

## Section 1 — Analytics catalog (15 items, scored)

Priority: **P0** = fix existing broken KPI / unblock daily decisions, **P1** = high analytical value, **P2** = nice-to-have / diagnostic.

| # | Idea | SAP analog | Inputs | Cadence | Priority | Goes to |
|---|------|------------|--------|---------|----------|---------|
| 1 | **Daily CBM volume trend** (m³/day, 7d/30d) | MM consumption analytics | Σ shipment.Total_CBM by day | daily cron | **P0** | Dashboard + Supabase |
| 2 | **차량이용률 v2** (CBM-weighted, not count) | TM Vehicle Utilization | Σ actual CBM / Σ vehicle capacity CBM | weekly | **P0** | AutoResearch |
| 3 | **Today's truck load board** (per-carrier load %) | TM Capacity Planning | today's planned ships + carrier capacity | hourly | **P0** | Dashboard (TMS tab) |
| 4 | **CBM ABC analysis** (top-20 items = 80% volume) | MM Material ABC | 30d items × per-unit CBM × qty | weekly | **P0** | AutoResearch + Dashboard |
| 5 | **Box-mix forecast** (next-day cartons needed) | WM Picking Slip Planning | tomorrow's orders × items × box_type | nightly | **P0** | Dashboard (WMS tab) |
| 6 | **Standard vs actual freight variance** | MM 운임 표준원가 | CBM × per-CBM standard vs paid 운송비용 | weekly | P1 | AutoResearch |
| 7 | **Carrier-suitability mismatch alert** | TM Routing Optimization | shipment CBM vs carrier type rule | daily | P1 | Dashboard exception banner |
| 8 | **PNA customer CBM profile** | CRM Customer Analytics | 90d shipments per PNA + CBM stats | monthly | P1 | AutoResearch |
| 9 | **Next-week CBM forecast** (pipeline-based) | TM Forecast / SOP | open 배송요청 × items × per-unit CBM | weekly | P1 | Dashboard + AutoResearch |
| 10 | **CBM × OTIF correlation** | TM Performance | per-ship CBM vs On_Time outcome | weekly | P2 | AutoResearch |
| 11 | **CBM anomaly per PNA** (outliers) | TM Anomaly Detect | rolling Z-score on PNA CBM history | daily | P2 | Dashboard exception |
| 12 | **Multi-stop CBM density** | TM Stop Density | trip CBM / stop count | weekly | P2 | AutoResearch |
| 13 | **Per-unit margin check** | FI-CO Profitability | per-unit CBM × shipping cost vs item price | monthly | P2 | AutoResearch |
| 14 | **Unload fee invariance audit** | FI-CO Settlement Audit | recomputed vs paid 상하차비용 by driver | monthly | P2 | AutoResearch |
| 15 | **Dock-to-Stock × inbound CBM** | WM Putaway KPI | inbound CBM vs putaway time | weekly | P2 | AutoResearch (WMS) |

## Section 2 — Recommended Vercel dashboard additions

Five widgets, all on the **TMS tab** unless noted. Each maps to a P0/P1 catalog item.

### W1. CBM Volume Trend (catalog #1) — **P0**

- **Where**: TMS tab, next to existing `TmsDailyVolume` widget
- **Look**: dual-axis line chart — left axis: shipment count, right axis: CBM (m³), 30-day window
- **Data table**: extend `tms_daily_volume` with `total_cbm NUMERIC(8,3)` column
- **Sync**: `sync_tms_daily_volume.py` adds `SUM(Total_CBM)` per day
- **Why P0**: replaces "count-as-volume" with real volume — this single chart corrects the most common SCM misread

### W2. Today's Truck Load Board (catalog #3) — **P0**

- **Where**: TMS tab, top-of-page exception/operational card
- **Look**: one row per carrier (이장훈, 조희선, 박종성), columns: today's CBM / capacity / utilization %, color-coded (>100% red, 80-100% yellow, <80% gray)
- **Capacity master**: add `tms_carrier_capacity` table `(partner_id, vehicle_type, capacity_m3)` — seed 4-5 records manually
- **Sync**: `sync_tms_truck_load.py` runs every 1h during ops hours
- **Why P0**: turns the current 박종성 "택배 over-flow" recurring incident into a 09:00 morning glance

### W3. Box-Mix Forecast (catalog #5) — **P0**

- **Where**: WMS tab (cross-team — packing planning)
- **Look**: stacked bar — tomorrow's carton needs by `박스명칭` (5 colors)
- **Sync**: `sync_wms_box_mix.py` runs at 17:00 KST for next-day planning
- **Why P0**: lets the WMS team pre-fold cartons the night before

### W4. CBM ABC Pareto (catalog #4) — **P0**

- **Where**: TMS tab, monthly section
- **Look**: Pareto bar+line — top 20 items by 30d Σ CBM, cumulative % line
- **Sync**: `sync_tms_cbm_abc.py` weekly
- **Why P0**: WMS slotting, sales focus — answers "which items move the most volume"

### W5. Carrier-Suitability Mismatch Alert (catalog #7) — P1

- **Where**: TMS tab existing `TmsExceptionBanner`
- **Look**: red banner if any shipment Σ CBM > 0.5 m³ went to 택배 (로젠) instead of direct truck
- **Logic**: rule-based in `sync_tms_kpi.py`, surface as `tms_kpi.exceptions JSONB` entry
- **Why P1**: prevents cost leakage — large CBM via parcel is 3-5× more expensive

### Schema deltas required

```sql
ALTER TABLE tms_daily_volume ADD COLUMN total_cbm NUMERIC(8,3) DEFAULT 0;

CREATE TABLE tms_carrier_capacity (
  partner_id TEXT PRIMARY KEY,
  partner_name TEXT,
  vehicle_type TEXT,
  capacity_m3 NUMERIC(6,2) NOT NULL
);

CREATE TABLE tms_truck_load_today (
  snapshot_at TIMESTAMPTZ NOT NULL,
  partner_id TEXT NOT NULL,
  loaded_m3 NUMERIC(8,3) NOT NULL,
  capacity_m3 NUMERIC(6,2) NOT NULL,
  utilization_pct NUMERIC(5,2) NOT NULL,
  status TEXT NOT NULL,  -- 'green' | 'yellow' | 'red'
  shipment_count INT NOT NULL,
  PRIMARY KEY (snapshot_at, partner_id)
);

CREATE TABLE wms_box_mix_forecast (
  forecast_date DATE PRIMARY KEY,
  box_counts JSONB NOT NULL,  -- {"중대형":12,"대형":8,...}
  total_cbm NUMERIC(8,3),
  synced_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE tms_cbm_abc_weekly (
  week_start DATE NOT NULL,
  rank INT NOT NULL,
  product_code TEXT NOT NULL,
  product_name TEXT,
  total_cbm NUMERIC(8,3),
  cumulative_pct NUMERIC(5,2),
  PRIMARY KEY (week_start, rank)
);
```

## Section 3 — Recommended GitHub auto-KPI additions

The weekly `_AutoResearch/SCM/outputs/week_YYYYMMDD.md` already tracks `차량이용률 / OTIF / 약속납기일전환율 / 내부소화율`. Three new CBM-based KPIs to inject into the same weekly cron, plus one monthly:

### K1. 차량이용률 v2 (CBM-weighted) — **P0** (catalog #2)

**Replaces** the current count-based 차량이용률 (currently 19.4% — meaningless because it ignores load size).

Formula:
```
util_v2 = Σ(Total_CBM of shipped trips) / Σ(vehicle.capacity_m3 of those trips)
```

Where `vehicle.capacity_m3` comes from the new `tms_carrier_capacity` master.

**Acceptance**: weekly report shows both `이용률 (count-based)` and `이용률 v2 (CBM-weighted)` — operations can compare.

### K2. Standard vs Actual Freight Variance — P1 (catalog #6)

```
expected = Total_CBM × std_rate_per_m3[carrier]
variance = (actual_운송비용 - expected) / expected
```

Flag any PNA where weekly Σ variance > 15% (over- or under-paid).

**Acceptance**: weekly report adds a section "운임 표준 대비 편차 > 15% PNA 목록" with 5-10 rows.

### K3. Next-Week CBM Forecast — P1 (catalog #9)

For each upcoming day in next ISO week:
- Sum CBM of currently-open `배송요청` records assigned to that date
- Compare to last 4-week same-weekday avg
- Output: `예상 m³ / 평균 m³ (편차%)`

**Acceptance**: weekly report ends with "다음 주 예상 적재" table → drives capacity planning meeting.

### K4. Monthly CBM ABC (catalog #4) — **P0**

Top 20 items by previous-month Σ CBM, plus cumulative %. Output to `monthly_YYYYMM.md`.

**Acceptance**: monthly report has a section "월간 CBM ABC — 상위 20품목" with code, name, CBM, cum%.

## Section 4 — Implementation phasing

**Phase A — Foundation (this week)** ✅ DONE today:
- Fix master data (10 INSERT + 321 박스사이즈 backfill + code fallback)
- Re-backfill Shipment.Total_CBM with correct calc

**Phase B — P0 dashboard widgets (next sprint)**:
1. Schema migration (`tms_daily_volume.total_cbm` + 4 new tables)
2. `sync_tms_daily_volume.py` — add CBM SUM
3. `sync_tms_truck_load.py` (new) — hourly, requires `tms_carrier_capacity` seed
4. `sync_tms_cbm_abc.py` (new) — weekly
5. React widgets W1/W2/W4 on TMS tab

**Phase C — P0 WMS-side widget**:
6. `sync_wms_box_mix.py` (new) — nightly
7. React widget W3 on WMS tab

**Phase D — P0 AutoResearch KPIs**:
8. Update `_AutoResearch/SCM/scripts/tms_weekly_runner.py` (or equivalent) to compute K1 (utilization v2)
9. Update report template to surface K1 + K4

**Phase E — P1 polish**:
- W5 (carrier-suitability banner)
- K2 (freight variance) / K3 (forecast)

## Section 5 — Out of scope (P2 / later)

- Items 10-15 in the catalog (correlation studies, anomaly detection, FI-CO margin) — defer until Phase A-D are running and we have 4+ weeks of CBM history to make these statistically meaningful.
- Airtable formula `박스 당 CBM` extension to cover all 5 sizes — currently Python code patches around this. If sales team wants accurate Airtable UI display, separate one-line formula change required.

## Open questions (not blocking — surfaced for transparency)

- **Carrier capacity master**: who owns the `tms_carrier_capacity` seed values? Defaults proposed: 이장훈 1t (4 m³), 조희선 1t (4 m³), 박종성 2.5t (10 m³), 로젠택배 unlimited (no cap). Confirm with ops.
- **Standard $/m³ rate**: where does K2's `std_rate_per_m3` come from? Suggested: derive from last 4 weeks' median (actual_freight / Total_CBM) per carrier — self-calibrating baseline.
