# ABC/XYZ/ROP/EOQ — Detailed Formulas & Sincerely Parameters

## ROP Calculation — Step by Step

```python
# Parameters (sincerely defaults)
service_level_z = {
    "A": 2.054,   # 98% — high-value items
    "B": 1.645,   # 95%
    "C": 1.282,   # 90%
}
data_window_days = 90  # rolling 90-day history

# Step 1: daily demand from outbound movements
daily_demand = outbound_qty_90d / 90

# Step 2: daily demand std dev
sigma_daily = std(daily_qty_per_day_over_90d)

# Step 3: lead time (from supplier master, in days)
L = supplier_lead_time_days

# Step 4: safety stock
Z = service_level_z[abc_grade]
safety_stock = Z * sigma_daily * sqrt(L)

# Step 5: ROP
ROP = daily_demand * L + safety_stock
```

## EOQ Calculation — Step by Step

```python
# Parameters
D = annual_demand_units          # units/year
S = ordering_cost_per_order_krw  # ₩/order (typically 15,000~50,000)
unit_cost = item_unit_cost_krw   # ₩/unit
carrying_rate = 0.25             # 25% of unit cost/year (sincerely standard)
H = unit_cost * carrying_rate    # ₩/unit/year

EOQ = sqrt((2 * D * S) / H)
```

## ABC Reclassification Trigger

- Reclassify quarterly or when annual revenue change > 20%
- New items: start at C grade (insufficient history)
- After 13 weeks of data → recalculate

## XYZ CoV Calculation

```python
# Rolling 13-week window
weekly_demand = [sum(outbound per week) for week in last_13_weeks]
mean_d = mean(weekly_demand)
std_d  = stdev(weekly_demand)
CoV    = std_d / mean_d if mean_d > 0 else float('inf')

grade = "X" if CoV <= 0.5 else ("Y" if CoV <= 1.0 else "Z")
```

## BIN Location Strategy by Grade

| Grade | BIN Zone | Pick Priority |
|-------|---------|--------------|
| AX | A (골든존 — 허리 높이) | Highest |
| AY/AZ | A or B | High |
| BX/BY | B | Medium |
| CZ | C or overflow | Low |
