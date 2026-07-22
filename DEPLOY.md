# Deploying to Streamlit Community Cloud (single process)

The whole app — Streamlit UI **and** the backend (services + MCP servers) —
runs in one Streamlit process. No separate API server. Data lives in TiDB Cloud.

```
Streamlit Community Cloud (one app)
  frontend  ->  backend services (in-process)
                  ├─ MCP servers (read_queue / write_assignment, spawned on demand)
                  ├─ Claude (Anthropic API)
                  └─ TiDB Cloud (MySQL)  via TLS
```

Two free accounts: **TiDB Cloud** (database) and **Streamlit Community Cloud**
(the app). Plus **GitHub** to host the repo Streamlit deploys from.

---

## Step 0 — Rotate the Anthropic key ⚠️

The key used in local development was exposed. Before going public, open the
[Anthropic console](https://console.anthropic.com/settings/keys), **revoke it and
create a new one**. Never commit it — it goes in Streamlit **Secrets**.

## Step 1 — Database: TiDB Cloud

1. Sign up at <https://tidbcloud.com> → create a **Serverless** cluster (free).
2. Click **Connect** → set/copy a password → note host, port `4000`, user
   (`xxxxxxxx.root`), password.
3. In the cluster's **SQL Editor** run:
   ```sql
   CREATE DATABASE maintenance_triage;
   ```
4. Your `DATABASE_URL` (TLS is handled in code):
   ```
   mysql+pymysql://<user>:<password>@<host>:4000/maintenance_triage
   ```

## Step 2 — Push to GitHub

```bash
git push -u origin main
```
`.gitignore` excludes `.env` and `.streamlit/secrets.toml`, so no secrets ship.

## Step 3 — Deploy on Streamlit Community Cloud

1. Go to <https://share.streamlit.io> → **Create app** → pick your GitHub repo.
2. **Main file path:** `frontend/app.py`.
3. **Advanced settings → Secrets** — paste (from `.streamlit/secrets.toml.example`):
   ```toml
   DATABASE_URL = "mysql+pymysql://<user>:<password>@<host>:4000/maintenance_triage"
   ANTHROPIC_API_KEY = "sk-ant-...your-rotated-key..."
   CLAUDE_MODEL = "claude-opus-4-8"
   SEED_ON_START = "true"
   ```
4. **Deploy.** First boot installs `requirements.txt`, creates the tables, and
   (via `SEED_ON_START`) seeds sample orders if the DB is empty.

## Step 4 — Verify

- Header pills all green: **Backend (in-process) / Database / Queue MCP /
  Assignment MCP / Claude**.
- **Run triage** (try **Agentic mode**) → proposals appear.
- **Approve** one → it moves to Assignment History (a real `write_assignment`
  MCP call against TiDB).

---

## Notes & gotchas

- **Secrets → environment**: `frontend/app.py` bridges Streamlit secrets into
  `os.environ` before importing the backend, so the DB engine and MCP servers
  (which read `DATABASE_URL` / `ANTHROPIC_API_KEY` from the env) see them.
- **MCP on Streamlit Cloud**: the MCP servers are spawned as stdio subprocesses;
  Python 3.11's `ThreadedChildWatcher` makes this work off the main thread.
- **Data durability**: TiDB Cloud persists across app restarts (Community
  Cloud's own disk is ephemeral, but we don't rely on it).
- **Re-seeding**: from a machine with `DATABASE_URL` set to TiDB, run
  `python -m backend.database.seed_extra` / `seed_more` to add more orders.
- The FastAPI app (`backend/main.py`) still exists and works if you ever want to
  run a standalone API (`uvicorn backend.main:app`), but it is not used by the
  Streamlit deploy.
