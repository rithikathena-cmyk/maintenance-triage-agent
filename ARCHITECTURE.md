# Maintenance Triage Agent Architecture

This document outlines the end-to-end architecture of the Maintenance Triage Agent, explaining how the AI integrates into the workflow and the security measures in place.

## 1. Data Ingestion (The Queue)
* **Operators file work orders**: Factory workers submit issues containing a title, description, and location (e.g., "Leaking hydraulic press").
* **Database Storage**: These orders are stored in a database (local SQLite or hosted MySQL).
* **MCP Read Server**: The `queue_server.py` MCP server exposes one tool, `read_queue`, that returns work orders by lifecycle status.

## 2. AI Triage Engine (The "Brain") — a real MCP tool-use loop
For a batch run (`backend/services/agent.agentic_triage`, prompted using `backend/services/prompts.py`), Claude is genuinely agentic — it is handed the `read_queue` MCP tool itself and drives the loop:
1. Claude calls `read_queue` (status="pending") — the backend executes the real MCP tool call and returns the results to the model.
2. For each order, Claude calls `submit_triage` with its decision — this is *not* an MCP tool, it's an in-loop reporting call that only ever produces a proposal.
3. Claude stops once every order it read has a submitted triage.

Each `submit_triage` proposal includes:
  1. **Urgency**: `safety-critical`, `production-stopping`, or `routine`.
  2. **Crew**: The most appropriate technician team (e.g., Mechanical, Electrical, CNC).
  3. **Reasoning**: A 1-2 sentence justification for the dispatcher to read.
  4. **Confidence Score**: A 0.0 to 1.0 rating indicating how certain the model is about its triage.

For triaging a *single* just-filed order (no queue to read), the simpler `backend/services/agent.propose_triage` path is used instead: one structured API call with the order's text, constrained by a JSON schema — same four fields, no tool use needed since there's nothing to look up.

**Fallback Heuristic**: If the API key is missing, the SDK isn't installed, or either path errors, the system transparently falls back to a deterministic, keyword-matching heuristic (e.g., "wire" -> Electrical crew).

## 3. Deterministic Safety Guards
Before the AI's proposal is sent to the dispatcher, it must pass through a hard-coded safety layer (`backend/services/safety_rules.py`).
* **Override Rule**: If the original work order text mentions any severe risk keywords (like "injury" or "blood"), the safety guard overrides the AI's response and forces the urgency to `safety-critical`. 
* **Purpose**: This ensures that even if the AI hallucinates or fails to recognize a severe hazard, it cannot downgrade a potentially dangerous situation.

## 4. Human-in-the-Loop Dashboard
The AI's generated proposals are rendered as "cards" on a dark-mode operations console built with Streamlit (`frontend/app.py`).
* The dispatcher sees the original issue, the AI's proposed crew, urgency, reasoning, and the AI's confidence meter.
* The dispatcher has three choices for each card: **Approve**, **Change Crew**, or **Reject**.
* Cards are sorted safety-critical first, then by urgency, then oldest first — a safety-keyword hit always surfaces at the top of the queue, regardless of when it was filed.

## 5. Execution (The Write Server)
This is where the structural security of the system is enforced:
* **The AI's Limitation**: The Claude agent's toolset is *only* `{read_queue, submit_triage}`. It never has access to the `assignment_server` (WRITE) tool — not even behind an "ask permission first" gate. This is a structural guarantee, not a prompted one: the model cannot call a tool it was never given.
* **The Approval Click**: When the dispatcher clicks **Approve**, the backend application—not the AI—invokes the `write_assignment` MCP tool.
* **Database Commit**: This tool updates the Work Orders database to mark the task as 'assigned' and creates a new assignment record.

### MCP Servers
* **`queue_server.py`**: Exposes `read_queue` to read work orders. This is the **only** database tool given to the AI.
* **`assignment_server.py`**: Exposes `write_assignment` to commit assignments. This is **never** given to the AI and is only executed by the backend after human approval.
