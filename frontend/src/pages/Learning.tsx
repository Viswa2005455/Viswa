import { CheckCircle2, Eye, EyeOff, GraduationCap } from 'lucide-react';
import { useState } from 'react';
import { Link } from 'react-router-dom';
import { Badge, Card, Formula, PageHeader } from '../components/ui';

interface Concept {
  id: string; title: string; area: string; tool?: string; definition: string; formula: string; variables: [string, string][];
  example: { setup: string; steps: string[]; answer: string }; interpretation: string; mistakes: string[];
  practice: { q: string; a: string }[];
}

/** Learning content is fixed educational material, kept separate from user data. Worked answers were checked with the app's calculation engine. */
const CONCEPTS: Concept[] = [
  {
    id: 'npv', title: 'Net present value (NPV)', area: 'Investment appraisal', tool: '/investment',
    definition: 'The value today of all future cash flows of a project, minus the initial investment, discounted at the required rate of return.',
    formula: 'NPV = Σ CFₜ / (1 + r)ᵗ   for t = 0 … n   (CF₀ is not discounted)',
    variables: [['CFₜ', 'Net cash flow in period t (outflows negative)'], ['r', 'Discount rate per period (cost of capital)'], ['n', 'Number of periods']],
    example: {
      setup: 'Investment of 1,000 today returns 500 at the end of each of the next 3 years. Cost of capital 10%.',
      steps: ['Year 1: 500 / 1.10 = 454.55', 'Year 2: 500 / 1.10² = 413.22', 'Year 3: 500 / 1.10³ = 375.66', 'Sum of PVs = 1,243.43', 'NPV = 1,243.43 − 1,000 = 243.43'],
      answer: 'NPV = +243.43 → accept: the project earns more than 10%.',
    },
    interpretation: 'Positive NPV adds value at the chosen discount rate; negative NPV destroys value. NPV is in currency, so it measures how much value is created.',
    mistakes: ["Using Excel's NPV() on the whole range, which also discounts CF₀ by one period.", 'Using an annual rate with monthly cash flows.', 'Including sunk costs or ignoring working capital and terminal flows.'],
    practice: [
      { q: 'CF₀ = −2,000; CF₁ = 800; CF₂ = 900; CF₃ = 1,000; r = 8%. What is the NPV?', a: '740.74 + 771.60 + 793.83 − 2,000 = 306.18. Accept.' },
      { q: 'Two mutually exclusive projects: A has the higher IRR, B has the higher NPV. Which should you choose?', a: 'B. With mutually exclusive projects, NPV is the decision rule because it measures value created in currency.' },
    ],
  },
  {
    id: 'irr', title: 'Internal rate of return (IRR) & MIRR', area: 'Investment appraisal', tool: '/investment',
    definition: 'IRR is the discount rate at which NPV equals zero. MIRR replaces IRR\'s assumption of reinvestment at the IRR with explicit finance and reinvestment rates.',
    formula: '0 = Σ CFₜ / (1 + IRR)ᵗ\nMIRR = (FV of inflows at reinvestment rate / PV of outflows at finance rate)^(1/n) − 1',
    variables: [['IRR', 'Rate making NPV zero'], ['n', 'Number of periods']],
    example: {
      setup: 'Same project: −1,000 then +500 for 3 years.',
      steps: ['Find r where 500 × annuity factor(3, r) = 1,000', 'Annuity factor must equal 2.0', 'Trial: r = 23% → 2.011; r = 24% → 1.981', 'Interpolate / solve numerically: r ≈ 23.38%'],
      answer: 'IRR ≈ 23.38% > 10% cost of capital → accept.',
    },
    interpretation: 'Accept a conventional project if IRR exceeds the cost of capital. IRR is a rate, so it does not show scale.',
    mistakes: ['Using IRR when cash flows change sign more than once (there may be several IRRs or none).', 'Ranking mutually exclusive projects of different size by IRR.'],
    practice: [
      { q: 'Cash flows −100, +230, −132. How many IRRs?', a: 'Two: 10% and 20%. The flows change sign twice, so IRR is ambiguous; use NPV.' },
      { q: 'Initial outlay 5,000 and 2,000 per year for 3 years. Is IRR above or below 12%?', a: 'NPV at 12% = −196.34 < 0, so IRR is below 12% (it is about 9.70%).' },
    ],
  },
  {
    id: 'payback', title: 'Payback and discounted payback', area: 'Investment appraisal', tool: '/investment',
    definition: 'The time needed for cumulative cash inflows to recover the initial investment (undiscounted or discounted).',
    formula: 'Payback = years before recovery + (unrecovered amount at start of year / cash flow in that year)',
    variables: [['Unrecovered amount', 'Negative cumulative cash flow at the start of the recovery year']],
    example: {
      setup: '−1,000 then +400 per year for 3 years.',
      steps: ['Cumulative: −600 after Y1, −200 after Y2, +200 after Y3', 'Recovery happens during Y3', 'Payback = 2 + 200/400 = 2.5 years'],
      answer: 'Payback = 2.5 years.',
    },
    interpretation: 'A liquidity/risk screen, not a value measure. Shorter is safer, but cash flows after payback are ignored.',
    mistakes: ['Treating payback as a profitability measure.', 'Ignoring the time value of money (use discounted payback).'],
    practice: [{ q: '−50,000 then 15,000, 20,000, 25,000. Payback?', a: 'After Y2 cumulative = −15,000; 15,000/25,000 = 0.6 → 2.6 years.' }],
  },
  {
    id: 'capm', title: 'CAPM and cost of equity', area: 'Cost of capital', tool: '/dcf',
    definition: 'The Capital Asset Pricing Model estimates the return equity investors require for bearing systematic (market) risk.',
    formula: 'Re = Rf + β × (Rm − Rf)',
    variables: [['Rf', 'Risk-free rate (government bond yield, same currency)'], ['β', 'Sensitivity of the stock to the market'], ['Rm − Rf', 'Market (equity) risk premium']],
    example: { setup: 'Rf = 4%, β = 1.2, expected market return 10%.', steps: ['Market risk premium = 10% − 4% = 6%', 'β × MRP = 1.2 × 6% = 7.2%', 'Re = 4% + 7.2% = 11.2%'], answer: 'Cost of equity = 11.2%.' },
    interpretation: 'Higher beta means higher required return. CAPM only prices systematic risk; company-specific risk is assumed diversifiable.',
    mistakes: ['Mixing a USD risk-free rate with INR cash flows.', 'Using a beta measured against the wrong market index.'],
    practice: [{ q: 'Rf 7%, β 0.8, MRP 6%. Re?', a: '7% + 0.8 × 6% = 11.8%.' }],
  },
  {
    id: 'wacc', title: 'Weighted average cost of capital (WACC)', area: 'Cost of capital', tool: '/dcf',
    definition: 'The blended return required by all capital providers, weighted by the market values of equity and debt.',
    formula: 'WACC = E/(D+E) × Re + D/(D+E) × Rd × (1 − T)',
    variables: [['E, D', 'Market values of equity and debt'], ['Re', 'Cost of equity'], ['Rd', 'Pre-tax cost of debt'], ['T', 'Marginal tax rate (interest tax shield)']],
    example: { setup: 'E = 600, D = 400, Re = 11.2%, Rd = 6%, T = 25%.', steps: ['Weights: E 60%, D 40%', 'After-tax Rd = 6% × 0.75 = 4.5%', 'WACC = 0.6 × 11.2% + 0.4 × 4.5% = 6.72% + 1.80%'], answer: 'WACC = 8.52%.' },
    interpretation: 'The hurdle rate for projects with average company risk, and the discount rate for FCFF in a DCF.',
    mistakes: ['Using book values for weights.', 'Forgetting the tax shield on debt.', 'Using WACC for projects much riskier than the company.'],
    practice: [{ q: 'E 70%, D 30%, Re 14%, Rd 9%, T 30%. WACC?', a: '0.7 × 14% + 0.3 × 9% × 0.7 = 9.8% + 1.89% = 11.69%.' }],
  },
  {
    id: 'dcf', title: 'DCF valuation & terminal value', area: 'Valuation', tool: '/dcf',
    definition: 'Values a business as the present value of its future free cash flows to the firm, plus a terminal value for the years beyond the forecast.',
    formula: 'FCFF = EBIT(1 − T) + D&A − CapEx − ΔNWC\nTVₙ = FCFFₙ₊₁ / (WACC − g)\nEV = Σ FCFFₜ/(1+WACC)ᵗ + TVₙ/(1+WACC)ⁿ',
    variables: [['g', 'Perpetual growth rate after year n (must be below WACC)'], ['ΔNWC', 'Increase in net working capital (a cash outflow)']],
    example: { setup: 'Year-5 FCFF = 120, g = 3%, WACC = 10%.', steps: ['FCFF₆ = 120 × 1.03 = 123.6', 'TV₅ = 123.6 / (0.10 − 0.03) = 1,765.71', 'PV of TV = 1,765.71 / 1.10⁵ = 1,096.37'], answer: 'Terminal value 1,765.71; present value 1,096.37.' },
    interpretation: 'Equity value = EV − debt + cash. Check what share of EV comes from the terminal value — often 60–80%.',
    mistakes: ['g ≥ WACC (formula breaks).', 'Discounting FCFF at the cost of equity.', 'Double-counting cash.'],
    practice: [{ q: 'Why must WACC exceed g in the Gordon Growth model?', a: 'Otherwise the denominator is zero or negative and the perpetuity has no finite value; a firm cannot grow faster than its discount rate forever.' }],
  },
  {
    id: 'variance', title: 'Budget variance analysis', area: 'FP&A', tool: '/variance',
    definition: 'Compares actual results with budget to find, explain and act on differences.',
    formula: 'Variance = Actual − Budget\nVariance % = (Actual − Budget) / |Budget| × 100',
    variables: [['F / A', 'Favourable (helps profit) or adverse (hurts profit)']],
    example: { setup: 'Revenue budget 500, actual 540. Salaries budget 200, actual 230.', steps: ['Revenue: +40 (8.0%) → favourable', 'Salaries: +30 (15.0%) → adverse (cost above budget)', 'Net effect on profit: +40 − 30 = +10'], answer: 'Profit is 10 above budget.' },
    interpretation: 'Investigate material variances; split revenue variances into price and volume, and costs into spending and activity (flexible budget).',
    mistakes: ['Calling every positive number favourable.', 'Computing % variance on a zero budget.', 'Inferring causes without evidence.'],
    practice: [{ q: 'Budget price 50, qty 1,000; actual price 48, qty 1,100. Price and volume variances?', a: 'Price = (48 − 50) × 1,100 = −2,200 A. Volume = (1,100 − 1,000) × 50 = +5,000 F. Total +2,800 F.' }],
  },
  {
    id: 'ratios', title: 'Liquidity ratios', area: 'Ratio analysis', tool: '/ratios',
    definition: 'Measure the ability to meet short-term obligations from short-term resources.',
    formula: 'Current ratio = Current assets / Current liabilities\nQuick ratio = (Current assets − Inventory) / Current liabilities',
    variables: [['Inventory', 'Excluded from quick ratio because it may be slow to convert to cash']],
    example: { setup: 'Current assets 300, of which inventory 60; current liabilities 150.', steps: ['Current ratio = 300 / 150 = 2.0×', 'Quick ratio = (300 − 60) / 150 = 1.6×'], answer: 'Current 2.0×, quick 1.6×.' },
    interpretation: 'Higher is safer, but very high liquidity may mean idle cash. Compare with industry norms.',
    mistakes: ['Comparing across industries with different operating cycles.', 'Ignoring window dressing at period end.'],
    practice: [{ q: 'CA 900, inventory 400, CL 600. Quick ratio?', a: '(900 − 400) / 600 = 0.83×.' }],
  },
  {
    id: 'ccc', title: 'Working capital & cash conversion cycle', area: 'Working capital', tool: '/ratios',
    definition: 'The number of days cash is tied up between paying suppliers and collecting from customers.',
    formula: 'CCC = DIO + DSO − DPO\nDIO = Inventory/COGS × 365 · DSO = Receivables/Revenue × 365 · DPO = Payables/COGS × 365',
    variables: [['DIO', 'Days inventory outstanding'], ['DSO', 'Days sales outstanding'], ['DPO', 'Days payable outstanding']],
    example: { setup: 'DIO 45 days, DSO 40 days, DPO 30 days.', steps: ['CCC = 45 + 40 − 30'], answer: 'CCC = 55 days.' },
    interpretation: 'Shorter cycles free up cash. A negative CCC means suppliers finance operations.',
    mistakes: ['Using revenue instead of COGS for DIO/DPO.', 'Mixing quarterly balances with 365 days.'],
    practice: [{ q: 'Receivables 720, revenue 5,000. DSO?', a: '720 / 5,000 × 365 = 52.6 days.' }],
  },
  {
    id: 'forecast', title: 'Forecasting & growth rates', area: 'FP&A', tool: '/forecasting',
    definition: 'Projecting future values from history and assumptions, while measuring and disclosing uncertainty.',
    formula: 'CAGR = (End / Start)^(1/n) − 1\nMAPE = mean(|Actual − Forecast| / |Actual|) × 100',
    variables: [['n', 'Number of periods between start and end']],
    example: { setup: 'Revenue grew from 100 to 121 over 2 years.', steps: ['121 / 100 = 1.21', '1.21^(1/2) = 1.10'], answer: 'CAGR = 10%.' },
    interpretation: 'Always test forecasts on periods the model has not seen, and show ranges, not single numbers.',
    mistakes: ['Testing on training data.', 'Using simple average growth instead of CAGR.', 'Presenting forecasts as certain.'],
    practice: [{ q: 'Sales 200 → 260 over 3 years. CAGR?', a: '(260/200)^(1/3) − 1 = 9.14%.' }],
  },
  {
    id: 'statements', title: 'Common-size statements', area: 'Financial statements',
    definition: 'Express each line as a percentage of a base (revenue for the income statement, total assets for the balance sheet) to compare across periods and companies.',
    formula: 'Common-size % = Line item / Base × 100',
    variables: [['Base', 'Revenue (income statement) or total assets (balance sheet)']],
    example: { setup: 'Revenue 1,000, COGS 600, operating income 150.', steps: ['COGS = 600/1,000 = 60%', 'Gross margin = 40%', 'Operating margin = 15%'], answer: 'COGS 60%, gross margin 40%, operating margin 15%.' },
    interpretation: 'Vertical analysis reveals cost structure; horizontal analysis (period over period) reveals trends.',
    mistakes: ['Comparing companies with different fiscal year-ends without adjustment.'],
    practice: [{ q: 'Total assets 4,200, inventory 610. Inventory as % of assets?', a: '610 / 4,200 = 14.5%.' }],
  },
  {
    id: 'sensitivity', title: 'Scenario vs sensitivity analysis', area: 'Risk analysis', tool: '/sensitivity',
    definition: 'Sensitivity changes one or two inputs at a time; scenarios change several related inputs together to describe a coherent future.',
    formula: 'Swing = Output(input high) − Output(input low)',
    variables: [['Tornado chart', 'Inputs ranked by swing']],
    example: { setup: 'EV is 2,400 at WACC 10%, 2,150 at 11% and 2,700 at 9%.', steps: ['Swing for ±1pp WACC = 2,700 − 2,150 = 550'], answer: 'A 1-point change in WACC moves EV by roughly ±11%.' },
    interpretation: 'Focus research effort on the inputs with the largest swings.',
    mistakes: ['Treating one-at-a-time sensitivity as if inputs were independent in reality.'],
    practice: [{ q: 'Which chart ranks inputs by impact?', a: 'A tornado chart.' }],
  },
];

