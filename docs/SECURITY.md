# Security and privacy notes

**This application has not been security-audited and is not production-secure yet.** It is intended for local use until Phase 7 (authentication and per-user isolation) is complete.

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
| Secrets | API keys live only in `backend/.env` (git-ignored) and are read with `SecretStr`. The frontend never receives them |
| AI privacy | No document is sent to any external service in the current version. The assistant (Phase 6) will require consent for each request |

## Not yet implemented (required before public deployment)

- Authentication, authorisation and per-user data isolation. **Today any visitor can list and delete all uploads.**
- Rate limiting.
- A retention policy with automatic expiry. Today, uploads stay until deleted in Settings.
- Malware scanning of uploads.
- Sandboxed code execution (Phase 5): container isolation, no network, CPU/memory/time/output limits, and cleanup after each run.
- HTTPS termination and HSTS (deployment concern).
- Dependency vulnerability scanning in CI.

## Reporting

If you find a security issue, open a private issue in the repository instead of a public one.
