# Finance Intelligence Studio

A financial analysis workspace for FP&A, valuation and learning. You can upload spreadsheets, documents or code, run tested financial calculations (NPV, IRR, DCF, ratios, variances, forecasts, scenarios and sensitivities), see every formula and its source, and export the results.

> **Status:** this is a work in progress, built in phases. See [PROJECT_PLAN.md](PROJECT_PLAN.md) for what works today and what comes next. In the app, sections marked **"Under development"** are not functional yet.
>
> This is an educational and analytical tool, not investment advice. It has **not** been security-audited for production use. See [docs/SECURITY.md](docs/SECURITY.md).

---

## What works today

| Area | What you can do |
|---|---|
| **Accounts & projects** | Sign up and sign in; every user's files, projects and saved models are private. **My Projects** groups uploads and saved models by company or assignment. **Save / Open** on the DCF, Scenarios, Budgeting, Statements, Cash Flow, Variance and Ratios pages stores every save as a version you can restore. Each project has a history timeline and JSON export. |
| **Overview** | KPI cards, revenue forecast with prediction interval, budget vs actual, health ratios. Uses a clearly labelled **fictional sample company**. |
| **Upload & Analyse** | Drag-and-drop multiple files: Excel (`.xlsx` `.xlsm` `.xls`), CSV/TSV, PDF, Word (`.docx`), text, JSON/XML/YAML/TOML, notebooks, Python/SQL/Java/JS/TS/R/SAS and more, plus safe ZIP inspection. You get previews with cell references, formula detection, data-quality warnings, detected currency/units/periods, and recommended analyses. |
| **Investment Appraisal** | NPV, IRR (detects multiple IRRs and cases with no IRR), MIRR, payback, discounted payback, PI, EAA, NPV profile, step-by-step table. |
| **DCF Valuation** | Driver-based FCFF model, Gordon growth or exit multiple, mid-year option, WACC/CAPM builder, valuation bridge, full projection table. |
| **Scenario Planning** | Base, optimistic, pessimistic and custom scenarios on the DCF model. Includes a comparison table, charts, driver attribution and CSV export. |
| **Sensitivity Analysis** | Two-variable heatmap, one-variable chart, tornado chart and break-even solver. Every cell re-runs the model. |
| **Forecasting** | Linear trend, exponential smoothing, moving average and CAGR. Shows prediction intervals and holdout backtest metrics (MAE, RMSE, MAPE). Can use series from your uploads. |
| **Budgeting** | Monthly budgets by line, department and product, using four methods: direct monthly entry, annual amount with even, custom or seasonal phasing, incremental (prior year ± %) and driver-based (quantity × rate, for zero-based budgeting). Supports versions, approval status, version comparison, a flexible budget, CSV export, and **Compare with actuals**, which sends the budget to Variance Analysis. |
| **Financial Statements** | Multi-period income statement, balance sheet and cash flow. Includes horizontal analysis (Δ, Δ%, CAGR), common-size analysis, derived metrics (margins, FCF, NWC, cash conversion, accruals ratio, CapEx/D&A), reconciliation checks (A = L + E, cash roll-forward and more) and earnings-quality indicators. Can import sheets from uploads, including annual reports that list years newest-first. |
| **Cash Flow & Working Capital** | Monthly cash budget with a minimum balance and automatic financing need, runway, receipts vs payments, and working-capital targets (DSO/DIO/DPO) showing how much cash they release. |
| **Variance Analysis** | Budget vs actual with favourable/adverse logic, materiality, a profit bridge (waterfall), largest contributors, price/volume split, and import from uploads. |
| **Ratio Analysis** | 29 ratios (liquidity, profitability, efficiency, leverage, valuation). Each shows its formula, inputs, steps and interpretation, and uses average balances when available. Can import statement lines from uploads after you confirm them. |
| **Learning Centre** | 12 topics with formulas, worked examples, common mistakes and practice questions (PGDM / CMA level). |
| **Settings** | Change your password and see signed-in devices (with "sign out other devices"). Export all your data, delete it, or delete your account. Also: light/dark/system theme, reduced motion, learning mode and AI provider status. |

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

## Production build and deployment (outline)

1. Create a production PostgreSQL database with a strong password (or use Supabase/RDS/Cloud SQL). Then set `DATABASE_URL` and run `uv run alembic upgrade head`.
2. Run `cd frontend && npm run build` and serve `frontend/dist/` as static files (for example with Nginx or any static host).
3. Run the API behind HTTPS on the **same domain**, with `/api` routed to it, for example:
   `uv run uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1 --proxy-headers`
4. Set the following in `backend/.env` and keep that file out of git:
   - `FIS_ENV=production` — this makes cookies `Secure`, adds HSTS, and refuses the development database password.
   - `FIS_CORS_ORIGINS` — your site's address.
   - `FIS_ALLOW_REGISTRATION=false` — once your own accounts exist, if the site is private.
5. Limit the request body size in the reverse proxy (Nginx: `client_max_body_size 30m;`).
6. Read [docs/SECURITY.md](docs/SECURITY.md) first. Rate limiting is per process: with several workers or servers, use the proxy's rate limiting.
