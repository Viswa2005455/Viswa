"""Cash budgeting, runway and working-capital analysis.

Cash budget convention: flows are per period (usually months). Receipts are positive
amounts, payments are positive amounts (they are subtracted). If a minimum cash balance is
set, the shortfall in any period is covered by financing drawn in that period; repayment is
not modelled, so cumulative financing is the peak funding need.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from . import FinanceInputError


@dataclass
class CashLine:
    name: str
    values: list[float]


@dataclass
class CashPeriod:
    period: str
    opening: float
    receipts: float
    payments: float
    net_flow: float
    financing: float
    closing: float
    closing_without_financing: float


@dataclass
class CashBudget:
    periods: list[CashPeriod]
    total_receipts: float
    total_payments: float
    total_financing: float
    lowest_closing_without_financing: float
    lowest_period: str
    first_negative_period: str | None
    receipts_by_line: dict[str, float]
    payments_by_line: dict[str, float]
    warnings: list[str] = field(default_factory=list)


def cash_budget(period_labels: list[str], opening_cash: float, receipts: list[CashLine], payments: list[CashLine],
                minimum_cash: float = 0.0) -> CashBudget:
    n = len(period_labels)
    if not 1 <= n <= 60:
        raise FinanceInputError("Provide between 1 and 60 periods.")
    if minimum_cash < 0:
        raise FinanceInputError("Minimum cash balance cannot be negative.")
    for line in receipts + payments:
        if len(line.values) != n:
            raise FinanceInputError(f"'{line.name}' has {len(line.values)} values; expected {n}.")
        if any(v is None for v in line.values):
            raise FinanceInputError(f"'{line.name}' has blank values; enter 0 explicitly if there is no flow.")
        if any(v < 0 for v in line.values):
            raise FinanceInputError(f"'{line.name}' has negative values; enter receipts and payments as positive amounts.")

    rows: list[CashPeriod] = []
    opening = opening_cash
    unfinanced = opening_cash
    total_fin = 0.0
    lowest, lowest_p, first_neg = float("inf"), period_labels[0], None
    for i, p in enumerate(period_labels):
        r = sum(l.values[i] for l in receipts)
        pay = sum(l.values[i] for l in payments)
        net = r - pay
        pre = opening + net
        fin = max(0.0, minimum_cash - pre)
        closing = pre + fin
        unfinanced += net
        if unfinanced < lowest:
            lowest, lowest_p = unfinanced, p
        if unfinanced < 0 and first_neg is None:
            first_neg = p
        rows.append(CashPeriod(p, opening, r, pay, net, fin, closing, unfinanced))
        total_fin += fin
        opening = closing

    warnings = []
    if first_neg:
        warnings.append(f"Without financing, cash turns negative in {first_neg}.")
    if total_fin > 0:
        warnings.append(f"Financing of {total_fin:,.2f} is needed to keep cash at or above the minimum balance (repayment not modelled).")
    return CashBudget(rows, sum(x.receipts for x in rows), sum(x.payments for x in rows), total_fin, lowest, lowest_p, first_neg,
                      {l.name: sum(l.values) for l in receipts}, {l.name: sum(l.values) for l in payments}, warnings)


@dataclass
class Runway:
    average_net_burn: float
    months: float | None
    message: str


def runway(cash: float, monthly_net_flows: list[float]) -> Runway:
    """Runway = cash / average monthly net burn. Net flows: negative = burning cash."""
    if not monthly_net_flows:
        raise FinanceInputError("Provide at least one month of net cash flow.")
    if cash < 0:
        raise FinanceInputError("Cash balance is already negative.")
    avg = sum(monthly_net_flows) / len(monthly_net_flows)
    burn = -avg
    if burn <= 0:
        return Runway(burn, None, "Average net cash flow is positive or zero; the business is not burning cash on average.")
    return Runway(burn, cash / burn, f"At the average burn of {burn:,.2f} per month, cash lasts about {cash / burn:.1f} months.")


@dataclass
class WorkingCapital:
    dso: float
    dio: float
    dpo: float
    ccc: float
    target_dso: float
    target_dio: float
    target_dpo: float
    target_ccc: float
    receivables: float
    inventory: float
    payables: float
    target_receivables: float
    target_inventory: float
    target_payables: float
    nwc: float
    target_nwc: float
    cash_released: float  # positive = cash freed by moving to targets
    breakdown: dict[str, float]


def working_capital(revenue: float, cogs: float, receivables: float, inventory: float, payables: float,
                    target_dso: float, target_dio: float, target_dpo: float, days: int = 365) -> WorkingCapital:
    if revenue <= 0 or cogs <= 0:
        raise FinanceInputError("Revenue and COGS must be positive to compute days ratios.")
    if min(receivables, inventory, payables, target_dso, target_dio, target_dpo) < 0:
        raise FinanceInputError("Balances and target days cannot be negative.")
    dso, dio, dpo = receivables / revenue * days, inventory / cogs * days, payables / cogs * days
    tr, ti, tp = target_dso * revenue / days, target_dio * cogs / days, target_dpo * cogs / days
    breakdown = {"receivables": receivables - tr, "inventory": inventory - ti, "payables": tp - payables}
    nwc, tnwc = receivables + inventory - payables, tr + ti - tp
    return WorkingCapital(dso, dio, dpo, dso + dio - dpo, target_dso, target_dio, target_dpo, target_dso + target_dio - target_dpo,
                          receivables, inventory, payables, tr, ti, tp, nwc, tnwc, nwc - tnwc, breakdown)
