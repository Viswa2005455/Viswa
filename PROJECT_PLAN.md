# Finance Intelligence Studio — Project Plan

This file is the source of truth for progress. Update it at the end of every working session so development can resume reliably.

_Last updated: 2026-10-15 (session 3)_

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
| 6. AI & reports | AI assistant, Excel/PDF/Word report generation | ⏳ Not started (provider abstraction, status endpoint and CSV exports exist) |
| 7. Persistence & security | Accounts (scrypt, server-side sessions, CSRF/origin check, rate limits), PostgreSQL + Alembic, projects, saved models with versions, history, per-user isolation, retention purge, export and deletion | ✅ Done |
| 8. Final QA | Full accessibility audit, performance, deployment hardening | ⏳ Ongoing per phase |

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
- Excel formulas are detected, but the app does not recalculate them. Cells without a cached value are flagged (LibreOffice could be used for recalculation in the future).
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
- The Overview dashboard still shows the fictional sample company; a per-project dashboard built from saved models is a future step.

## Next steps (in order)

1. **Phase 5: Data & Code Lab.**
   - Editor with a diff view.
   - Python/SQL/Java explanations.
   - Docker-based sandbox execution with no network, CPU/memory/time/output limits, and explicit approval for every run.
2. **Phase 6: AI assistant and reports.**
   - AI assistant through the provider abstraction in `backend/app/ai/`, with tool-calling into `app.finance`, consent for each request, and source citations.
   - Report builder with Excel (live formulas), PDF and Word exports, stored as report versions in projects.
3. **Phase 8: hardening.**
   - PostgreSQL row-level security, a shared rate limiter, password reset by email, and MFA.
   - Full WCAG 2.1 AA audit, a performance budget, a deployment guide with HTTPS, and a dependency audit in CI.

## How to resume

```bash
sudo pg_ctlcluster 16 main start   # or start PostgreSQL however your OS does it
cd backend && uv sync && uv run alembic upgrade head && uv run pytest
cd ../frontend && npm install && npm run typecheck && npm test
./scripts/dev.sh     # then open http://localhost:5173
```
