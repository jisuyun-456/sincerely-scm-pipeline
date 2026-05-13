"""Configuration loader for Virtual SAP Simulation engine."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# SAP movement type labels
MOVEMENT_TYPES: dict[str, str] = {
    "101": "입고 (GR from PO)",
    "122": "반품입고 (Return GR)",
    "201": "출고 (GI to cost center)",
    "261": "생산출고 (GI for production)",
    "311": "이전 (Transfer between sloc)",
    "551": "폐기 (Scrap)",
    "601": "납품 (GI for customer delivery)",
    "701": "조정 (Inventory adjustment)",
}

# K-IFRS / 더존 chart of accounts used in FI postings
GL_MAP = {
    "inventory":        "1410",   # 상품 (Merchandise Inventory)
    "ar":               "1110",   # 외상매출금 (Trade Receivables)
    "gr_ir":            "2110",   # 미지급금-GR/IR (Goods Receipt / Invoice Receipt clearing)
    "ap":               "2120",   # 외상매입금 (Trade Payables)
    "revenue":          "4110",   # 매출 (Sales Revenue)
    "cogs":             "5110",   # 매출원가 (Cost of Goods Sold)
    "freight_expense":  "5210",   # 물류비 (Freight & Logistics Expense)
    "scrap_expense":    "5510",   # 폐기손실 (Scrap & Disposal Loss)
    "inventory_adj":    "5610",   # 재고조정손익 (Inventory Adjustment)
}

# FI document type labels
DOC_TYPES = {
    "WE": "Goods Receipt (입고)",
    "RE": "Vendor Invoice (매입전표)",
    "SD": "Sales Document (매출전표)",
    "GI": "Goods Issue (출고)",
    "ADJ": "Inventory Adjustment (재고조정)",
    "REVAL": "Revaluation (재고재평가)",
}


def _require(key: str) -> str:
    val = os.environ.get(key)
    if not val:
        raise RuntimeError(
            f"Required environment variable '{key}' is not set. "
            "Copy .env.virtual-sap.example to .env.virtual-sap and fill in values."
        )
    return val


@dataclass
class SimConfig:
    supabase_url: str = field(default_factory=lambda: _require("VSAP_SUPABASE_URL"))
    supabase_service_key: str = field(default_factory=lambda: _require("VSAP_SUPABASE_SERVICE_KEY"))
    slack_bot_token: str = field(default_factory=lambda: os.environ.get("SLACK_BOT_TOKEN", ""))
    slack_dm_user_id: str = field(default_factory=lambda: os.environ.get("SLACK_DM_USER_ID", ""))

    dry_run: bool = field(default_factory=lambda: os.environ.get("VSAP_DRY_RUN", "false").lower() == "true")
    sim_mode: str = field(default_factory=lambda: os.environ.get("VSAP_MODE", "manual"))
    orders_per_tick: int = field(default_factory=lambda: int(os.environ.get("VSAP_ORDERS_PER_TICK", "2")))

    def __post_init__(self) -> None:
        valid_modes = {"manual", "daily", "backfill"}
        if self.sim_mode not in valid_modes:
            raise RuntimeError(f"VSAP_MODE must be one of {valid_modes}, got '{self.sim_mode}'")


# Singleton — import and call get_config() everywhere
_config: SimConfig | None = None


def get_config() -> SimConfig:
    global _config
    if _config is None:
        _config = SimConfig()
    return _config


def reset_config() -> None:
    """Reset singleton (used in tests)."""
    global _config
    _config = None
