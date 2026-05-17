---
name: scm-kpi-formulas
description: Reference for SCM KPI formulas — OTIF, Perfect Order Rate, Dock-to-Stock, Vehicle Utilization, Internal Fill Rate, Consolidation ROI. Use when computing, validating, or explaining KPI values.
allowed-tools: Read
---

# SCM KPI Formulas — Sincerely Standard

## Delivery KPIs

### OTIF (On-Time In-Full)
```
OTIF = On-Time Rate × In-Full Rate

On-Time Rate  = shipments where actual_delivery_date ≤ promised_delivery_date / total shipments
In-Full Rate  = shipments where delivered_qty = ordered_qty / total shipments

Target: OTIF ≥ 95%
Minimum data window: 4 weeks before drawing trend conclusions
```

### Perfect Order Rate (POR)
```
POR = OTIF × Damage-Free Rate × Invoice Accuracy Rate

Damage-Free Rate = shipments without damage claim / total shipments
Invoice Accuracy = correct invoices / total invoices

Target: POR ≥ 92%
```

## Inbound KPIs

### Dock-to-Stock Time
```
D2S = timestamp(로케이션 입고완료) - timestamp(도착)
Unit: hours
Target: ≤ 4 hours for A-grade items, ≤ 24 hours for C-grade
```

## Capacity KPIs

### Vehicle Utilization (차량이용률)

```
# v1 — Count-based (legacy)
Util_v1 = assigned_shipment_count / vehicle_capacity_count

# v2 — CBM-weighted (current standard, commit CBM-PHASE-D-01)
Util_v2 = Σ(Total_CBM per shipment) / Σ(vehicle.capacity_m3)

Target: 80% ≤ Util ≤ 100% (>100% = overbooking alert)
Source: tms_carrier_capacity master table
```

### Internal Fill Rate (내부소화율)
```
Internal Fill Rate = self-driver shipments / total shipments × 100%
Target: ≥ 80%
Period: rolling 4-week / 8-week / 13-week comparison
```

## Cost KPIs

### Consolidation ROI
```
ROI = (per-unit-cost × consolidatable_volume - batched_cost × consolidatable_volume)
      - inventory_holding_cost_during_delay
      - delay_risk_cost

Anomaly threshold: 4-week moving average ±15% → flag for SK-09 tms-cost-lane
```

## KPI Trend Rules
- Minimum 4 weeks before trend conclusion
- Anomaly = OTIF drop ≥ 10 percentage points week-over-week → SK-06 escalation
- Vehicle utilization anomaly = negative or >150% → data validation request

## ABC Classification Input
For cycle count frequency by grade → `abc-xyz-rop-eoq` Skill
