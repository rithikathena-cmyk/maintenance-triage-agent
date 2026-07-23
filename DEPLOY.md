# Deploying to Streamlit Community Cloud (single process)

The whole app — Streamlit UI **and** the backend (services + MCP servers) — runs
in one Streamlit process. No separate API server.

```
Streamlit Community Cloud (one app)
  frontend  ->  backend services (in-process)
                  ├─ MCP servers (read_queue / write_assignment, in-process)
                  ├─ Claude (Anthropic API)      [optional]
                  └─ Database: local SQLite  OR  hosted MySQL (Aiven)
```

You need a **GitHub** repo (Streamlit deploys from it) and a **Streamlit
Community Cloud** account. A database and a Claude key are both optional.

---

## Step 1 — Choose a database

| Option | Persistence | Setup |
| --- | --- | --- |
| **Local SQLite** (default) | ❌ ephemeral on Cloud — resets on reboot | none — leave `DATABASE_URL` unset |
| **Hosted MySQL (Aiven)** | ✅ persists across restarts | free account, one URL |

For a quick demo, skip to Step 3 and leave `DATABASE_URL` unset (SQLite).

### Hosted MySQL with Aiven (for persistent data)
1. Sign up at <https://aiven.io> → **Create service → MySQL → Free plan** → create.
2. Wait until the service is **Running**.
3. On the service **Overview**, copy the connection details (host, port, user
   `avnadmin`, password, database `defaultdb`).
4. Your `DATABASE_URL` — the raw Aiven `mysql://...` form works as-is (the app
   upgrades it to the pymysql driver and handles TLS):
   ```
   mysql://avnadmin:<password>@<host>:<port>/defaultdb?ssl-mode=REQUIRED
   ```

## Step 2 — (Optional) get an Anthropic key

Without a key, triage uses a transparent keyword heuristic and the app still runs.
With one, Claude classifies urgency + crew with reasoning. Create a key at
<https://console.anthropic.com/settings/keys>. It goes in **Secrets**, never in a
commit.

## Step 3 — Push to GitHub

```bash
git push -u origin main
```
`.gitignore` excludes `.env`, `.streamlit/secrets.toml`, and `*.sqlite3`, so no
secrets or local data ship.

## Step 4 — Deploy on Streamlit Community Cloud

1. Go to <https://share.streamlit.io> → **Create app** → pick your repo / `main`.
2. **Main file path:** `frontend/app.py`
3. **Advanced settings → Secrets** — add only what you use (all optional):
   ```toml
   # Omit DATABASE_URL entirely to use local SQLite (ephemeral).
   DATABASE_URL = "mysql://avnadmin:<password>@<host>:<port>/defaultdb?ssl-mode=REQUIRED"
   ANTHROPIC_API_KEY = "sk-ant-...your-key..."
   CLAUDE_MODEL = "claude-opus-4-8"
   ```
4. **Deploy.** First boot installs `requirements.txt` and creates the tables.

## Step 5 — Use it

- Header status pills should be green.
- Sidebar → **Generate next batch of orders** → 10 cards appear. Press again for
  the next set (50 orders across 5 sets).
- Review each card → **Approve / Change crew / Reject**. Approvals write a real
  assignment (via the `write_assignment` MCP tool) and show in Assignment History.
- **Reset queue** clears everything to start from empty.

---

## Notes & gotchas

- **Secrets → environment**: `frontend/app.py` bridges Streamlit secrets into
  `os.environ` before importing the backend, so the DB engine and MCP servers see
  `DATABASE_URL` / `ANTHROPIC_API_KEY`.
- **After changing Secrets, Reboot** (Manage app → ⋮ → Reboot) — a rerun isn't
  enough; the backend reads `DATABASE_URL` at import time.
- **`mysql://` vs `mysql+pymysql://`**: either works — the app forces the pymysql
  driver and strips the `ssl-mode` query param automatically.
- **Data durability**: hosted MySQL persists across restarts; SQLite on Community
  Cloud does not (the disk is ephemeral).
- The FastAPI app (`backend/main.py`) still exists for a standalone API
  (`uvicorn backend.main:app`) but is not used by the Streamlit deploy.
