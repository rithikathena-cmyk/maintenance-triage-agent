# Maintenance Triage Console

A **human-in-the-loop** maintenance dispatcher. Operators file work orders; a
Claude agent proposes an **urgency** level and a technician **crew** for each one;
a dispatcher reviews every card and **Approves**, **Changes crew**, or **Rejects**.
Nothing is ever assigned without a human click — the write path lives only behind
the Approve button.

```
Operator ──▶ Work Orders DB
                  ▲  │  read_queue (MCP tool)
                  │  ▼
            Claude ── proposes urgency + crew (never assigns)
                  │
                  ▼
        Dispatcher reviews each card
          Approve / Change crew / Reject
                  │  write_assignment (MCP tool, only on Approve)
                  ▼
            Assignments DB
```

- **Manual by design.** Claude only *proposes*; a dispatcher decides. The write
  MCP tool (`write_assignment`) is never handed to the agent — it fires only when
  a human clicks Approve.
- **Safety keywords always flag.** Any work order mentioning injury risk is
  force-classified `safety-critical` by a deterministic guard
  (`backend/services/safety_rules.py`), layered on top of the model — the agent
  can never downgrade a hazard.

## Dispatcher dashboard

A dark operations console (`frontend/app.py`):

- **Generate next batch of orders** — the sidebar button loads the next set of 10
  sample work orders (from a 50-order pool, `backend/database/sample_orders.py`)
  and triages them into reviewable cards. Press again for the next set.
- **Reset queue** — clears all orders, proposals, and assignments to start fresh.
- **KPI tiles** — open orders, safety cases, awaiting review, assigned, rejected.
- **Triage queue** — one card per proposal with an urgency chip, a confidence
  meter (the model's own 0–1 score), the crew, its reasoning, and any matched
  safety keywords. Manual **Approve / Change crew / Reject** on each.
- **Filters** — full-text search, urgency, crew, and a safety-only toggle.
- **Sidebar** — generate/reset, file a new order, the safety-keyword rule list,
  the crew directory, and a recent-activity feed.

## Database

The app uses **SQLAlchemy** and works on either:

- **Local SQLite** (default) — a `maintenance_triage.sqlite3` file created at the
  repo root on first run. Zero setup. On Streamlit Community Cloud this file is
  ephemeral (resets on reboot), so it's great for a demo but not durable.
- **Hosted MySQL** (e.g. [Aiven](https://aiven.io), free) — set `DATABASE_URL` for
  data that persists across restarts. TLS is handled in code.

Set the database via the `DATABASE_URL` environment variable / Streamlit secret;
leave it unset to use local SQLite. See [DEPLOY.md](DEPLOY.md).

## Two MCP tools

| Server | Tool | Used by |
| --- | --- | --- |
| `mcp_servers/queue_server.py` | `read_queue` | reading the queue for triage |
| `mcp_servers/assignment_server.py` | `write_assignment` | committing an assignment on Approve |

## Setup

1. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```
2. **(Optional) configure `.env`**
   ```
   # Leave DATABASE_URL unset to use local SQLite, or point at hosted MySQL:
   # DATABASE_URL=mysql://user:pass@host:port/dbname?ssl-mode=REQUIRED
   ANTHROPIC_API_KEY=sk-ant-...     # optional; without it, triage uses a keyword heuristic
   CLAUDE_MODEL=claude-opus-4-8
   ```
   Without `ANTHROPIC_API_KEY` the app still runs end-to-end using a transparent
   keyword heuristic for triage.

## Run

```bash
streamlit run frontend/app.py
```

Open the Streamlit URL. Press **Generate next batch of orders** in the sidebar to
load work orders, then review each card and Approve / Change crew / Reject.

## Deploy

See [DEPLOY.md](DEPLOY.md) — deploy to Streamlit Community Cloud, with optional
hosted MySQL (Aiven) for persistent data.

## Security

`.env` holds your `DATABASE_URL` (with password) and `ANTHROPIC_API_KEY`; it is
gitignored. On Streamlit Cloud these go in **Secrets**, never in a committed file.
If a key or password was ever committed or shared, rotate it.

## Layout

```
backend/
  database/   database.py · models.py · sample_orders.py (50-order pool)
  api/        workorders.py · assignments.py
  services/   triage_service · claude_service · safety_rules · assignment_service · mcp_client
  schemas/    schemas.py
  local_client.py   (in-process backend used by the Streamlit app)
  main.py           (optional standalone FastAPI app; not used by the deploy)
frontend/     app.py
mcp_servers/  queue_server.py · assignment_server.py
```
