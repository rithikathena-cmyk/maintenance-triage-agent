# Deploying to the cloud

Architecture (split hosting):

```
Streamlit Community Cloud (frontend)  ──HTTPS──▶  Render (FastAPI + MCP servers)
                                                        └──TLS──▶ TiDB Cloud (MySQL)
```

Three free accounts: **TiDB Cloud** (database), **Render** (backend API), **Streamlit
Community Cloud** (dashboard). Plus **GitHub** to host the repo both deployers pull from.

---

## Step 0 — Rotate the Anthropic key ⚠️

The key currently in your local `.env` was exposed during development. Before going
public, open the [Anthropic console](https://console.anthropic.com/settings/keys),
**revoke it, and create a new one**. Use the new key everywhere below. Never commit it —
`.env` and `.streamlit/secrets.toml` are gitignored; secrets live in each host's
dashboard.

---

## Step 1 — Database: TiDB Cloud

1. Sign up at <https://tidbcloud.com> and create a **Serverless** cluster (free).
2. In the cluster, click **Connect**. Choose **Connect With: General / SQLAlchemy**
   (or "PyMySQL"). Copy the details: host, port `4000`, user (looks like
   `xxxxxxxx.root`), password.
3. Create the database once — in the cluster's **SQL Editor** (or `Chat2Query`) run:
   ```sql
   CREATE DATABASE maintenance_triage;
   ```
4. Assemble your `DATABASE_URL` (TLS is handled in code, no extra params needed):
   ```
   mysql+pymysql://<user>:<password>@<host>:4000/maintenance_triage
   ```
   Keep this handy for Render below.

## Step 2 — Push the repo to GitHub

```bash
git init
git add -A
git commit -m "Maintenance triage app — deploy-ready"
git branch -M main
git remote add origin https://github.com/<you>/maintenance-triage-agent.git
git push -u origin main
```
`.gitignore` already excludes `.env` and `.streamlit/secrets.toml`, so no secrets ship.

## Step 3 — Backend: Render

1. At <https://render.com> → **New +** → **Blueprint**, select your GitHub repo.
   Render reads `render.yaml` and provisions the `maintenance-triage-api` web service.
   (Or **New + → Web Service** and set Start Command
   `uvicorn backend.main:app --host 0.0.0.0 --port $PORT` manually.)
2. In the service's **Environment**, set the two `sync: false` secrets:
   - `DATABASE_URL` = your TiDB URL from Step 1
   - `ANTHROPIC_API_KEY` = your rotated key
   (`CLAUDE_MODEL` and `SEED_ON_START=true` come from `render.yaml`.)
3. Deploy. On first boot the backend creates the tables and — because
   `SEED_ON_START=true` — seeds the sample work orders. Watch the logs for
   `Application startup complete`.
4. Verify: open `https://<your-service>.onrender.com/health/full` — every component
   should report `up` / `configured`. Copy the base URL.

> Free-tier note: the Render service **sleeps after ~15 min idle** and cold-starts
> (~30–60 s) on the next request. The dashboard's first load after idle will be slow.
> You can turn off `SEED_ON_START` after the first successful boot (optional).

## Step 4 — Frontend: Streamlit Community Cloud

1. At <https://share.streamlit.io> → **Create app** → pick your GitHub repo.
2. Set **Main file path** to `frontend/app.py`.
3. Open **Advanced settings → Secrets** and paste:
   ```toml
   BACKEND_URL = "https://<your-service>.onrender.com"
   ```
4. Deploy. The app installs `requirements.txt`, launches, and the header pills will
   go green once it reaches the Render backend.

## Step 5 — Verify end to end

- Header shows **Backend API / Database / Queue MCP / Assignment MCP / Claude Agent**
  all green.
- Click **Run triage on pending queue** → proposals appear.
- **Approve** one → it moves to **Assignment History** (a real `write_assignment` MCP
  call against TiDB).

---

## Notes & gotchas

- **CORS** is already open (`allow_origins=["*"]` in `backend/main.py`), so the
  Streamlit domain can call Render out of the box. Tighten it to your Streamlit URL
  later if you like.
- **MCP on Linux**: the backend spawns the MCP servers as stdio subprocesses; Python
  3.11's default `ThreadedChildWatcher` makes this work off the main thread on Render.
- **Data durability**: TiDB Cloud persists across redeploys (unlike Community Cloud's
  disk). Your approvals/rejections survive restarts.
- **Re-seeding more data**: from a machine with `DATABASE_URL` set to TiDB, run
  `python -m backend.database.seed_extra` / `seed_more` to top up the queue.
