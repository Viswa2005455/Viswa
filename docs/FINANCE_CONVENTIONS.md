# Financial calculation conventions

These rules apply to every function in `backend/app/finance/`. Each formula is a reusable function covered by `backend/tests/`.

## Units and rates
- Rates are decimals (`0.10` = 10%). The UI converts percentages typed by the user.
- A rate must match the cash-flow period. Do not discount monthly flows with an annual rate. To convert an annual rate to a monthly one, use (1 + r)^(1/12) − 1.
- All monetary inputs to one calculation must share the same currency and units. The app does not convert currencies.

## Sign convention
- Outflows are negative and inflows are positive.
- In Investment Appraisal the UI asks for the initial investment as a positive number and negates it.

## Time value of money
- `npv(r, [CF0..CFn]) = Σ CFₜ/(1+r)ᵗ`, where CF0 is at t = 0 and is **not discounted**. Excel equivalent: `=CF0 + NPV(r, CF1:CFn)`.
- `irr` scans NPV on a dense grid from −99% to +1000% and refines every sign change with Brent's method. It returns `unique`, `multiple` (all roots listed) or `none`. It never silently returns one of several roots.
- `mirr` matches Excel `MIRR`. Negative flows are discounted to t = 0 at the finance rate; positive flows are compounded to t = n at the reinvestment rate.
- Payback interpolates within the recovery period, assuming even flows. The result warns if cumulative cash later turns negative again, and returns `None` if the investment is never recovered.
- PI = PV(CF₁..CFₙ) / |CF₀|, and requires CF₀ < 0.
- EAA = NPV × r / (1 − (1+r)⁻ⁿ), or NPV / n when r = 0.

## Cost of capital and DCF
- CAPM: Re = Rf + β(Rm − Rf). WACC uses market-value weights, and Rd is multiplied by (1 − T).
- FCFF = EBIT(1 − T) + D&A − CapEx − ΔNWC. Tax is applied only to positive EBIT; no tax credit is modelled for losses.
- NWC = NWC% × revenue, and the base-year NWC = NWC% × base revenue. So ΔNWC = NWC% × Δrevenue.
- End-of-year discounting by default. With the mid-year option, forecast flows are discounted at t − 0.5, while the terminal value is still discounted at t = n.
- Gordon terminal value: FCFFₙ(1+g)/(WACC − g). The app **refuses** to calculate if WACC ≤ g.
- Exit-multiple terminal value: EBITDAₙ × multiple. The implied g is reported.
- Equity = EV − debt + cash. Value per share is shown only when shares outstanding are provided.

## Sensitivity and scenarios
- Every grid cell, tornado bar and scenario re-runs `run_dcf`. Invalid combinations return `null` with a reason, never a fabricated number.
- "Revenue growth" and "EBIT margin" sensitivities set the same value for every forecast year.
- Scenario attribution applies each changed assumption alone to the base case. The remainder is shown as the interaction effect.

## Variance
- Variance = Actual − Budget. Variance % = (Actual − Budget)/|Budget| × 100.
- **Zero budget:** the percentage is `null` ("not meaningful"); the absolute variance is still shown.
- **Negative budget:** the percentage uses |Budget|, with a warning note.
- Revenue above budget is favourable; expenses above budget are adverse; zero difference is on budget.
- Decimal arithmetic is used so totals reconcile exactly.
- Price variance = (AP − BP) × AQ; volume variance = (AQ − BQ) × BP; together they sum to the total revenue variance.

## Ratios
- A ratio is computed only when every input is present. Otherwise its status is `missing` and the missing items are listed.
- A zero denominator gives `undefined`. ROE, D/E, P/E, P/B, EV/EBITDA and net debt/EBITDA are `undefined` (not meaningful) when their denominator is zero or negative.
- Turnover and return ratios use average balances when an opening (`*_prior`) value is supplied. Otherwise they use the closing balance and add a note.
- Day-based ratios use the period length you enter (365 by default).

## Forecasting
- The holdout backtest uses the most recent `h` observations, which the model never sees during fitting (time-aware validation).
- The linear-trend interval is the classical OLS prediction interval. The SES interval follows ETS(A,N,N): σ√(1 + (h−1)α²).
- MAPE is `null` when any actual value is zero.
- Missing values in a series raise an error; they are never treated as zero.

## Rounding
- The engine never rounds. Rounding happens only when values are displayed.

## Budgeting
- Money uses Decimal. Monthly amounts are rounded to 2 decimals, and the rounding remainder goes into the last month, so the 12 months always sum exactly to the annual figure.
- Incremental method: annual = prior-year actual × (1 + change % / 100), then phased.
- Driver method: month = quantity × rate. Zero-based mode warns about lines with no justification, and about cost lines that are not driver-based.
- Operating result = revenue − operating expenses. CapEx is reported separately and is not deducted from the operating result.
- Version comparison matches lines by (type, name) and reports them as added, removed, changed or unchanged.
- Flexible budget: total cost = fixed + variable rate × activity.

## Financial statements
- Horizontal Δ% = (current − prior) / |prior| × 100. It is `null` when the prior value is zero, and a note is added when the sign flips.
- Common-size base: revenue for the income statement and cash flow lines; total assets for balance sheet lines.
- FCF = operating cash flow − |CapEx|. CapEx may be entered as negative or positive; it is always treated as an outflow.
- Reconciliation tolerance is 0.5% of the larger value (minimum 1 unit), to allow for rounding in published statements. A failed check flags an inconsistency to investigate; it is not evidence of misstatement.
- Accruals ratio = (net income − OCF) / average total assets.

## Cash budget and working capital
- Receipts and payments are entered as positive amounts. Blank cells are rejected; enter 0 explicitly.
- Financing in a period = max(0, minimum balance − (opening + net flow)). Repayment and interest are not modelled.
- Runway = cash ÷ average monthly net burn. The page also shows the first month in which unfinanced cash turns negative.
- Target balances: receivables = DSO × revenue / days; inventory = DIO × COGS / days; payables = DPO × COGS / days. Cash released = (receivables now − target) + (inventory now − target) + (payables target − now).
