# Security and privacy notes

**This application has not been independently security-audited.** Phase 7 added accounts, per-user isolation and retention, but complete the deployment checklist below before exposing it to the internet.

## Controls implemented

| Area | Control |
|---|---|
| Upload validation | Extension allow-list; magic bytes checked against the extension (ZIP/OLE/PDF/text); configurable per-file size limit and files-per-request limit. The web framework still receives the whole request body first, so set a body-size limit in the reverse proxy (e.g. Nginx `client_max_body_size`) when deploying |
| Stored filenames | Files are stored as `<random-uuid>.bin`. The client filename is display-only metadata, stripped of path components and control characters |
| Path traversal | Upload IDs must be 32 lowercase hex characters before any filesystem access |
| Archives | ZIPs are never extracted to disk. Limits apply to entry count, total uncompressed size and per-entry compression ratio (zip-bomb defence). Members with traversal paths, symlinks or encryption are blocked; nested archives are listed but not opened. The same container checks run before opening `.xlsx`/`.docx` |
| XML | Parsed with `defusedxml` (blocks XXE and entity-expansion attacks); openpyxl also uses defusedxml when it is installed |
| YAML | `yaml.safe_load` only |
| Code | Uploaded code is **never executed**. Python is inspected with `ast.parse`, which does not run code; notebooks are not re-run. Execution is a future Phase 5 feature with a sandbox and explicit approval |
| Rendering | Uploaded text and code are rendered as React text nodes, never as raw HTML |
| CSV export | Cells starting with `= + - @`, tab or CR (other than plain numbers) are prefixed with `'` to prevent spreadsheet formula injection |
| Errors | Unhandled errors return a generic message; stack traces stay in the server log |
| Headers | `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`; CORS limited to configured origins and methods |
| Accounts | Passwords are hashed with scrypt (stdlib `hashlib.scrypt`, N=2¹⁴, r=8, p=1, 16-byte random salt) and checked in constant time. Policy: at least 10 characters, not a common password, and not containing the email name |
| Sessions | A random 256-bit token is set in an `HttpOnly`, `SameSite=Lax` cookie (also `Secure` in production). Only its SHA-256 hash is stored. Sessions are server-side, expire after `FIS_SESSION_DAYS`, are deleted on sign-out, and are revoked on other devices when the password changes |
| Sign-in errors | One message for an unknown email and a wrong password; a dummy hash is checked for unknown emails so response times match |
| Rate limiting | In memory, per process: sign-in 10 per email and 30 per IP per 15 min; sign-up 10 per IP per hour; password change 10 per 15 min; uploads 120 per user per hour |
| CSRF | `SameSite=Lax` cookies, plus a middleware that rejects any state-changing request whose `Origin` is neither this site nor a configured origin |
| Authorisation | Every data endpoint requires a session. Every query is filtered by `user_id`, and another user's object returns 404. Tests cover uploads, projects, saved models, versions, history and exports |
| Privacy controls | Users can export all their data as JSON, delete all data, or delete their account (password plus typed confirmation). Uploads expire after `FIS_UPLOAD_RETENTION_DAYS` and are purged automatically. Browser drafts are cleared on sign-out and when a different user signs in |
| Secrets | API keys and the database URL live only in `backend/.env` (git-ignored); API keys are read with `SecretStr`. The frontend never receives them. In production the server refuses to start with the development database password |
| Headers | `Cache-Control: no-store` on API responses, and HSTS in production |
| AI privacy | No document is sent to any external service in the current version. The assistant (Phase 6) will require consent for each request |

## Not yet implemented

- PostgreSQL row-level security (defence in depth on top of the application-level `user_id` filters).
- A shared rate-limit store for multi-process or multi-server deployments (use the reverse proxy's limits meanwhile).
- Email verification and password reset by email (needs an email provider).
- Multi-factor authentication.
- Malware scanning of uploads.
- Sandboxed code execution (Phase 5).
- Dependency vulnerability scanning in CI.

## Deployment checklist

1. Use HTTPS and set `FIS_ENV=production`; cookies then become `Secure` and HSTS is sent.
2. Use a strong database password in `DATABASE_URL`; the development password is refused in production.
3. Set `FIS_CORS_ORIGINS` to your exact site address.
4. Serve the frontend and `/api` from the **same domain**.
5. Run uvicorn with `--proxy-headers` behind the proxy so rate limits see real client IPs.
6. Set a request body limit in the proxy (for example `client_max_body_size 30m;`).
7. Set `FIS_ALLOW_REGISTRATION=false` if only invited users should have accounts (create them first).
8. Back up the database and `backend/storage/uploads/` (see docs/DATABASE.md).

## Reporting

If you find a security issue, open a private issue in the repository instead of a public one.
