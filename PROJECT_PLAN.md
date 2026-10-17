# Finance Intelligence Studio — Project Plan

This file is the source of truth for progress. Update it at the end of every working session so development can resume reliably.

_Last updated: 2026-10-17 (session 7)_

## Environment found at the start

- Repository contained one earlier project: a single-file personal finance tracker. It was preserved in `legacy/personal-tracker/`.
- Available tools: Node 22, npm/pnpm, Python 3.13, uv, Docker, a Java JDK, LibreOffice and PostgreSQL client.
- PostgreSQL 16 server binaries are installed locally (Docker is not running). Not configured: an AI provider key and OCR (Tesseract).
- npm 10 crashes on this dependency set unless `legacy-peer-deps` is set (see `frontend/.npmrc`), so `react-is` is installed explicitly for Recharts.

## Phase status

| Phase | Scope | Status |
|---|---|---|
| 1. Foundation | Structure, navigation (18 sections), theme (dark/light), premium background, dashboard with labelled sample data, API connection, docs | ✅ Done |
| 2. Upload engine | Multi-file upload with real progress, type detection plus magic-byte checks, Excel/CSV/PDF/Word/text/data/notebook/code/ZIP parsers, previews with cell references, formula detection, data-quality warnings, routing recommendations, delete/replace/retry | ✅ Done (OCR not configured) |
| 3. Core analysis | Forecasting ✅, Variance ✅, Ratios ✅, Budgeting ✅, Financial Statements ✅, Cash Flow & Working Capital ✅ | ✅ Done |
| 4. Advanced finance | Scenarios ✅, Sensitivity (2-way, 1-way, tornado, break-even) ✅, DCF ✅, WACC/CAPM ✅, NPV/IRR/MIRR/payback/PI/EAA ✅ | ✅ Done |
| 5. Data & Code Lab | Editor, explanations, sandboxed execution | ⏳ Not started (uploads already provide syntax checks and outlines) |
| 6. AI & reports | AI assistant ✅ (Claude Opus 5.5, 15 engine tools, consent per question), Excel (live formulas) / Word / PDF report packs ✅ | ✅ Done |
| 7. Persistence & security | Accounts (scrypt, server-side sessions, CSRF/origin check, rate limits), PostgreSQL + Alembic, projects, saved models with versions, history, per-user isolation, retention purge, export and deletion | ✅ Done |
| 8. Final QA | Full accessibility audit, performance, deployment hardening | ⏳ Ongoing per phase |

## Visual refresh (v0.9.1)

- Ink-navy sidebar in both themes, with a glowing active-item marker and grouped navigation.
- Aurora background (emerald, indigo and cyan glows, a fading dot texture and fine grain), static with no motion.
- Page headers are hero panels with a quiet chart illustration.
- Breadcrumb in the top bar.
- Plus Jakarta Sans for headings; Inter is kept for data.
- Gradient primary buttons, KPI cards with an accent bar and delta pills.
- Split sign-in screen with a brand panel listing the real modules.
- Verified: all 24 routes load in light and dark with no console errors; no horizontal overflow at phone width.

## Session 7: professional modules (v0.9.0)

The app is now aimed at practising professionals: CPAs, CFA charterholders, CMAs and auditors.
- **Screener.in import** (`app/files/screener.py`):
  - Parses the "Data Sheet" by its labels.
  - Imports ten years of P&L, balance sheet and cash flow, plus share price and adjusted shares, with cell references.
  - The quarterly block is skipped.
  - Derived lines are labelled; approximations for current assets/liabilities and COGS are opt-in and labelled.
- **Company dashboard** (`app/finance/profile.py`, `components/CompanyDashboard.tsx`) replaces the sample when a company exists; unit-aware amounts (e.g. 2.6L Cr).
- **Cost & Management Accounting** (`app/finance/costing.py`): standard-cost variances with reconciliation checks, CVP, absorption vs marginal costing, limiting factor.
- **Accounting & Audit** (`app/finance/accounting.py`): bonds, leases (ASC 842 / IFRS 16), depreciation, EPS, deferred tax and materiality, all with journal entries; every entry is tested to balance.
- **Investment Analytics** (`app/finance/investments.py`): fixed income, equity models, portfolio and performance analytics, options (BSM, binomial, parity, strategies).
- **Reports & Exports** (`app/reports/builder.py`):
  - Excel pack with live formulas and `fullCalcOnLoad`.
  - Word report.
  - Print/PDF view.
