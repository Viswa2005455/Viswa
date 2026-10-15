# Database guide

Finance Intelligence Studio stores accounts, projects, saved models and upload metadata in
**PostgreSQL** (version 14 or newer). The original uploaded file bytes are stored on disk in
`backend/storage/uploads/<random-id>.bin`.

## Local mode (SQLite)

The one-click launchers (`start-windows.bat`, `start-mac-linux.sh`) set
`DATABASE_URL=sqlite:///storage/finance_studio.db` when no `DATABASE_URL` is configured.
The same migrations create the same tables in a single file. This mode:

- is meant for **one person on one computer**;
- is refused by the server when `FIS_ENV=production`;
- can be backed up by copying `backend/storage/` while the app is stopped.

To move to PostgreSQL later, create the database (README step 2), set `DATABASE_URL` in
`backend/.env`, and run `uv run alembic upgrade head`. Data in the SQLite file is not copied
automatically; use **Settings → Export all my data** before switching.

## Schema

| Table | Purpose | Key columns |
|---|---|---|
| `users` | Accounts | `email` (unique, lower-cased), `display_name`, `password_hash` (scrypt) |
| `sessions` | Sign-in sessions | `user_id`, `token_hash` (SHA-256 of the cookie token, never the token itself), `expires_at` |
| `projects` | Folders for a company or assignment | `user_id`, `name` (unique per user), `currency`, `units`, `archived` |
| `uploads` | Uploaded file metadata + extracted analysis (JSONB) | `user_id`, `project_id`, `sha256`, `analysis`, `expires_at` |
| `saved_items` | A saved model (DCF, budget, scenarios, …) | `user_id`, `project_id`, `kind`, `name`, `latest_version` |
| `saved_item_versions` | Every saved version of a model | `item_id`, `version`, `note`, `data` (JSONB) |
| `activity` | History of actions (uploads, saves, deletions, sign-ins) | `user_id`, `project_id`, `action`, `detail` |

Relationships and deletion behaviour:

- Deleting a **user** cascades to all of their sessions, projects, uploads, saved items, versions and history. The app also deletes the uploaded files from disk.
- Deleting a **project** deletes its saved items (and their versions) and its uploads (and their files). History entries remain, with the project link cleared.
- Deleting a **saved item** deletes all of its versions.

## Access control

Every table except `saved_item_versions` has a `user_id` column, and every query in `backend/app/api/` filters by the signed-in user's id. (Version rows are always reached through their owned `saved_items` row.)

A request for another user's object returns **404**, not 403, so ids cannot be probed. The test suite (`tests/test_phase7.py::test_users_cannot_see_or_change_each_others_data`) checks this for every object type.

PostgreSQL row-level security (RLS) is **not** enabled yet. It would add defence in depth and is a planned hardening step, especially with Supabase.

## Migrations (Alembic)

```bash
cd backend
uv run alembic upgrade head                      # apply all migrations (run after every update)
uv run alembic current                           # show the database's version
uv run alembic revision --autogenerate -m "..."  # after changing app/db/models.py — always review the generated file
uv run alembic downgrade -1                      # undo the last migration
```

The test suite runs `downgrade base` followed by `upgrade head` on the test database, so every migration is exercised in both directions.

## Retention

- Uploaded files expire `FIS_UPLOAD_RETENTION_DAYS` (default 90) after upload. The expiry date is shown in the app.
- The server purges expired uploads (database rows and files) and expired sessions at startup and every hour. You can also run the purge by hand:
  `uv run python -m app.maintenance purge`
- Saved models and history are kept until the user deletes them, deletes their account, or uses **Settings → Delete all my data**.

## Using a hosted database (Supabase or similar)

The app only needs a PostgreSQL connection string. Authentication stays in the app; Supabase Auth is not used.

1. Create a Supabase project, then open **Project settings → Database → Connection string → URI**.
2. Put it in `backend/.env`, changing the scheme to `postgresql+psycopg://`:
   ```
   DATABASE_URL=postgresql+psycopg://postgres.<ref>:<password>@<host>:5432/postgres?sslmode=require
   ```
3. Run `uv run alembic upgrade head`.

Keep the database password only in `backend/.env` on the server; never put it in frontend code or in git.

## Backups

For a self-hosted database, back up regularly with
`pg_dump -Fc -h <host> -U fis_app finance_studio > backup.dump`.
Also back up `backend/storage/uploads/` if you need the original files. Managed services such as Supabase include automatic backups on paid plans.
