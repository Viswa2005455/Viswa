# Finance Intelligence Studio

A financial analysis workspace for FP&A, valuation and learning. You can upload spreadsheets, documents or code, run tested financial calculations (NPV, IRR, DCF, ratios, variances, forecasts, scenarios and sensitivities), see every formula and its source, and export the results.

> **Status:** this is a work in progress, built in phases. See [PROJECT_PLAN.md](PROJECT_PLAN.md) for what works today and what comes next. In the app, sections marked **"Under development"** are not functional yet.
>
> This is an educational and analytical tool, not investment advice. It has **not** been security-audited for production use. See [docs/SECURITY.md](docs/SECURITY.md).

---

## What works today

| Area | What you can do |
|---|---|
| **Overview** | KPI cards, revenue forecast with prediction interval, budget vs actual, health ratios. Uses a clearly labelled **fictional sample company**. |
| **Upload & Analyse** | Drag-and-drop multiple files: Excel (`.xlsx` `.xlsm` `.xls`), CSV/TSV, PDF, Word (`.docx`), text, JSON/XML/YAML/TOML, notebooks, Python/SQL/Java/JS/TS/R/SAS and more, plus safe ZIP inspection. You get previews with cell references, formula detection, data-quality warnings, detected currency/units/periods, and recommended analyses. |
| **Investment Appraisal** | NPV, IRR (detects multiple IRRs and cases with no IRR), MIRR, payback, discounted payback, PI, EAA, NPV profile, step-by-step table. |
| **DCF Valuation** | Driver-based FCFF model, Gordon growth or exit multiple, mid-year option, WACC/CAPM builder, valuation bridge, full projection table. |
| **Scenario Planning** | Base, optimistic, pessimistic and custom scenarios on the DCF model. Includes a comparison table, charts, driver attribution and CSV export. |
| **Sensitivity Analysis** | Two-variable heatmap, one-variable chart, tornado chart and break-even solver. Every cell re-runs the model. |
| **Forecasting** | Linear trend, exponential smoothing, moving average and CAGR. Shows prediction intervals and holdout backtest metrics (MAE, RMSE, MAPE). Can use series from your uploads. |
| **Variance Analysis** | Budget vs actual with favourable/adverse logic, materiality, a profit bridge (waterfall), largest contributors, price/volume split, and import from uploads. |
| **Ratio Analysis** | 29 ratios (liquidity, profitability, efficiency, leverage, valuation). Each shows its formula, inputs, steps and interpretation, and uses average balances when available. Can import statement lines from uploads after you confirm them. |
| **Learning Centre** | 12 topics with formulas, worked examples, common mistakes and practice questions (PGDM / CMA level). |
| **Settings** | Light, dark or system theme; reduced motion; learning mode; AI provider status; data deletion. |

---

## Quick start (step by step)

You need three tools installed. Check them in a terminal:

```bash
node --version     # needs v20 or newer
python3 --version  # needs 3.11 or newer
uv --version       # Python package manager; install: https://docs.astral.sh/uv/
```

### 1. Get the code

```bash
git clone https://github.com/Viswa2005455/Viswa.git
cd Viswa
```

### 2. Start the backend (the calculation server)

```bash
cd backend
uv sync                                   # installs Python packages into backend/.venv
uv run uvicorn app.main:app --reload --port 8000
```

Leave this terminal open. To check it is running, open http://localhost:8000/api/health in a browser. You should see `{"status":"ok", ...}`. Interactive API docs are at http://localhost:8000/docs.

### 3. Start the frontend (the website), in a second terminal

```bash
cd frontend
npm install        # first time only
npm run dev
```

Open **http://localhost:5173**. The sidebar's bottom-left corner should say **"API connected"**.

> **Shortcut:** `./scripts/dev.sh` starts both servers in one terminal (macOS/Linux).

### 4. Optional: configuration

Copy `.env.example` to `backend/.env` and edit it to change upload limits or enable an AI provider. The app works fully without this file.

---

## Run the tests

```bash
cd backend && uv run pytest          # 79 tests: financial formulas, parsers, API, security cases
cd frontend && npm test              # formatting / CSV-safety unit tests
cd frontend && npm run typecheck     # TypeScript type check
cd frontend && npm run build         # production build (output in frontend/dist)
```

---

## Project structure

```
backend/                 Python · FastAPI
  app/finance/           Pure, tested calculation engine (no web code)
    tvm.py               NPV, IRR (all roots), MIRR, payback, PI, EAA
    cost_of_capital.py   CAPM, WACC
    dcf.py               FCFF model, terminal value, EV → equity bridge
    sensitivity.py       Two-way grids, tornado, scenarios, break-even
    variance.py          Budget vs actual (Decimal arithmetic), price/volume, flexible budget
    ratios.py            29 ratios with formula, steps, interpretation
    forecasting.py       Linear, SES, moving average, CAGR, holdout backtest
  app/files/             Upload engine: detection, parsers, safe ZIP, routing
  app/api/               HTTP endpoints (finance, uploads, dashboard)
  app/ai/                AI provider abstraction (server-side keys only)
  tests/                 pytest suite
frontend/                React · TypeScript · Vite · Recharts
  src/pages/             One file per sidebar section
  src/components/        UI kit, charts, code viewer, sheet preview
  src/lib/               API client, formatting, settings, shared DCF model
docs/                    Conventions and security notes
legacy/personal-tracker/ The earlier single-file personal finance tracker (kept for reference)
```

**How a calculation flows:** you type in the browser, the page waits 250 ms (debounce), then sends `POST /api/finance/...`. Pydantic validates the inputs, the `app/finance` engine runs the calculation, and the page renders the JSON as charts and tables. All maths runs in the tested Python engine; the browser only formats the numbers for display.

## Key conventions

- Rates are **decimals** in the API (`0.10` = 10%). The UI shows them as percentages.
- NPV treats **CF₀ as today and does not discount it**. Excel's `NPV()` does discount it, so to match, use `=CF0 + NPV(r, CF1:CFn)`.
- **Blank inputs are never turned into zero.** Calculations ask for the missing value instead.
- Example and sample data are always labelled with a badge.

Full details: [docs/FINANCE_CONVENTIONS.md](docs/FINANCE_CONVENTIONS.md).

## Production build and deployment (outline)

1. `cd frontend && npm run build` and serve `frontend/dist/` as static files (for example with Nginx or any static host).
2. Run the API with a process manager, for example `uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 2`, behind HTTPS on the same domain, with `/api` routed to it.
3. Set `FIS_ENV=production` and `FIS_CORS_ORIGINS` to your site's address, and keep `backend/.env` out of git.
4. **Before exposing it to the internet**, complete Phase 7 (authentication and per-user isolation). Right now any visitor could see every upload.