- **AI:** professional system prompt, a technical research mode (standards cited, confirm against authoritative literature) and 8 new tools (15 total).
- Learning Centre renamed Methodology Library; grid items no longer overflow on phones; negative zero never shown.
- **Verified:**
  - 229 backend tests pass on PostgreSQL, including known answers:
    - BSM 10.4506 / 5.5735; Macaulay duration 2.7355; Gordon 42;
    - bond price 92,278.26; lease liability 42,123.64; EPS antidilution;
    - textbook variances, CVP and absorption reconciliation.
  - The report tests recalculate the generated Excel with the app's formula evaluator and match the DCF and ratio engines exactly. LibreOffice recalculation of a downloaded pack also matched.
  - 10 frontend tests pass; the build is clean.
  - Browser checks:
    - all 24 pages in dark and light themes with no console errors;
    - no horizontal overflow at 390 px;
    - end to end: Screener upload → import → dashboard → red flags → Excel/Word download → PDF print.
- **Not verified:** a real Screener export (the parser was built from the published layout and a faithful fixture; the user's own file is its live test), and a real Claude API call (no key here).

## Session 6: unique analysis features and the AI assistant (v0.8.0)

- **Red-Flag Detector** (`app/finance/forensic.py`):
  - Beneish M-score; uses the 5-variable model when SG&A, leverage or accruals inputs are missing, and says so.
  - Altman Z and Z''; Piotroski F-score reported as "x of y tests"; cash-quality warnings.
  - Undefined components (zero denominators) are explained, not filled in.
- **Excel Model Checker** (`app/files/model_check.py`):
  - Finds error values, #REF!, external links and missing sheets.
  - Detects circular references (Tarjan's algorithm), typed constants inside formulas (structural arguments such as ROUND's digits are ignored), formulas inconsistent with both neighbours, values typed over formula rows, balance-sheet mismatches and hidden sheets.
- **Peer Comparison** (`app/finance/peers.py`): 24 metrics with direction-aware ranks (ties share a rank), medians, and warnings when years or tested metrics differ.
- **Reverse DCF and Monte Carlo** (`app/finance/valuation_range.py`):
  - Reverse DCF scans, then bisects, for growth, margin, WACC, terminal growth or exit multiple.
  - Monte Carlo is seeded and reproducible; invalid draws are counted and excluded; 5,000 runs take about 0.2 s.
- **AI Finance Assistant** (`app/ai/assistant.py`, `app/api/ai.py`, `pages/Assistant.tsx`):
  - Claude Opus 5.5 via the official Anthropic SDK, with `fallbacks: "default"` and prompt caching.
  - Seven tools call the tested engines; modes: ask, red flags, model check, challenge my DCF, peers, CMA tutor, report draft.
  - Consent is required per question and resets after each; attachments are framed as data; replies are rendered as safe text; there is a cost estimate per answer.
- Number style setting (Indian or international grouping); new statement items (SG&A, other income, share capital, reserves, long-term debt) with Screener-style label matching.
- **Verified:**
  - 184 backend tests pass on PostgreSQL. AI tests use a fake client, so no paid API calls were made.
  - 8 frontend tests pass; typecheck and build are clean.
  - Browser check: all 21 pages in dark and light themes with no console errors; the new pages fit phone width.
  - End-to-end AI check through the real Anthropic SDK against a local stand-in server confirmed the request shape (model, fallbacks beta, tools, cache control, consented attachments), tool execution and safe rendering of a `<script>` in a reply.
- **Not verified:** no call to the real Claude API was made (no key here). The first real question on the user's machine is its live test.

## Session 5: Excel files without saved formula results

- Fixed a reported upload failure ("The file could not be parsed (IndexError)") on an Excel export (TCS.xlsx). Some exports, such as Screener.in-style workbooks or files written by scripts, store formulas without saved results. The parser trimmed those apparently empty formula columns and then indexed past the edge.
- Formula cells are no longer trimmed.
- New `backend/app/files/formula_eval.py`: a safe, hand-written calculator for common formulas.
  - Supports cell references (including other sheets), arithmetic, comparisons, `&`, and SUM, AVERAGE, MIN, MAX, COUNT, IF, IFERROR, ROUND and similar.
  - No `eval`/`exec`.
  - Depth, cell-count and range limits; circular references are detected.
  - Calculated cells are highlighted and labelled "calculated by the app" with a warning to verify them in Excel.
  - Errors (e.g. `#DIV/0!`) and unsupported functions stay blank, never zero.
- Statement mapping now ignores non-period columns such as "Growth" when picking the latest and prior year.
- 145 backend tests pass on PostgreSQL (8 new). Frontend typecheck, tests and build pass. A browser check with a Screener-style workbook showed 11 highlighted cells and no console errors.
- The user's actual TCS.xlsx was not available here, so the fix was tested on a reconstructed workbook.
- **Follow-up: "Cross-site request blocked" on Windows.** The old copy was still running, so the new website started on port 5174, which the origin check rejected.
  - Outside production, any localhost port is now accepted; production is unchanged and tested.
  - Vite uses `strictPort`, so it fails clearly instead of moving to another port.
  - Both launchers stop an earlier copy of this app that still holds ports 8000 or 5173, detected by its response. Other programs are left alone and reported.
  - Tested here on Linux: an old copy was stopped and a foreign program was not. The Windows PowerShell part (`scripts/stop-old-copy.ps1`) could not be run here.
  - 146 backend tests pass.

## Session 4: one-click local start

- `start-windows.bat` and `start-mac-linux.sh` install missing tools (uv, and Node.js via winget on Windows), use a local SQLite database unless `DATABASE_URL` is set, run the migrations, start both servers and open the browser.
- Verified here on a clean copy of the repository, as if downloaded as a ZIP: the macOS/Linux launcher installed everything, created the SQLite database and started both servers, and the full browser flow passed (sign-up, projects, uploads, save/restore versions, second-user isolation, sign-out).
- **The Windows `.bat` could not be executed here (no Windows machine)**. It was checked for syntax and CRLF line endings only, so the first Windows run is its real test.
- 137 backend tests pass, including the new SQLite path resolution test and the test that production refuses SQLite.

## Verified in session 3 (Phase 7: persistence and security)

- PostgreSQL 16 runs locally with an `fis_app` role and two databases: `finance_studio` (dev) and `finance_studio_test`. The schema is managed by Alembic (`migrations/`), and the test suite runs downgrade → upgrade on every run.
- **135 backend tests pass on PostgreSQL**, and they also pass on the SQLite fallback. The 21 new tests cover:
  - sign-up validation, the cookie flags (HttpOnly, SameSite) and hashed token storage;
  - generic sign-in errors, sign-in rate limiting, rejection of replayed and expired sessions, and password change signing out other devices;
  - CSRF origin blocking, closed registration, and refusing the dev database password in production;
  - **cross-user isolation for every object type**;
  - project cascade deletes, saved-model versions and size limits, and history;
  - retention purge (rows and files), export without secrets, deleting all data, and deleting the account.
- Browser check (headless Chromium):
  - Sign-up rejects a common password.
  - Registration leads to the dashboard, project creation makes the new project active, and uploads land in it.
  - DCF: save v1 → edit → save v2 → restore v1 returns WACC to 11%.
  - Budgeting saves correctly, and the Projects page shows the saved models, files and a six-entry history.
  - Opening a saved model from a project works.
  - Signing out clears drafts.
  - A second user sees an empty workspace and gets "Upload not found" for the first user's file URL.
  - There are no console errors on any route, and the projects page works at phone width.

## Verified in session 2 (Phase 3 completion)

- New engines: `budgeting.py`, `statements.py` and `cashflow.py`, with 35 new tests (114 backend tests in total). The tests cover exact phasing to the cent, incremental and driver-based methods, version diffs, a flexible budget, horizontal and vertical analysis, every reconciliation check (pass, fail, insufficient data, rounding tolerance), quality flags, a cash budget with minimum-balance financing, runway and working-capital cash release.
- Upload import into Financial Statements:
  - Detects statement sheets, maps line items to standard keys and keeps cell references.
  - Reorders newest-first year columns to oldest-first.
  - Skips sheets whose columns are not periods (e.g. Budget/Actual).
- Browser checks:
  - All 18 routes load in dark and light themes with no console errors.
  - The three new pages also work at phone width.
  - Flows tested: statement import → checks; budget new version → edit → version comparison; budget → **Compare with actuals** → Variance pre-filled.

## Verified in session 1

- `cd backend && uv run pytest`: 79 tests pass. They cover known answers checked against Excel's documented examples, multiple and absent IRRs, zero and negative denominators, invalid terminal growth, missing values, malformed uploads, path traversal, zip bombs, oversized files, and a check that uploaded code is never executed.
- `cd frontend && npm test` passes; `npm run typecheck` is clean; `npm run build` succeeds.
- Browser check (headless Chromium): all 18 routes load in dark and light themes at 1440 px, and 8 key pages load at 390 px. There were no console errors and no horizontal scrolling. End-to-end flows passed: upload → ratio import with confirmation; upload → variance import; upload → forecast from a sheet series; DCF invalid-input message; IRR with unconventional flows; blank-input warning.

## Known limitations (honest list)

- **Security hardening still open:**
  - No PostgreSQL row-level security; isolation is enforced in application queries and covered by tests.
  - No email verification, password reset by email, or MFA.
  - Rate limits are in memory, per process.
- Uploads: the original bytes stay on local disk, so multiple servers would need shared storage (e.g. S3).
- Excel formulas without saved results are recalculated only for common functions (see `formula_eval.py`). Lookups (VLOOKUP, XLOOKUP, INDEX/MATCH), whole-column ranges and date functions are left blank and reported. Full recalculation via LibreOffice is a possible future step.
- PDF table extraction uses pdfplumber and can misalign columns, so the app warns you to confirm figures. Scanned PDFs need OCR, which is not configured.
- Legacy `.doc` files are not parsed (the app asks you to save them as `.docx`). `.mat` files are stored but not previewed.
- Forecasting does not model seasonality yet.
- **Budgeting:**
  - "Approved" is a status label without a separate approver role.
  - There is no Excel import of budgets yet.
- **Cash budget:**
  - Financing is drawn to restore the minimum balance, but repayment and interest are not modelled.
- **Saving:** Forecasting and Investment Appraisal have no Save/Open yet. Saving on the other seven model pages is explicit; unsaved edits live only in this browser.
- The currency selector changes labels only; no FX conversion is performed.
- The company dashboard covers saved companies; budgets, forecasts and other saved models are not yet summarised on it.
- Screener import reads annual data only (quarterly results are skipped).
- The accounting schedules assume settlement on period dates (no stub periods or accrued interest between coupon dates), and lease modifications/remeasurements are not modelled.

## Next steps (in order)

1. **Phase 5: Data & Code Lab.**
   - Editor with a diff view.
   - Python/SQL/Java explanations.
   - Docker-based sandbox execution with no network, CPU/memory/time/output limits, and explicit approval for every run.
2. **Phase 8: hardening.**
   - PostgreSQL row-level security, a shared rate limiter, password reset by email, and MFA.
   - Full WCAG 2.1 AA audit, a performance budget, a deployment guide with HTTPS, and a dependency audit in CI.

## How to resume

```bash
sudo pg_ctlcluster 16 main start   # or start PostgreSQL however your OS does it
cd backend && uv sync && uv run alembic upgrade head && uv run pytest
cd ../frontend && npm install && npm run typecheck && npm test
./scripts/dev.sh     # then open http://localhost:5173
```
