"""Sub-Spec 5 Scorecard + KPI — 월간 carrier 평가 파이프라인."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class CarrierScore:
    carrier_id: str          # Airtable record ID
    carrier_name: str        # 배송파트너.배송파트너 field
    cost: Optional[float]    # 0-100, None = 운임단가 없음(N/A)
    reliability: Optional[float]  # 0-100, None = OTIF 레코드 없음
    capacity: float          # 0-100
    damage: float            # 0-100
    total: float             # weighted aggregate (N/A 축 재정규화)
    shipment_count: int      # 해당 월 처리 건수


@dataclass
class KpiSnapshot:
    K_LC_1: float            # 자체 기사 활용도 (0-1)
    K_LC_2: float            # Wave 자동화 비중 (0-1)
    K_LC_3: float            # 외주 spillover 비용 (₩ 원단위)
    K_LC_1_baseline: Optional[float] = None  # 첫 측정값
    K_LC_3_baseline: Optional[float] = None  # 첫 측정값


@dataclass
class MonthlySnapshot:
    month: str               # "YYYY-MM"
    generated_at: str        # ISO 8601 KST
    carriers: dict[str, dict] = field(default_factory=dict)  # name → score dict
    kpi: dict = field(default_factory=dict)
