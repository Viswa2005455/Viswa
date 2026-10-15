# Finance Intelligence Studio — Project Plan

This file is the source of truth for progress. Update it at the end of every working session so development can resume reliably.

_Last updated: 2026-10-15_

## Environment found at the start

- Repository contained one earlier project: a single-file personal finance tracker. It was preserved in `legacy/personal-tracker/`.
- Available tools: Node 22, npm/pnpm, Python 3.13, uv, Docker, a Java JDK, LibreOffice and PostgreSQL client.
- Not configured: a PostgreSQL server or Supabase project, an AI provider key, and OCR (Tesseract).
- npm 10 crashes on this dependency set unless `legacy-peer-deps` is set (see `frontend/.npmrc`), so `react-is` is installed explicitly for Recharts.

## Phase status

| Phase | Scope | Status |
|---|---|---|
| 1. Foundation | Structure, navigation (18 sections), theme (dark/light), premium background, dashboard with labelled sample data, API connection, docs | ✅ Done |
| 2. Upload engine | Multi-file upload with real progress, type detection plus magic-byte checks, Excel/CSV/PDF/Word/text/data/notebook/code/ZIP parsers, previews with cell references, formula detection, data-quality warnings, routing recommendations, delete/replace/retry | ✅ Done (OCR not configured) |
| 3. Core analysis | Forecasting ✅, Variance ✅, Ratios ✅, Budgeting ✅, Financial Statements ✅, Cash Flow & Working Capital ✅ | ✅ Done |
| 4. Advanced finance | Scenarios ✅, Sensitivity (2-way, 1-way, tornado, break-even) ✅, DCF ✅, WACC/CAPM ✅, NPV/IRR/MIRR/payback/PI/EAA ✅ | ✅ Done |
| 5. Data & Code Lab | Editor, explanations, sandboxed execution | ⏳ Not started (uploads already provide syntax checks and outlines) |
| 6. AI & reports | AI assistant, Excel/PDF/Word report generation | ⏳ Not started (provider abstraction, status endpoint and CSV exports exist) |
| 7. Persistence & security | Auth, PostgreSQL, projects, history, per-user isolation, retention | ⏳ Not started |
| 8. Final QA | Full accessibility audit, performance, deployment hardening | ⏳ Ongoing per phase |

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

- **No authentication.** Every visitor to a running server can see and delete all uploads. Do not deploy publicly before Phase 7.
- Uploads are stored on local disk (`backend/storage/`) with JSON metadata, not PostgreSQL. There is no automatic retention or expiry yet; deletion is manual (Settings → Delete all uploads).
- Excel formulas are detected, but the app does not recalculate them. Cells without a cached value are flagged (LibreOffice is available on this machine and could be used for recalculation in the future).
- PDF table extraction uses pdfplumber and can misalign columns, so the app warns you to confirm figures. Scanned PDFs need OCR, which is not configured.
- Legacy `.doc` files are not parsed; the app asks you to save them as `.docx`. `.mat` files are stored but not previewed.
- Forecasting does not model seasonality yet.
- **Budgeting:**
  - Versions and approval status live in browser storage, and "Approved" is a label without user sign-off (needs Phase 7).
  - There is no Excel import of budgets yet; upload a Budget/Actual sheet into Variance Analysis instead.
- **Cash budget:**
  - Financing is drawn to restore the minimum balance, but repayment and interest are not modelled.
  - There is no indirect-method cash flow statement builder.
- The scenario engine drives DCF assumptions only (growth, margin, WACC, g, tax, CapEx, D&A, NWC). Volume × price, salary, inflation and interest-rate drivers need the Budgeting operating model.
- The DCF, scenarios and preferences are saved in browser `localStorage` (per browser, per device).
- The currency selector changes labels only; no FX conversion is performed.
- There is no rate limiting yet.

## Next steps (in order)

1. **Phase 7 early.** Authentication and PostgreSQL (Supabase or self-hosted), Alembic migrations, `user_id` on every row plus row-level security, projects, saved models and scenarios, analysis history, retention policy. This is the prerequisite for any public deployment.
2. **Phase 5.** Data & Code Lab: editor with diff, Python/SQL/Java explanations, and Docker-based sandbox execution (no network, CPU/memory/time/output limits, explicit approval for every run).
3. **Phase 6.**
   - AI assistant through the provider abstraction in `backend/app/ai/`, with tool-calling into `app.finance`, per-request consent, and source citations.
   - Report builder with Excel (live formulas), PDF and Word exports.
4. **Phase 8.** Full WCAG 2.1 AA audit, performance budget, rate limiting, deployment guide with HTTPS, and a dependency audit.

## How to resume

```bash
cd backend && uv sync && uv run pytest
cd ../frontend && npm install && npm run typecheck && npm test
./scripts/dev.sh     # then open http://localhost:5173
```
