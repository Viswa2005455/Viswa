"""Deterministic financial calculation engine.

Conventions used across every module (also documented in docs/FINANCE_CONVENTIONS.md):

* Rates are decimals: 10% is passed as 0.10, never as 10.
* Periods are whole, equal-length periods (usually years). A rate must match the period
  length of the cash flows it discounts — do not mix monthly flows with an annual rate.
* Cash-flow sign convention: outflows are negative, inflows are positive.
* Cash flow index 0 is "today" (t = 0) and is NOT discounted. This differs from Excel's
  NPV(), which discounts the first value by one period.
* Missing inputs are never silently treated as zero: functions raise FinanceInputError or
  return an explicit "missing"/"undefined" status.
* Results are not rounded inside the engine; rounding is a presentation concern.
"""


class FinanceInputError(ValueError):
    """Raised when inputs make a calculation impossible or meaningless."""
