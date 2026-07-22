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

from backend.services.safety_rules import CREWS, URGENCY_LEVELS

MODEL = os.getenv("CLAUDE_MODEL", "claude-opus-4-8")

SYSTEM_PROMPT = f"""You are a maintenance triage assistant for a machine-shop /
production-floor maintenance team. Machine operators submit work orders all day
(a leaking hydraulic press, a mis-calibrated CNC, a flickering control panel).

You receive one work order (a title, a free-text description, and optionally a
machine/location). Your job is to PROPOSE — never to assign:

1. An urgency level, one of: {", ".join(URGENCY_LEVELS)}.
   - "safety-critical": anyone could be hurt (pinch points, exposed moving
     parts, hydraulic bursts, arc flash, missing guards, injury reports).
   - "production-stopping": the machine is down or unsafe to run, halting
     output, but no immediate injury risk.
   - "routine": degraded or cosmetic; production continues.
2. The most appropriate technician crew, one of: {", ".join(CREWS)}.
   - "Mechanical / Hydraulics": presses, pumps, cylinders, seals, leaks,
     bearings, belts, mechanical wear.
   - "Electrical / Controls": panels, wiring, PLCs, sensors, drives, power.
   - "CNC / Calibration": CNC machines, calibration, tolerances, tool offsets,
     axis/positioning accuracy.
   - "Safety / Hazmat": spills, chemicals, hazardous conditions, guarding.
   - "General Maintenance": anything that doesn't fit the specialist crews.
3. A one or two sentence justification a lead can read at a glance.
4. Your confidence in this triage, a number from 0.0 to 1.0. Use the full range:
   a clear-cut hazard with an obvious crew is ~0.95+; an ambiguous description
   that could fit two crews, or borderline urgency, should be 0.5-0.8.

A separate deterministic rule independently escalates any order mentioning
injury risk to safety-critical, so err toward flagging risk rather than hiding
it. Respond ONLY with the requested structured fields. Do not assign the work —
a human maintenance lead approves every assignment."""

# JSON schema the model output is constrained to.
_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "urgency": {"type": "string", "enum": URGENCY_LEVELS},
        "crew": {"type": "string", "enum": CREWS},
        "is_safety_risk": {"type": "boolean"},
        "reasoning": {"type": "string"},
        # The API rejects minimum/maximum on number types in structured output;
        # the 0..1 range is enforced by the prompt and clamped after parsing.
        "confidence": {"type": "number"},
    },
    "required": ["urgency", "crew", "is_safety_risk", "reasoning", "confidence"],
    "additionalProperties": False,
}


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
        "reasoning": "Heuristic triage (no ANTHROPIC_API_KEY configured).",
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
            max_tokens=1024,
            thinking={"type": "adaptive"},
            output_config={
                "effort": "medium",
                "format": {"type": "json_schema", "schema": _OUTPUT_SCHEMA},
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
        return _heuristic(title, description)

    data = json.loads(text)
    # Clamp confidence into [0, 1] defensively (the range is prompt-enforced, not
    # schema-enforced, since the API rejects min/max on number types).
    if isinstance(data.get("confidence"), (int, float)):
        data["confidence"] = max(0.0, min(1.0, float(data["confidence"])))
    data["source"] = "claude"
    return data
