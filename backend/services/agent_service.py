"""Agentic triage — a real Claude tool-use loop.

Unlike ``claude_service`` (one structured call per order, no tools), here Claude
is an autonomous agent: it is given tools and DRIVES the flow itself in a loop —

    read_queue  (a real MCP tool)  -> Claude fetches the pending orders
    submit_triage (an action tool) -> Claude records its decision per order
    ... Claude keeps calling tools until every order is triaged, then stops.

The backend only executes the tools Claude asks for and feeds results back.

SAFETY: Claude is handed ONLY read/propose tools. The ``write_assignment`` MCP
tool is never in its toolset, so the agent structurally cannot assign work —
``submit_triage`` writes a *proposal* (still requires human approval), and the
deterministic safety guard is re-applied on top of whatever the agent proposes.
"""
import json
import os

from sqlalchemy.orm import Session

from backend.database import models
from backend.services import triage_service
from backend.services.mcp_client import QUEUE_SERVER, run_tool
from backend.services.safety_rules import CREWS, URGENCY_LEVELS

MODEL = os.getenv("CLAUDE_MODEL", "claude-opus-4-8")
_MAX_TURNS = 16  # hard stop so a misbehaving loop can never run away

AGENT_SYSTEM = f"""You are an autonomous maintenance-triage agent for a machine
shop / production floor. You have tools and you drive the triage yourself.

Work in this loop, orchestrating your tools:
1. Call `read_queue` (status="pending") to fetch the work orders waiting for triage.
2. Optionally call `get_crew_load` to see how many orders are already queued per crew,
   so you can balance workload when two crews could both handle an order.
3. For EACH order returned, decide its urgency and the right technician crew, then
   call `submit_triage` with your decision — exactly one call per order.
4. Once you have submitted a triage for every order you read, stop and reply with a
   one-line summary. Do not call read_queue again in a loop.

Urgency is one of: {", ".join(URGENCY_LEVELS)}.
  - "safety-critical": anyone could be hurt — pinch points, exposed moving parts,
    hydraulic bursts, arc flash, missing guards, injury reports.
  - "production-stopping": the machine is down or unsafe to run (halting output),
    but no immediate injury risk.
  - "routine": degraded or cosmetic; production continues.
Crew is one of: {", ".join(CREWS)}.

Set is_safety_risk=true whenever anyone could be injured. Give a one/two sentence
reasoning and a confidence from 0.0 to 1.0 (use the full range). You only PROPOSE —
a human dispatcher approves every assignment. Never try to assign work yourself."""

TOOLS = [
    {
        "name": "read_queue",
        "description": "Read work orders from the maintenance queue by lifecycle status.",
        "input_schema": {
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "enum": ["pending", "triaged", "assigned", "rejected"],
                    "description": "Which orders to read. Use 'pending' for untriaged ones.",
                },
            },
            "required": ["status"],
        },
    },
    {
        "name": "get_crew_load",
        "description": "How many orders are currently awaiting review per crew — use it to balance workload.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "submit_triage",
        "description": "Record your triage decision for ONE work order (creates a proposal, not an assignment).",
        "input_schema": {
            "type": "object",
            "properties": {
                "work_order_id": {"type": "integer"},
                "urgency": {"type": "string", "enum": URGENCY_LEVELS},
                "crew": {"type": "string", "enum": CREWS},
                "is_safety_risk": {"type": "boolean"},
                "reasoning": {"type": "string"},
                "confidence": {"type": "number"},
            },
            "required": ["work_order_id", "urgency", "crew", "is_safety_risk", "reasoning", "confidence"],
        },
    },
]


def _exec_read_queue(tool_input: dict, limit: int) -> str:
    """Run the REAL read_queue MCP tool; cap the batch the agent sees at `limit`."""
    status = tool_input.get("status", "pending")
    rows = run_tool(QUEUE_SERVER, "read_queue", {"status": status, "limit": limit})
    return json.dumps(rows)


