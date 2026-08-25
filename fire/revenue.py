"""Revenue Engine: revenue as a first-class system variable.

Tracks per-engine and portfolio economics, and models the north-star
capacity (R1,000,000/day) as NUMBER OF ENGINES x AVERAGE DAILY REVENUE/ENGINE
rather than one magical product.
"""
from __future__ import annotations

from dataclasses import dataclass

from .models import RevenueEngine

PERIOD_MONTHS = {"month": 1, "one-off": 0, "percent": 0}


@dataclass
class EngineEconomics:
    engine: str
    monthly_revenue: float
    annual_revenue: float
    monthly_profit: float
    gross_margin_pct: float


def engine_monthly_revenue(e: RevenueEngine) -> float:
    if e.period == "month":
        return e.price * e.customers
    if e.period == "percent":
        return e.price * e.customers  # price = take rate, customers = recovered amount
    return 0.0  # one-off amortised to zero for MRR


def engine_economics(e: RevenueEngine) -> EngineEconomics:
    if e.period == "percent":
        mr = e.price * e.customers  # take_rate * recovered
        cost = e.cost_month
    else:
        mr = engine_monthly_revenue(e)
        cost = e.cost_month
    profit = mr - cost
    margin = (profit / mr * 100.0) if mr > 0 else 0.0
    return EngineEconomics(
        engine=e.name, monthly_revenue=round(mr, 2), annual_revenue=round(mr * 12, 2),
        monthly_profit=round(profit, 2), gross_margin_pct=round(margin, 1),
    )


def portfolio(engines: list[RevenueEngine]) -> dict:
    rows = [engine_economics(e) for e in engines]
    total_mrr = sum(r.monthly_revenue for r in rows)
    total_profit = sum(r.monthly_profit for r in rows)
    return {
        "engines": [r.__dict__ for r in rows],
        "total_mrr": round(total_mrr, 2),
        "total_arr": round(total_mrr * 12, 2),
        "total_monthly_profit": round(total_profit, 2),
        "count": len(engines),
    }


def capacity_scenario(target_daily_zar: float = 1_000_000,
                      avg_daily_rev_per_engine: float = 500.0) -> dict:
    """Model the north star as a portfolio capacity target."""
    engines_needed = target_daily_zar / avg_daily_rev_per_engine
    return {
        "target_daily_zar": target_daily_zar,
        "avg_daily_rev_per_engine": avg_daily_rev_per_engine,
        "engines_needed": round(engines_needed),
        "label": "CAPACITY TARGET — not realised revenue",
        "formula": "engines_needed = target_daily / avg_daily_per_engine",
    }
