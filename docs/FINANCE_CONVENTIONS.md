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
- `irr` scans NPV on a dense grid from −99% to +1000% and refines every sign change with Brent's method. Because a grid only sees sign changes, it also takes the real roots of the NPV polynomial in x = 1/(1+r) and keeps those that make NPV zero, so a double root (NPV touches zero without crossing) and two roots closer together than the grid step are found. It returns `unique`, `multiple` (all roots listed) or `none`. It never silently returns one of several roots.
- `mirr` matches Excel `MIRR`. Negative flows are discounted to t = 0 at the finance rate; positive flows are compounded to t = n at the reinvestment rate.
- Payback is measured from the point where cumulative cash flow first goes negative, so CF₀ need not be the outlay ([0, −100, 50, 80] pays back at 2.625). It interpolates within the recovery period, assuming even flows, warns if cumulative cash later turns negative again, and returns `None` if the investment is never recovered.
- PI = PV(CF₁..CFₙ) / |CF₀|, and requires CF₀ < 0. (Some textbooks use PV of inflows ÷ PV of outflows; the two agree when only CF₀ is negative.)
- EAA = NPV × r / (1 − (1+r)⁻ⁿ), or NPV / n when r = 0.

## Cost of capital and DCF
- CAPM: Re = Rf + β(Rm − Rf). WACC uses market-value weights, and Rd is multiplied by (1 − T).
- FCFF = EBIT(1 − T) + D&A − CapEx − ΔNWC. Tax is applied only to positive EBIT; no tax credit is modelled for losses.
- NWC = NWC% × revenue, and the base-year NWC = NWC% × base revenue. So ΔNWC = NWC% × Δrevenue.
- End-of-year discounting by default. With the mid-year option, forecast flows are discounted at t − 0.5, while the terminal value is still discounted at t = n.
- Gordon terminal value: FCFFₙ(1+g)/(WACC − g). The app **refuses** to calculate if WACC ≤ g.
- Exit-multiple terminal value: EBITDAₙ × multiple. The implied g is reported.
- Equity = EV − debt + cash. Value per share is shown only when shares outstanding are provided. Minority interests, preference capital, leases and other claims are not deducted automatically; include them in debt if they apply.
- Inputs must be finite numbers; revenue growth must be above −100% and EBIT margin at most 100% in every year.

## Sensitivity and scenarios
- Every grid cell, tornado bar and scenario re-runs `run_dcf`. Invalid combinations return `null` with a reason, never a fabricated number.
- "Revenue growth" and "EBIT margin" are year-by-year. When a tool varies them (sensitivity, tornado, break-even, reverse DCF, Monte Carlo) every year is shifted by the same amount, so the **average** equals the value shown and your year profile is kept; at the base average the base case is reproduced exactly.
- An assumption that the chosen terminal method ignores (exit multiple under Gordon growth, terminal growth under the exit multiple) is refused rather than shown as a flat line.
- Break-even skips points where the model is invalid (for example WACC at or below terminal growth) when looking for a solution. Reverse DCF reports when the price is matched at more than one value.
- Monte Carlo excludes draws that make the model invalid and says how many; results are then conditional on a valid model.
- Scenario attribution applies each changed assumption alone to the base case. The remainder is shown as the interaction effect.

## Variance
- Variance = Actual − Budget. Variance % = (Actual − Budget)/|Budget| × 100.
- **Zero budget:** the percentage is `null` ("not meaningful"); the absolute variance is still shown, and any unbudgeted amount is treated as material.
- **Negative budget:** the percentage uses |Budget|, with a warning note.
- Revenue above budget is favourable; expenses above budget are adverse; zero difference is on budget.
- Decimal arithmetic is used so totals reconcile exactly.
- Price variance = (AP − BP) × AQ; volume variance = (AQ − BQ) × BP; together they sum to the total revenue variance.

## Ratios
- A ratio is computed only when every input is present. Otherwise its status is `missing` and the missing items are listed.
- A zero denominator gives `undefined`. ROE, D/E, P/E, P/B, EV/EBITDA and net debt/EBITDA are `undefined` (not meaningful) when their denominator is zero or negative; ROE is also undefined when closing equity is zero or negative.
- Inputs must be finite. Shares outstanding must be positive, the tax rate is a decimal between 0 and 1, and interest expense is entered as a positive cost.
- Turnover and return ratios use average balances when an opening (`*_prior`) value is supplied. Otherwise they use the closing balance and add a note.
- Day-based ratios use the period length you enter (365 by default).

## Forecasting
- The holdout backtest uses the most recent `h` observations, which the model never sees during fitting (time-aware validation).
- The linear-trend interval is the classical OLS prediction interval. The SES interval follows ETS(A,N,N): σ√(1 + (h−1)α²), where σ = √(SSE/n) of the one-step forecast errors (not centred on their mean, so a persistent bias widens the interval).
- MAPE leaves out periods whose actual value is zero (the note says how many) and is `null` only when every actual is zero.
- If the backtest cannot run on the training window (for example CAGR with a negative value), the forecast is still returned and accuracy is reported as unmeasured.
- Missing values in a series raise an error; they are never treated as zero.

## Rounding
- The engine never rounds. Rounding happens only when values are displayed.

## Budgeting
- Money uses Decimal. Monthly amounts are rounded to 2 decimals, and the rounding remainder goes into the latest month with the largest weight (the last month for even phasing), so the 12 months always sum exactly to the annual figure and a zero-weight month stays zero.
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

## Accounting schedules
- Every journal entry balances to the cent: lines are rounded individually and any one-cent difference goes on the largest line of the short side.
- Deferred tax: income-tax expense = current tax + movement in net deferred tax. A net credit is shown as "Income tax benefit" and a negative current tax as "Income tax receivable", so the entry always balances.
- Leases: the ROU asset may not be negative (incentives larger than the liability plus costs are refused). Under the ASC 842 operating pattern the ROU amortisation is a plug and can be negative in early periods; the result says so. Lease periods and useful lives must be whole numbers.

## Investment analytics
- Maximum drawdown is measured from the value before the first return (1.0), so a first-period loss counts.
- M² (Modigliani) = Rf + Sharpe × σ_benchmark; the excess over the benchmark return is reported separately.
- Sortino uses downside deviation over all n periods, counting only returns below the risk-free rate.
- The two-asset minimum-variance weight can fall outside 0–100% (short selling); the result says so, and the frontier drawn is long-only.

## Indian income tax and GST
- Rules are versioned: income tax `IN-ITA1961-AY2026-27` (FY 2025-26, AY 2026-27) and GST `IN-GST-2026.10`; each result carries its rule-set id and check date. Other assessment years are refused, not approximated.
- Surcharge tiers of 25% and 37% are tested on income excluding dividends and gains under 111A/112/112A; the surcharge on those incomes is capped at 15%, and the new regime caps the rate at 25%. Marginal relief is applied at each threshold.
- Total income is rounded to the nearest ₹10 (s.288A) and tax to the nearest ₹10 (s.288B). 80C + 80CCC + 80CCD(1) are capped together at ₹1.5 lakh (80CCE); 80CCD(2) at 14% (new) or 10% (old) of salary.
- The 234F fee applies only above the basic exemption for the regime, age and residence; 234A interest is on tax rounded down to the nearest ₹100.
- GST Rule 86B (1% of output tax in cash) can be switched off when a proviso applies. B2C large invoices use the ₹2.5 lakh limit before August 2024 and ₹1 lakh after; notes on small B2C supplies are netted into B2CS.
- Open points the app does not decide for you are listed as notes in each result (for example MAT is not checked for co-operatives, and the HSN digits assume your turnover band).
