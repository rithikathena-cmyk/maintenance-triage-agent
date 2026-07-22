"""Deterministic safety guard and shared domain constants.

The core rule of the system: **anything mentioning injury risk is always
classified as safety-critical.** This is applied deterministically ON TOP of
whatever the model proposes, so the model can never downgrade a hazardous
work order below safety-critical.
"""
import re

# ---------------------------------------------------------------------------
# Domain vocabulary (single source of truth, imported across the backend)
# ---------------------------------------------------------------------------
# Technician crews for a machine-shop / production-floor maintenance team.
CREWS = [
    "Mechanical / Hydraulics",
    "Electrical / Controls",
    "CNC / Calibration",
    "Safety / Hazmat",
    "General Maintenance",
]

# Urgency taxonomy from the spec (index 0 = most urgent), used to sort the
# dashboard: safety first, then anything that stops production, then routine.
URGENCY_LEVELS = ["safety-critical", "production-stopping", "routine"]
SAFETY_CRITICAL = "safety-critical"

# ---------------------------------------------------------------------------
# Injury / hazard keyword lexicon
# ---------------------------------------------------------------------------
# Matched as whole words / phrases, case-insensitively. Kept intentionally
# broad — a false positive (surfacing a non-urgent order at the top) is far
# cheaper than a false negative (burying a hazard).
SAFETY_KEYWORDS = [
    "injury", "injured", "injure", "hurt", "harm",
    "electrocution", "electrocute", "shock", "live wire", "exposed wire",
    "fire", "smoke", "burn", "burning", "flame", "spark", "sparking",
    "gas leak", "gas smell", "carbon monoxide", "fumes", "toxic", "chemical",
    "asbestos", "mold", "hazard", "hazardous", "danger", "dangerous", "unsafe",
    "fall", "fell", "falling", "collapse", "collapsing", "structural failure",
    "trapped", "stuck person", "unconscious", "bleeding", "wound",
    "slip", "trip hazard", "flooding", "flood", "leak flooding",
    "explosion", "explode", "scald", "scalding", "steam burn",
    "no ventilation", "suffocate", "choking", "eye injury", "cut",
    # machine-floor hazards
    "pinch point", "crush", "crushing", "amputation", "laceration",
    "moving parts", "guard removed", "guard missing", "missing guard",
    "lockout", "tagout", "hydraulic burst", "entanglement",
    "arc flash", "energized", "operator injured", "caught in",
]

# Pre-compile one regex with word boundaries for phrases/words.
_KEYWORD_RE = re.compile(
    r"|".join(rf"\b{re.escape(k)}\b" for k in SAFETY_KEYWORDS),
    flags=re.IGNORECASE,
)


# Negators that flip a nearby hazard word into an *absence* of hazard
# ("no hazard", "not dangerous"). Kept small and conservative on purpose.
_NEGATORS = {
    "no", "not", "without", "never", "none", "zero", "nil", "non",
    "isn't", "aren't", "wasn't", "weren't", "isnt", "arent", "wasnt",
}
_WORD_RE = re.compile(r"[a-z']+")


def detect_safety(text: str):
    """Return (is_safety_critical, sorted list of matched keywords).

    Fail-safe: escalates on *any* non-negated injury/hazard mention. A keyword
    is ignored only when one of the three words immediately before it is a
    negator, so "no hazard" / "not dangerous" don't trip the rule while a real
    "pinch point" still does.
    """
    if not text:
        return False, []

    lowered = text.lower()
    effective = set()
    for m in _KEYWORD_RE.finditer(lowered):
        preceding = _WORD_RE.findall(lowered[max(0, m.start() - 30):m.start()])[-3:]
        if any(w in _NEGATORS for w in preceding):
            continue  # negated mention — absence of hazard, not a risk
        effective.add(m.group(0))
    return (len(effective) > 0, sorted(effective))


def apply_safety_override(description: str, proposed_urgency: str):
    """Force safety-critical urgency when injury-risk language is present.

    Returns (final_urgency, is_safety_critical, matched_keywords). The model's
    proposal is only ever *escalated* here, never softened.
    """
    is_critical, keywords = detect_safety(description)
    if is_critical:
        return SAFETY_CRITICAL, True, keywords
    return proposed_urgency, False, keywords


def urgency_rank(urgency: str) -> int:
    """Sort key: lower = more urgent. Unknown urgencies sort last."""
    try:
        return URGENCY_LEVELS.index(urgency)
    except ValueError:
        return len(URGENCY_LEVELS)