def _exec_crew_load(db: Session) -> str:
    """Current count of awaiting-review proposals per crew (for load balancing)."""
    from sqlalchemy import func

    db.rollback()  # fresh snapshot so the agent's own just-submitted rows count
    rows = (
        db.query(models.Proposal.proposed_crew, func.count())
        .join(models.WorkOrder)
        .filter(models.WorkOrder.status == models.STATUS_TRIAGED)
        .group_by(models.Proposal.proposed_crew)
        .all()
    )
    load = {crew: 0 for crew in CREWS}
    for crew, n in rows:
        load[crew] = n
    return json.dumps(load)


def _exec_submit_triage(db: Session, tool_input: dict, submitted: set) -> str:
    """Apply the safety guard and upsert the agent's proposal for one order."""
    wo_id = tool_input.get("work_order_id")
    work_order = db.get(models.WorkOrder, wo_id) if wo_id is not None else None
    if work_order is None:
        return json.dumps({"ok": False, "error": f"work order {wo_id} not found"})
    if work_order.status != models.STATUS_PENDING:
        return json.dumps({"ok": False, "error": f"work order {wo_id} is not pending"})

    conf = tool_input.get("confidence")
    if isinstance(conf, (int, float)):
        conf = max(0.0, min(1.0, float(conf)))
    # source="agent" marks this as coming from the tool-use loop, not a single call.
    proposal_data = {
        "urgency": tool_input["urgency"],
        "crew": tool_input["crew"],
        "reasoning": tool_input.get("reasoning"),
        "confidence": conf,
        "source": "agent",
    }
    triage_service._upsert_proposal(db, work_order, proposal_data)
    db.commit()  # persist per order — the deterministic safety guard ran inside
    submitted.add(wo_id)
    return json.dumps({"ok": True, "work_order_id": wo_id})


def agentic_triage(db: Session, limit: int = 8) -> dict:
    """Triage pending orders with a genuine Claude tool-use loop.

    Returns the same shape as ``triage_service.run_triage`` so the frontend can
    drive it with the identical chunked-progress loop.
    """
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        # No key -> no agent; fall back to the deterministic path transparently.
        return triage_service.run_triage(db, limit=limit)

    # Reuse the same single-run lock so agentic and classic runs never overlap.
    if not triage_service._triage_lock.acquire(blocking=False):
        return {"triaged": 0, "queue_size": 0, "remaining": triage_service._pending_count(db), "busy": True}

    try:
        import anthropic

        client = anthropic.Anthropic(api_key=api_key)
        messages = [{"role": "user", "content": f"Triage the pending queue now (up to {limit} orders)."}]
        submitted: set = set()

        for _turn in range(_MAX_TURNS):
            response = client.messages.create(
                model=MODEL,
                max_tokens=4096,
                system=AGENT_SYSTEM,
                tools=TOOLS,
                messages=messages,
            )
            messages.append({"role": "assistant", "content": response.content})
            if response.stop_reason != "tool_use":
                break  # agent finished (no more tool calls)

            tool_results = []
            for block in response.content:
                if getattr(block, "type", None) != "tool_use":
                    continue
                if block.name == "read_queue":
                    content = _exec_read_queue(block.input, limit)
                elif block.name == "get_crew_load":
                    content = _exec_crew_load(db)
                elif block.name == "submit_triage":
                    content = _exec_submit_triage(db, block.input, submitted)
                else:
                    content = json.dumps({"ok": False, "error": f"unknown tool {block.name}"})
                tool_results.append(
                    {"type": "tool_result", "tool_use_id": block.id, "content": content}
                )
            messages.append({"role": "user", "content": tool_results})

        return {
            "triaged": len(submitted),
            "queue_size": limit,
            "remaining": triage_service._pending_count(db),
            "busy": False,
        }
    except Exception:
        # Never let an agent-loop error fail the request; the classic path is safe.
        db.rollback()
        return triage_service.run_triage(db, limit=limit)
    finally:
        triage_service._triage_lock.release()