export function Learning() {
  const [active, setActive] = useState(CONCEPTS[0].id);
  const c = CONCEPTS.find((x) => x.id === active)!;
  const areas = Array.from(new Set(CONCEPTS.map((x) => x.area)));
  return (
    <div className="page">
      <PageHeader title="Methodology Library" badge={<Badge tone="info">Reference</Badge>}
        subtitle="Methodology notes behind every calculation in the app: definitions, formulas, worked examples, common pitfalls and check questions. Examples here are separate from your financial data." />
      <div className="grid cols-3">
        <Card title="Topics">
          {areas.map((a) => (
            <div key={a} style={{ marginBottom: 10 }}>
              <div className="nav-group" style={{ padding: '6px 0' }}>{a}</div>
              {CONCEPTS.filter((x) => x.area === a).map((x) => (
                <button key={x.id} className={`btn ghost sm`} style={{ width: '100%', justifyContent: 'flex-start', background: x.id === active ? 'var(--accent-soft)' : undefined, color: x.id === active ? 'var(--accent-strong)' : undefined }}
                  onClick={() => setActive(x.id)}>{x.title}</button>
              ))}
            </div>
          ))}
        </Card>
        <div className="span-2 stack page" key={c.id}>
          <Card title={c.title} subtitle={c.area} actions={c.tool && <Link className="btn sm" to={c.tool}>Try it in the app</Link>}>
            <p>{c.definition}</p>
            <div className="mt"><Formula>{c.formula}</Formula></div>
            <div className="mt">{c.variables.map(([k, v]) => <div key={k} className="metric-row"><span className="mono">{k}</span><span className="muted" style={{ textAlign: 'right' }}>{v}</span></div>)}</div>
          </Card>
          <Card title="Worked example" actions={<GraduationCap size={17} className="pos" />}>
            <p className="muted">{c.example.setup}</p>
            <ol style={{ margin: '10px 0', paddingLeft: 20, display: 'grid', gap: 4 }} className="num">{c.example.steps.map((s) => <li key={s}>{s}</li>)}</ol>
            <div className="callout success"><CheckCircle2 size={17} /><b>{c.example.answer}</b></div>
            <p className="mt" style={{ fontSize: 13 }}><b>Interpretation: </b>{c.interpretation}</p>
          </Card>
          <div className="grid cols-2">
            <Card title="Common mistakes">
              <ul style={{ margin: 0, paddingLeft: 18, display: 'grid', gap: 6, fontSize: 13 }}>{c.mistakes.map((m) => <li key={m}>{m}</li>)}</ul>
            </Card>
            <Card title="Practice">
              <div className="stack">{c.practice.map((p) => <Practice key={p.q} {...p} />)}</div>
            </Card>
          </div>
        </div>
      </div>
    </div>
  );
}

function Practice({ q, a }: { q: string; a: string }) {
  const [show, setShow] = useState(false);
  return (
    <div style={{ fontSize: 13 }}>
      <p><b>Q.</b> {q}</p>
      <button className="btn sm ghost mt-sm" onClick={() => setShow((s) => !s)} aria-expanded={show}>{show ? <EyeOff size={14} /> : <Eye size={14} />}{show ? 'Hide answer' : 'Show answer'}</button>
      {show && <div className="callout success mt-sm" style={{ animation: 'fade-in var(--dur) var(--ease)' }}><CheckCircle2 size={16} />{a}</div>}
    </div>
  );
}
