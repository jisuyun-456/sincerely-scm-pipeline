---
name: abc-xyz-rop-eoq
description: Reference for ABC/XYZ inventory classification, ROP (Reorder Point), EOQ (Economic Order Quantity), and safety stock formulas. Use when classifying items, setting reorder triggers, or optimizing order quantities.
allowed-tools: Read
---

# ABC/XYZ Classification + ROP/EOQ Formulas

## ABC Classification (Pareto)

| Grade | Revenue/Movement Share | Cycle Count Frequency | Action |
|-------|----------------------|----------------------|--------|
| A | Top 80% | Monthly (월1회) | High safety stock, short lead time |
| B | Next 15% | Quarterly (분기1회) | Medium buffer |
| C | Bottom 5% | Semi-annual (반기1회) | Lean stock, consider consignment |

**Formula**: Rank items descending by annual usage value (unit cost × annual qty)
→ cumulative 80% = A / 80~95% = B / 95~100% = C

## XYZ Classification (Demand Variability)

| Grade | CoV (σ/μ) | Demand Pattern | Strategy |
|-------|-----------|---------------|---------|
| X | CoV ≤ 0.5 | Stable / predictable | MRP deterministic |
| Y | 0.5 < CoV ≤ 1.0 | Seasonal / moderate variation | Safety stock buffer |
| Z | CoV > 1.0 | Irregular / lumpy | Kanban or on-demand |

**CoV** = (standard deviation of demand) / (mean demand) — computed over rolling 13 weeks

## ROP (Reorder Point)

```
ROP = (Average Daily Demand × Lead Time) + Safety Stock

Safety Stock = Z × σ_L × √L
  Z = service level z-score (95% → 1.645 / 98% → 2.054 / 99% → 2.326)
  σ_L = demand std dev per period
  L = lead time in periods
```

## EOQ (Economic Order Quantity)

```
EOQ = √(2 × D × S / H)
  D = annual demand (units)
  S = ordering cost per order (₩)
  H = annual holding cost per unit (₩/unit/year) = unit cost × carrying rate
  carrying rate: typical 20~30% of unit cost per year
```

## Combined AX/BX/CZ Matrix

| | X (stable) | Y (variable) | Z (lumpy) |
|---|------------|-------------|----------|
| **A** | AX: MRP + EOQ | AY: safety stock + review | AZ: expedite |
| **B** | BX: periodic review | BY: min-max | BZ: on-demand |
| **C** | CX: consignment | CY: blanket PO | CZ: eliminate or make-to-order |

## Deep Reference
Detailed calculation examples + sincerely-specific parameters → `references/formulas.md`
