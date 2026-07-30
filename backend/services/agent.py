"""The triage 'brain'.

Given a work order description, the Claude agent proposes an urgency level and
a technician crew. It ONLY proposes — it never writes an assignment (the write
MCP tool is deliberately never handed to the agent). The deterministic safety
guard in ``safety_rules`` is layered on top of whatever the model returns.

If ``ANTHROPIC_API_KEY`` is unset the module falls back to a transparent
keyword heuristic so the whole app still runs end-to-end for demos.
"""
import json
import os

from backend.services import mcp_client
from backend.services.prompts import AGENT_SYSTEM, AGENT_TOOLS, OUTPUT_SCHEMA, SYSTEM_PROMPT

MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-5")
MAX_AGENT_TURNS = 16  # hard stop so a misbehaving tool-use loop can never run away


def _heuristic(title: str, description: str) -> dict:
    """Keyword-based fallback used when no API key is configured."""
    text = f"{title} {description}".lower()
    crew_keywords = {
        "CNC / Calibration": ["cnc", "calibrat", "tolerance", "tool offset", "axis", "spindle", "positioning", "machining"],
        "Mechanical / Hydraulics": ["hydraulic", "press", "pump", "cylinder", "seal", "bearing", "belt", "leak", "gearbox", "motor mount"],
        "Electrical / Controls": ["panel", "wire", "wiring", "plc", "sensor", "drive", "power", "electric", "voltage", "control", "breaker"],
        "Safety / Hazmat": ["chemical", "spill", "coolant", "fumes", "toxic", "hazard", "guard"],
    }
    crew = "General Maintenance"
    matched = False
    for candidate, kws in crew_keywords.items():
        if any(kw in text for kw in kws):
            crew = candidate
            matched = True
            break
    return {
        "urgency": "routine",
        "crew": crew,
        "is_safety_risk": False,
        "reasoning": "Heuristic triage applied.",
        # A keyword-matched crew is a firmer guess than the catch-all default.
        "confidence": 0.6 if matched else 0.3,
        "source": "heuristic",
    }


def propose_triage(title: str, description: str, location: str | None = None) -> dict:
    """Return a proposal dict: urgency, crew, is_safety_risk, reasoning, source."""
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return _heuristic(title, description)

    try:
        import anthropic
    except ImportError:
        return _heuristic(title, description)

    client = anthropic.Anthropic(api_key=api_key)
    user_content = f"Title: {title}\nLocation: {location or 'unspecified'}\n\nDescription:\n{description}"

    try:
        response = client.messages.create(
            model=MODEL,
            # Adaptive thinking shares this budget with the output, so keep it
            # generous — too low and a long think truncates the JSON mid-object.
            max_tokens=4096,
            thinking={"type": "adaptive"},
            output_config={
                "effort": "medium",
                "format": {"type": "json_schema", "schema": OUTPUT_SCHEMA},
            },
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_content}],
        )
    except Exception as exc:  # network / auth / model errors -> transparent fallback
        result = _heuristic(title, description)
        result["reasoning"] = f"Claude call failed ({exc.__class__.__name__}); used heuristic."
        return result

    text = next((b.text for b in response.content if b.type == "text"), None)
    if not text:
        # e.g. adaptive thinking consumed the whole budget before any output text.
        result = _heuristic(title, description)
        result["reasoning"] = "Claude returned no structured output; used heuristic."
        return result

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        # Truncated / malformed structured output (e.g. hit max_tokens mid-JSON).
        # A single bad response must never fail the whole triage batch.
        result = _heuristic(title, description)
        result["reasoning"] = "Claude output was not valid JSON; used heuristic."
        return result

    # Clamp confidence into [0, 1] defensively (the range is prompt-enforced, not
    # schema-enforced, since the API rejects min/max on number types).
    if isinstance(data.get("confidence"), (int, float)):
        data["confidence"] = max(0.0, min(1.0, float(data["confidence"])))
    data["source"] = "claude"
    return data


# --------------------------------------------------------------------------- #
# Agentic batch triage — a real Claude tool-use loop
#
# Unlike ``propose_triage`` above (one structured call per order, no tools),
# here Claude is handed the actual read_queue MCP tool and drives the queue
# itself: it decides when to read, reads it, and reports one triage decision
# per order via ``submit_triage``. The backend only executes the tool calls
# Claude asks for and feeds the results back.
#
# SAFETY: the agent's toolset is ONLY {read_queue, submit_triage}. The
# write_assignment MCP tool is never handed to it, so it structurally cannot
# write an assignment — submit_triage only ever produces a proposal, and the
# deterministic safety guard is still applied on top of it by the caller.
# --------------------------------------------------------------------------- #
def _exec_read_queue(tool_input: dict, limit: int) -> str:
    """Run the REAL read_queue MCP tool; cap what the agent sees at `limit`."""
    status = tool_input.get("status", "pending")
    rows = mcp_client.read_queue(status, limit)
    return json.dumps(rows)


def _exec_submit_triage(tool_input: dict):
    """Validate one submit_triage call. Returns (tool_result_json, proposal | None)."""
    work_order_id = tool_input.get("work_order_id")
    if not isinstance(work_order_id, int):
        return json.dumps({"ok": False, "error": "work_order_id is required"}), None

    confidence = tool_input.get("confidence")
    if isinstance(confidence, (int, float)):
        confidence = max(0.0, min(1.0, float(confidence)))
    proposal = {
        "work_order_id": work_order_id,
        "urgency": tool_input.get("urgency"),
        "crew": tool_input.get("crew"),
        "reasoning": tool_input.get("reasoning"),
        "confidence": confidence,
        "source": "agent",
    }
    return json.dumps({"ok": True, "work_order_id": work_order_id}), proposal


def agentic_triage(limit: int = 8) -> list[dict] | None:
    """Claude drives the triage itself via a real MCP tool-use loop.

    Returns the list of proposal dicts Claude submitted (each with
    work_order_id/urgency/crew/reasoning/confidence/source), or ``None`` if
    there's no API key, the SDK isn't installed, or the loop errors out —
    callers should fall back to the per-order ``propose_triage`` path then.
    """
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return None
    try:
        import anthropic
    except ImportError:
        return None

    client = anthropic.Anthropic(api_key=api_key)
    messages = [{"role": "user", "content": f"Triage the pending queue now (up to {limit} orders)."}]
    proposals: list[dict] = []

    try:
        for _turn in range(MAX_AGENT_TURNS):
            response = client.messages.create(
                model=MODEL,
                max_tokens=4096,
                system=AGENT_SYSTEM,
                tools=AGENT_TOOLS,
                messages=messages,
            )
            messages.append({"role": "assistant", "content": response.content})
            if response.stop_reason != "tool_use":
                break  # Claude finished — no more tool calls

            tool_results = []
            for block in response.content:
                if getattr(block, "type", None) != "tool_use":
                    continue
                if block.name == "read_queue":
                    content = _exec_read_queue(block.input, limit)
                elif block.name == "submit_triage":
                    content, proposal = _exec_submit_triage(block.input)
                    if proposal is not None:
                        proposals.append(proposal)
                else:
                    content = json.dumps({"ok": False, "error": f"unknown tool {block.name}"})
                tool_results.append({"type": "tool_result", "tool_use_id": block.id, "content": content})
            messages.append({"role": "user", "content": tool_results})
    except Exception:
        return None  # a hiccup mid-loop -> caller falls back to the per-order path

    return proposals
