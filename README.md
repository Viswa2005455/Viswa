# Finance Intelligence Studio

A professional financial analysis workspace for CPAs, CFA charterholders, CMAs, auditors and corporate finance teams. Import company financials (including one-click Screener.in exports), run tested calculations — valuation, ratios, forensic screens, accounting schedules, cost accounting, fixed income, portfolio and derivatives analytics — see every formula and its source, and export audit-ready Excel (live formulas), Word and PDF packs.

> **Status:** this is a work in progress, built in phases. See [PROJECT_PLAN.md](PROJECT_PLAN.md) for what works today and what comes next. In the app, sections marked **"Under development"** are not functional yet.
>
> This is an educational and analytical tool, not investment advice. It has **not** been security-audited for production use. See [docs/SECURITY.md](docs/SECURITY.md).

---

## What works today

| Area | What you can do |
|---|---|
| **Accounts & projects** | Sign up and sign in; every user's files, projects and saved models are private. **My Projects** groups uploads and saved models by company or assignment. **Save / Open** on the DCF, Scenarios, Budgeting, Statements, Cash Flow, Variance and Ratios pages stores every save as a version you can restore. Each project has a history timeline and JSON export. |
| **Overview** | **Company dashboard** for any saved company: ten-year growth, margins, ROE/ROCE, safety, cash conversion and valuation metrics, CAGRs, screening scores and fact-based highlights. A clearly labelled fictional sample dashboard is shown until you import a company. |
| **Upload & Analyse** | Drag-and-drop multiple files: Excel (`.xlsx` `.xlsm` `.xls`), CSV/TSV, PDF, Word (`.docx`), text, JSON/XML/YAML/TOML, notebooks, Python/SQL/Java/JS/TS/R/SAS and more, plus safe ZIP inspection. You get previews with cell references, formula detection, data-quality warnings, detected currency/units/periods, and recommended analyses. |
| **Investment Appraisal** | NPV, IRR (detects multiple IRRs and cases with no IRR), MIRR, payback, discounted payback, PI, EAA, NPV profile, step-by-step table. |
| **DCF Valuation** | Driver-based FCFF model, Gordon growth or exit multiple, mid-year option, WACC/CAPM builder, valuation bridge, full projection table. **Reverse DCF** finds the growth, margin, WACC or terminal value that today's market price implies. **Valuation range (Monte Carlo)** runs thousands of DCFs with uncertain assumptions and shows P10/P50/P90 and the chance the value exceeds the market price. |
| **Scenario Planning** | Base, optimistic, pessimistic and custom scenarios on the DCF model. Includes a comparison table, charts, driver attribution and CSV export. |
| **Sensitivity Analysis** | Two-variable heatmap, one-variable chart, tornado chart and break-even solver. Every cell re-runs the model. |
| **Forecasting** | Linear trend, exponential smoothing, moving average and CAGR. Shows prediction intervals and holdout backtest metrics (MAE, RMSE, MAPE). Can use series from your uploads. |
| **Budgeting** | Monthly budgets by line, department and product, using four methods: direct monthly entry, annual amount with even, custom or seasonal phasing, incremental (prior year ± %) and driver-based (quantity × rate, for zero-based budgeting). Supports versions, approval status, version comparison, a flexible budget, CSV export, and **Compare with actuals**, which sends the budget to Variance Analysis. |
| **Screener.in import** | One click turns a Screener “Export to Excel” file into a company: ten years of P&L, balance sheet and cash flow, share price and shares outstanding, with cell references. Derived lines (EBIT, total equity, total liabilities) are labelled; current assets/liabilities and COGS are offered only as opt-in, labelled approximations. |
| **Financial Statements** | Multi-period income statement, balance sheet and cash flow. Includes horizontal analysis (Δ, Δ%, CAGR), common-size analysis, derived metrics (margins, FCF, NWC, cash conversion, accruals ratio, CapEx/D&A), reconciliation checks (A = L + E, cash roll-forward and more) and earnings-quality indicators. Can import sheets from uploads, including annual reports that list years newest-first. |
| **Cash Flow & Working Capital** | Monthly cash budget with a minimum balance and automatic financing need, runway, receipts vs payments, and working-capital targets (DSO/DIO/DPO) showing how much cash they release. |
| **Variance Analysis** | Budget vs actual with favourable/adverse logic, materiality, a profit bridge (waterfall), largest contributors, price/volume split, and import from uploads. |
| **Accounting & Audit** | Workpaper-ready schedules with journal entries: bonds (effective interest, issuer or investor), leases (ASC 842 finance/operating, IFRS 16 / Ind AS 116), depreciation (SL, DDB with switch, SYD, units), EPS basic and diluted (treasury stock, if-converted, antidilution sequencing), deferred tax (ASC 740 / IAS 12) and audit materiality (AU-C 320 / ISA 320). |
| **Cost & Management Accounting** | Material (price, usage, mix, yield), labour (rate, idle time, efficiency), variable and fixed overhead (expenditure, volume, capacity, efficiency) and sales variances; CVP with multi-product mix, target profit, margin of safety and operating leverage; absorption vs marginal costing reconciliation; limiting-factor product mix. |
| **Investment Analytics** | Bond price/yield, Macaulay and modified duration, convexity, DV01 and shock analysis; Gordon and two-stage DDM, FCFE, residual income and justified multiples; multi-asset portfolio risk/return with risk contributions and frontier; Sharpe, Treynor, Jensen's alpha, M², information ratio, Sortino and drawdown; Black-Scholes-Merton with Greeks, binomial American/European, put-call parity and strategy payoffs. |
| **Income Tax (AY 2026-27)** | Which ITR form to file (ITR-1 to ITR-7) with the reason each simpler form is excluded; individual and HUF tax under the old and new regimes side by side (standard deduction, Chapter VI-A limits, 87A rebate with marginal relief, special-rate gains under 111A/112/112A/115BB with the unexhausted exemption, surcharge with marginal relief, cess, rounding); firm, LLP, company (normal rate, 115BAA, 115BAB, MAT) and co-operative tax; due dates (including Circular 07/2026), the 234F fee and 234A interest. Every rule links to the official page. **It prepares the return; filing is done on the e-filing portal** (direct filing needs registration as an e-Return Intermediary). |
| **GST Returns** | Which returns apply (regular, QRMP, composition, non-resident, ISD, TDS/TCS, UIN, registration threshold) with next due dates by state; GSTR-3B set-off in the order of sections 49/49A and Rule 88A with Rule 86B, interest and late fee; GSTR-1 tables (B2B, B2CL, B2CS, exports, notes, HSN split B2B/B2C, document summary) built from an uploaded sales register, with GSTIN check-digit and tax checks; purchase register vs GSTR-2B reconciliation (matched, differences, probable matches, missing). Files are read in memory and not stored. **Filing is done on the GST portal** (software filing needs a GST Suvidha Provider). |
| **Markets & Risk** | Live quotes, search and price history for shares worldwide through EODHD (NSE, BSE and about 70 exchanges) or Twelve Data, with your own API key kept on the server; or upload a price file (for example an NSE/BSE historical download). Risk check: volatility, largest fall and recovery, beta and correlation to an index, VaR and expected shortfall, Sharpe/Sortino, 52-week range and 200-day trend, a transparent points score and how it fits a conservative, balanced or aggressive profile. Not investment advice. |
| **Reports & Exports** | Company analysis pack: Excel with live formulas (ratios linked to statement cells, fully formula-driven DCF), Word report and print-ready PDF, with an optional AI-drafted memo you review first. |
| **Red-Flag Detector** | Beneish M-score (8- or 5-variable), Altman Z and Z'' scores, Piotroski F-score and cash-quality warnings (profit not turning into cash, receivables or inventory outgrowing sales, rising debt, large other income, low interest cover). Every score shows its formula, parts and inputs. Missing inputs are reported, never treated as zero. |
| **Peer Comparison** | Compare 2–12 saved companies on growth, margins, ROE/ROA/ROCE, efficiency, cash quality, safety, red-flag scores and valuation (with market cap), with ranks, medians and comparability warnings. |
| **Excel Model Checker** | Checks your own Excel models for error values, #REF!, links to other files, missing sheets, circular references, numbers typed inside formulas, inconsistent formulas, values typed over formula rows, balance sheets that do not balance and hidden sheets. Formulas are read, never run. |
| **AI Finance Assistant** | Optional, on Claude Opus 5.5 (needs your own Anthropic API key). Modes: analyse my data, earnings-quality review, model review, challenge the valuation, peer benchmarking, technical accounting research (US GAAP / IFRS / Ind AS) and analysis memo. Fifteen engine tools (ratios, forensic screens, DCF, lease/bond/EPS/deferred-tax schedules, materiality, CVP, bond and option analytics) produce every number, and you consent before each question is sent. |
| **Ratio Analysis** | 29 ratios (liquidity, profitability, efficiency, leverage, valuation). Each shows its formula, inputs, steps and interpretation, and uses average balances when available. Can import statement lines from uploads after you confirm them. |
| **Methodology Library** | The methodology behind the calculations: formulas, worked examples, common pitfalls and check questions. |
| **Settings** | Change your password and see signed-in devices (with "sign out other devices"). Export all your data, delete it, or delete your account. Also: light/dark/system theme, Indian (1,23,45,678) or international number style, reduced motion, learning mode and AI provider status. |

