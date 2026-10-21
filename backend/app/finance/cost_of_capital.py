"""CAPM cost of equity and weighted average cost of capital."""

from __future__ import annotations

from dataclasses import dataclass

from . import FinanceInputError


def capm(risk_free: float, beta: float, market_return: float) -> float:
    """Re = Rf + beta x (Rm - Rf)"""
    return risk_free + beta * (market_return - risk_free)


@dataclass
class WACCResult:
    wacc: float
    weight_equity: float
    weight_debt: float
    after_tax_cost_of_debt: float


def wacc(equity_value: float, debt_value: float, cost_of_equity: float,
         pre_tax_cost_of_debt: float, tax_rate: float) -> WACCResult:
    """WACC = E/(D+E) x Re + D/(D+E) x Rd x (1 - T)

    Use market values of equity and debt where available; book values are a weaker proxy.
    """
    if equity_value < 0 or debt_value < 0:
        raise FinanceInputError("Equity and debt values must not be negative.")
    total = equity_value + debt_value
    if total == 0:
        raise FinanceInputError("Equity plus debt must be greater than zero.")
    if not 0 <= tax_rate < 1:
        raise FinanceInputError("Tax rate must be between 0% and 100% (as a decimal, e.g. 0.25).")
    we = equity_value / total
    wd = debt_value / total
    rd_after = pre_tax_cost_of_debt * (1 - tax_rate)
    return WACCResult(we * cost_of_equity + wd * rd_after, we, wd, rd_after)
