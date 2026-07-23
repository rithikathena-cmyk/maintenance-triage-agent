# Maintenance Triage Agent

A **fully autonomous** maintenance dispatcher. An operator files work orders; a
Claude agent then drives the entire flow itself — it reads the queue, classifies
**urgency**, picks a technician **crew**, and **commits the assignment** through
a real tool-use loop, with no button in the loop. The Streamlit dashboard streams
the agent's live tool activity as it dispatches.

```
Operator ──▶ Work Orders DB
                  ▲  │  read_queue (MCP tool)
                  │  ▼
            Claude AI Agent ── read · triage · pick crew · assign · reject
                  │  drives the loop itself (up to 40 turns / batch)
                  ▼  write_assignment (MCP tool)
            Assignments DB
                  │
                  ▼
        Streamlit Dashboard ── live agent feed · KPIs · queue · history
```

The agent's toolset: `read_queue`, `get_crew_load`, `submit_triage`,
`assign_order` (writes the assignment), and `reject_order`. It loops until the
queue is empty, then stops. The dashboard auto-runs it whenever new work appears
(self-throttled so it fires on new orders, not on every rerun).

## Design notes

- **Autonomous by design.** Claude holds the write tool and dispatches without
  human approval. Manual **Approve / Change crew / Reject** controls remain on
  each queue card as an override for anything the agent leaves behind.
- **Safety keywords always escalate.** Any work order mentioning injury risk is
  force-classified `safety-critical` by a deterministic guard
  (`backend/services/safety_rules.py`), layered on top of the model — the agent
  can never downgrade a hazard — and sorted to the top of the dashboard.

## Dispatcher dashboard

A dark operations console (`frontend/app.py`):

- **Autonomous dispatcher feed** — when there's outstanding work, Claude runs
  automatically and its tool calls stream into a live feed (READ / TRIAGE /
  ASSIGN / REJECT rows). When idle it shows the last run's assigned/triaged/
  rejected tally, with the full activity log in an expander.
- **KPI tiles** — open orders, safety cases, awaiting review, assigned, rejected
  (backed by `GET /stats`).
- **Triage queue** — one card per order the agent hasn't yet dispatched, with an
  urgency chip, a **confidence meter** (the model's own 0–1 score), the crew, its
  reasoning, and any matched safety keywords. Safety-critical orders pinned first.
  Manual **Approve / Change crew / Reject** controls act as an override.
- **Filters** — full-text search, urgency, crew, and a safety-only toggle.
- **Sidebar** — file a new order (auto-picked-up by the dispatcher), the live
  safety-keyword rule list, the crew directory, and a recent-activity feed.

## Security

`.env` holds your database password and `ANTHROPIC_API_KEY`; it is gitignored.
Copy `.env.example` to `.env` to configure a fresh checkout. If a real key was
ever committed or shared, rotate it in the Anthropic console.

## Two MCP tools

| Server | Tool | Used by |
| --- | --- | --- |
| `mcp_servers/queue_server.py` | `read_queue` | the Claude agent (reads the queue) |
| `mcp_servers/assignment_server.py` | `write_assignment` | the backend, driven by the agent's `assign_order` |

## Setup

1. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

2. **Configure `.env`** — set your MySQL credentials in `DATABASE_URL`
   (`mysql+pymysql://root:PASSWORD@localhost:3306/maintenance_triage`).
   Optionally set `ANTHROPIC_API_KEY` (without it, triage falls back to a
   transparent keyword heuristic so the app still runs end-to-end).

3. **Create the database** (one time)
   ```bash
   mysql -u root -p -e "CREATE DATABASE maintenance_triage;"
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

Open the Streamlit URL. The autonomous dispatcher runs on load whenever the
queue has work — watch it read, triage, and assign in the live feed. File a new
order from the sidebar and it's picked up automatically.

## Layout

```
backend/
  database/   database.py · models.py · seed.py
  api/        workorders.py · assignments.py
  services/   agent_service (autonomous dispatcher) · triage_service · claude_service · safety_rules · assignment_service · mcp_client
  schemas/    schemas.py
  main.py
frontend/     app.py
mcp_servers/  queue_server.py · assignment_server.py
```