---

## Easiest way: one click (recommended for trying it out)

1. Download the project ZIP and unzip it (right-click → **Extract All**).
2. Open the unzipped folder:
   - **Windows:** double-click **`start-windows.bat`**. If Windows shows "Windows protected your PC", click **More info → Run anyway**.
   - **macOS / Linux:** open Terminal in the folder and run `./start-mac-linux.sh`.
3. Wait. The first run installs everything automatically and takes about 5–10 minutes; later runs take seconds. Your browser then opens **http://localhost:5173**.
4. Click **Create an account**.

What the launcher does:
- Installs **uv** (and through it Python) and, on Windows, **Node.js** if they are missing.
- Creates a local database file at `backend/storage/finance_studio.db`, so you do **not** need to install PostgreSQL for personal use.
- Starts the backend and the website in two windows. Keep those windows open while you use the app, and close them to stop it.
- If an older copy of the app is still running (for example from a previous download), it stops that copy first. Programs that are not this app are never stopped; the launcher tells you instead.

**Updating to a new version:** close the old BACKEND and WEBSITE windows, unzip the new version, and copy your old `backend/storage` folder into the new `backend` folder to keep your account and files. Then run the launcher again.

The local database file is fine for one person on one computer. For anything shared or put online, use PostgreSQL: follow the manual steps below, or set `DATABASE_URL` in `backend/.env` and the launcher will use it.

