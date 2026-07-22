# Maintenance Triage Agent

A human-in-the-loop maintenance dispatcher. An operator files work orders; a
Claude agent reads the queue, classifies **urgency**, and proposes a technician
**crew** — but it only *proposes*. A dispatcher approves (or changes the crew)
on a Streamlit dashboard before any assignment is written.

```
Operator ──▶ Work Orders DB
                  │  read_queue (MCP tool)
                  ▼
            Claude AI Agent ── analyze · detect safety risk · classify urgency · pick crew
                  │  proposed assignment only
                  ▼
        Streamlit Triage Dashboard  [ Approve ] [ Change Crew ]
                  │  Approve
                  ▼  write_assignment (MCP tool)
            Assignments DB
```

## Design guarantees

- **No assignment without an approval click.** The `write_assignment` MCP tool
  is never handed to the agent — it is reachable only through the backend's
  `/assignments/approve` endpoint, which the Approve button calls. (Verified:
  rendering the dashboard performs zero writes; only a click POSTs.)
- **Safety keywords always surface at the top.** Any work order mentioning
  injury risk is force-classified `safety-critical` by a deterministic guard
  (`backend/services/safety_rules.py`), layered on top of the model, and sorted
  to the top of the dashboard.

## Dispatcher dashboard

A dark operations console (`frontend/app.py`):

- **KPI tiles** — open orders, safety cases, awaiting review, assigned, rejected
  (backed by `GET /stats`).
- **Triage queue** — one card per proposal with an urgency chip, a **confidence
  meter** (the model's own 0–1 score), the suggested crew, its reasoning, and any
  matched safety keywords. Safety-critical orders are pinned to the top.
- **Three actions per card** — **Approve** (writes the assignment),
  **Change crew** (edits the proposal, no assignment), **Reject** (declines with
  an optional reason; `POST /proposals/{id}/reject`).
- **Filters** — full-text search, urgency, crew, and a safety-only toggle.
- **Sidebar** — run triage, file a new order, the live safety-keyword rule list,
  the crew directory, and a recent-activity feed.

Re-run triage over orders already awaiting review with `POST /triage?rescan=true`
(never touches assigned or rejected orders).

## Security

`.env` holds your database password and `ANTHROPIC_API_KEY`; it is gitignored.
Copy `.env.example` to `.env` to configure a fresh checkout. If a real key was
ever committed or shared, rotate it in the Anthropic console.

## Two MCP tools

| Server | Tool | Used by |
| --- | --- | --- |
| `mcp_servers/queue_server.py` | `read_queue` | the Claude agent (during triage) |
| `mcp_servers/assignment_server.py` | `write_assignment` | the backend, only on approval |

## Setup

1. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

2. **Configure `.env`** — set your Postgres password in `DATABASE_URL`.
   Optionally set `ANTHROPIC_API_KEY` (without it, triage falls back to a
   transparent keyword heuristic so the app still runs end-to-end).

3. **Create the database** (one time)
   ```bash
   psql -U postgres -c "CREATE DATABASE maintenance_triage;"
   ```

4. **Create tables + seed sample data**
   ```bash
   python -m backend.database.seed
   ```

## Run

Three processes (the MCP servers are spawned on demand by the backend — you do
not start them yourself):

```bash
# 1. Backend API
uvicorn backend.main:app --reload

# 2. Frontend dashboard
streamlit run frontend/app.py
```

Open the Streamlit URL, click **Run triage on pending queue**, then review and
approve on the dashboard.

## Layout

```
backend/
  database/   database.py · models.py · seed.py
  api/        workorders.py · assignments.py
  services/   triage_service · claude_service · safety_rules · assignment_service · mcp_client
  schemas/    schemas.py
  main.py
frontend/     app.py
mcp_servers/  queue_server.py · assignment_server.py
```