## Quick start (step by step, with PostgreSQL)

You need four tools installed. Check them in a terminal:

```bash
node --version     # needs v20 or newer          → https://nodejs.org
python3 --version  # needs 3.11 or newer         → https://www.python.org
uv --version       # Python package manager      → https://docs.astral.sh/uv/
psql --version     # PostgreSQL 14 or newer      → see step 2
```

### 1. Get the code

```bash
git clone https://github.com/Viswa2005455/Viswa.git
cd Viswa
```

### 2. Set up the database (first time only)

The app stores accounts, projects, saved models and file metadata in **PostgreSQL**.

1. Install PostgreSQL:
   - **Windows / macOS:** use the installer from https://www.postgresql.org/download/. On macOS, `brew install postgresql@16 && brew services start postgresql@16` also works.
   - **Ubuntu / Debian:** `sudo apt install postgresql`
2. Open a PostgreSQL prompt as the admin user:
   - **macOS / Windows:** `psql -U postgres`
   - **Linux:** `sudo -u postgres psql`
3. Paste these three lines. They create a login and two databases, one for the app and one for the tests:

   ```sql
   CREATE ROLE fis_app LOGIN PASSWORD 'fis_dev_password';
   CREATE DATABASE finance_studio OWNER fis_app;
   CREATE DATABASE finance_studio_test OWNER fis_app;
   ```

   Type `\q` to leave psql.

This password is for **your computer only**; the server refuses to start in production with it. Prefer a hosted database? See [docs/DATABASE.md](docs/DATABASE.md) for Supabase or any managed PostgreSQL.

### 3. Start the backend (the calculation server)

```bash
cd backend
uv sync                          # installs Python packages into backend/.venv
uv run alembic upgrade head      # creates/updates the database tables (run again after every update)
uv run uvicorn app.main:app --reload --port 8000
```

Leave this terminal open. To check it is running, open http://localhost:8000/api/health. You should see `"status":"ok"` and `"database":"ok"`.

### 4. Start the frontend (the website), in a second terminal

```bash
cd frontend
npm install        # first time only
npm run dev
```

Open **http://localhost:5173** and click **Create an account**. Your account exists only in your local database.

> **Shortcut:** `./scripts/dev.sh` runs the migrations and starts both servers in one terminal (macOS/Linux).

### 5. Optional: configuration

Copy `.env.example` to `backend/.env` to change the database address, upload limits, retention period, session length, registration, or to enable an AI provider.

**Turning on the AI assistant**
1. Create an API key at [console.anthropic.com](https://console.anthropic.com) (API keys) and add a prepaid balance under Billing.
2. In `backend/.env` set `FIS_AI_PROVIDER=anthropic`, `ANTHROPIC_API_KEY=<your key>` and `FIS_AI_MODEL=claude-opus-5-5`.
3. Restart the backend (close the BACKEND window and run the launcher again).

The key is read only by the backend and is never sent to the browser. A typical question costs a few US cents; the app shows an estimate under every answer.

---

## Run the tests

```bash
cd backend && uv run pytest          # 135 tests: formulas, parsers, API, accounts, access control, retention
cd frontend && npm test              # formatting / CSV-safety unit tests
cd frontend && npm run typecheck     # TypeScript type check
cd frontend && npm run build         # production build (output in frontend/dist)
```

The backend tests use the `finance_studio_test` database and build it with the real migrations. If PostgreSQL is not running, they fall back to SQLite and print a warning, so the formula tests still run.

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
    budgeting.py         Phasing, budgeting methods, roll-ups, version diff, flexible budget
    statements.py        Horizontal/vertical analysis, reconciliation checks, quality indicators
    cashflow.py          Cash budget with financing need, runway, working-capital targets
  app/files/             Upload engine: detection, parsers, safe ZIP, routing, retention purge
  app/api/               HTTP endpoints (auth, projects, saved models, finance, planning, uploads)
  app/auth/              Password hashing (scrypt), sessions, rate limiting
  app/db/                SQLAlchemy models and database session
  migrations/            Alembic database migrations
  app/ai/                AI provider abstraction (server-side keys only)
  tests/                 pytest suite
frontend/                React · TypeScript · Vite · Recharts
  src/pages/             One file per sidebar section
  src/components/        UI kit, charts, code viewer, sheet preview
  src/lib/               API client, auth and project context, formatting, settings, shared DCF model
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

## Put the app online (Render)

The repository includes a `Dockerfile` (one container serves the website and the API on one address) and a `render.yaml` Blueprint (that container plus a PostgreSQL database).

1. Create a free account at [render.com](https://render.com) and sign in with GitHub.
2. Click **New → Blueprint**, pick this repository and the branch `finance-intelligence-studio`, and click **Apply**.
3. Render builds the app (about 5–10 minutes the first time), creates the database and shows an address such as `https://finance-intelligence-studio.onrender.com`.
4. Open the address and create your account.
5. In Render, open the service → **Environment** and set `FIS_ALLOW_REGISTRATION` to `false`, so nobody else can sign up. To turn on the AI assistant, set `FIS_AI_PROVIDER=anthropic` and `ANTHROPIC_API_KEY` there too.

Things to know:

- **Free plans have limits.** The free web service sleeps after a period without visitors, so the first visit afterwards takes about a minute. Free databases are deleted after a fixed period. Check Render's current pricing page; use a paid plan for real client work.
- **Uploaded files and all data live in the PostgreSQL database**, so the service needs no disk. Back up the database (Render offers backups on paid plans).
- **The site's address is trusted automatically.** Render sets `RENDER_EXTERNAL_URL`, which the app adds to the allowed origins.
- Read [docs/SECURITY.md](docs/SECURITY.md) before putting client data online. The app has not been independently security-audited.

### Other hosts

Any host that runs a Docker container works (Railway, Fly.io, a VPS, Azure Container Apps…):

```
docker build -t finance-studio .
docker run -p 8000:8000 -e DATABASE_URL=postgresql://user:password@host:5432/finance_studio finance-studio
```

The container runs the database migrations, then starts on `$PORT` (default 8000) with `FIS_ENV=production`. Production mode makes cookies `Secure`, sends HSTS and a Content-Security-Policy, hides the API docs, and refuses SQLite and the development database password. Put it behind HTTPS. The container trusts the proxy's `X-Forwarded-For` header (for rate limits), so do not expose its port directly to the internet without a proxy. Request bodies over `FIS_MAX_REQUEST_MB` (default 60) are rejected with 413.
