"""Maintenance Work Order Triage — dispatcher console.

A human-in-the-loop dashboard. The Claude agent proposes an urgency level and a
technician crew for each incoming work order; a dispatcher reviews, then Approves
(writes an assignment), reassigns the crew, or Rejects. Nothing is ever assigned
without an explicit click — the write path lives only behind the Approve button.

Layout:
  Header .......... product title + live connection status
  KPI tiles ....... open orders · safety cases · awaiting review · assigned
  Filter bar ...... search · urgency · crew · safety-only
  Queue ........... one styled card per proposal, safety-critical pinned on top
  Sidebar ......... run triage · file order · safety rules · crews · activity
"""
import os
import sys
from datetime import datetime, timezone

# Streamlit runs this file with only its own folder (frontend/) on sys.path, so
# the sibling `backend` package isn't importable by default. Put the repo root
# on the path first, before any `from backend import ...`.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

import streamlit as st
from dotenv import load_dotenv

load_dotenv()  # local .env (no-op on Streamlit Community Cloud)

# Single-process deploy: the backend runs IN this Streamlit process (no separate
# server). Bridge Streamlit secrets into os.environ BEFORE importing the backend,
# because the DB engine reads DATABASE_URL at import time.
try:
    _secrets = dict(st.secrets)  # flatten top-level secrets to a plain dict
except Exception:
    _secrets = {}  # no secrets configured (e.g. local dev uses .env instead)
for _k in ("DATABASE_URL", "ANTHROPIC_API_KEY", "CLAUDE_MODEL", "SEED_ON_START"):
    if not os.getenv(_k) and _k in _secrets:
        os.environ[_k] = str(_secrets[_k])

SECRET_HAS_DB = "DATABASE_URL" in _secrets  # for the diagnostic gate below

from backend import local_client as api  # noqa: E402  (must follow the env bridge)

_DB_URL = os.getenv("DATABASE_URL", "")
DB_HOST = _DB_URL.split("@")[-1].split("/")[0] if "@" in _DB_URL else "local database"

st.set_page_config(
    page_title="Maintenance Triage Console",
    page_icon="🔧",
    layout="wide",
    initial_sidebar_state="expanded",
)

# --------------------------------------------------------------------------- #
# Design tokens
# --------------------------------------------------------------------------- #
URGENCY = {
    "safety-critical": {"label": "Safety Critical", "color": "#f85149", "dot": "🔴", "rank": 0},
    "production-stopping": {"label": "Production Stopping", "color": "#d29922", "dot": "🟠", "rank": 1},
    "routine": {"label": "Routine", "color": "#3fb950", "dot": "🟢", "rank": 2},
}
DEFAULT_URGENCY = {"label": "Unclassified", "color": "#7d8894", "dot": "⚪", "rank": 3}

# Brand — refined premium dark (muted indigo, GitHub/Linear aesthetic)
BRAND = "#6b7cff"


def u(urgency):
    return URGENCY.get(urgency, DEFAULT_URGENCY)


# --------------------------------------------------------------------------- #
# API helpers
# --------------------------------------------------------------------------- #
def api_get(path, **params):
    """Call the in-process backend (no network hop)."""
    return api.get(path, **params)


def api_post(path, json=None, **params):
    return api.post(path, json=json, **params)


def backend_online():
    """The backend is in-process; this really checks the database is reachable."""
    try:
        api.get("/stats")
        return True
    except Exception:
        return False


@st.cache_data(ttl=60)
def get_meta():
    return api_get("/meta")


@st.cache_data(ttl=15)
def get_health():
    """Live subsystem status (backend memoizes the expensive MCP probes)."""
    try:
        return api_get("/health/full")
    except Exception:
        return None


def humanize(ts):
    """'2026-07-22T09:15:00' -> 'Jul 22, 09:15'. Best-effort, tolerant of nulls."""
    if not ts:
        return "—"
    try:
        dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        return dt.strftime("%b %d, %H:%M")
    except Exception:
        return str(ts)


def ago(ts):
    """Compact relative time for the activity feed."""
    if not ts:
        return ""
    try:
        dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        delta = datetime.now(timezone.utc) - dt
        s = int(delta.total_seconds())
        if s < 60:
            return "just now"
        if s < 3600:
            return f"{s // 60}m ago"
        if s < 86400:
            return f"{s // 3600}h ago"
        return f"{s // 86400}d ago"
    except Exception:
        return ""


# --------------------------------------------------------------------------- #
# Global styling
# --------------------------------------------------------------------------- #
st.markdown(
    """
    <style>
      :root {
        --bg:#0d1117; --surface:#161b22; --surface-2:#1c2129; --surface-3:#232a33;
        --border:#232a33; --border-soft:#1c2129;
        --text:#e6edf3; --text-2:#aeb9c4; --text-3:#7d8894;
        --brand:#6b7cff; --brand-dim:#5563e8; --brand-soft:rgba(107,124,255,.13);
        --safety:#f85149; --safety-soft:rgba(248,81,73,.13); --safety-bd:rgba(248,81,73,.40);
        --amber:#d29922; --amber-soft:rgba(210,153,34,.14);
        --green:#3fb950;
        --shadow:0 1px 2px rgba(1,4,9,.55);
        --font:"Inter",-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
      }
      html, body, [class*="css"] { font-family:var(--font); letter-spacing:-.006em; }
      .stApp { background:var(--bg); }
      .block-container { padding-top: 2rem; padding-bottom: 3rem; max-width: 1400px; }
      #MainMenu, footer { visibility: hidden; }
      /* Keep the header transparent but functional — it holds the sidebar toggle,
         so hiding it entirely would strand a collapsed sidebar with no way back. */
      header[data-testid="stHeader"] { background: transparent; }
      [data-testid="stSidebarCollapseButton"],
      [data-testid="stSidebarCollapsedControl"],
      [data-testid="stExpandSidebarButton"] { visibility: visible !important; }
      [data-testid="stSidebarCollapsedControl"] button { color: var(--brand) !important; }

      /* ---- Top app bar ---- */
      .appbar {
        display:flex; align-items:center; justify-content:space-between; gap:1rem;
        padding:1.05rem 1.4rem; margin-bottom:1.4rem; border-radius:12px;
        background:var(--surface);
        border:1px solid var(--border); box-shadow:var(--shadow); position:relative;
      }
      .appbar .title { font-size:1.5rem; font-weight:680; letter-spacing:-.025em; color:#f6f9fc;
        display:flex; align-items:center; gap:.5rem; }
      .appbar .subtitle { font-size:.83rem; color:var(--text-2); margin-top:3px; letter-spacing:0; }
      .pillrow { display:flex; gap:.45rem; flex-wrap:wrap; justify-content:flex-end; }
      .pill {
        font-size:.71rem; font-weight:550; padding:.3rem .65rem; border-radius:6px;
        border:1px solid var(--border); color:var(--text-2); background:var(--surface-2);
        white-space:nowrap; display:inline-flex; align-items:center; gap:.4rem;
      }
      .pill.on   { border-color:var(--border); color:var(--text-2); background:var(--surface-2); }
      .pill.on .dot   { color:var(--green); }
      .pill.warn .dot { color:var(--amber); }
      .pill.off  { border-color:var(--safety-bd); color:var(--safety); background:var(--safety-soft); }
      .pill.off .dot  { color:var(--safety); }
      .pill .dot { font-size:.58rem; line-height:1; }

      /* ---- KPI tiles ---- */
      .kpi {
        border:1px solid var(--border); border-radius:10px; padding:1.05rem 1.15rem; background:var(--surface);
        position:relative; overflow:hidden; height:100%;
        transition:border-color .14s ease;
      }
      .kpi:hover { border-color:var(--surface-3); }
      .kpi::before {
        content:""; position:absolute; left:0; top:0; bottom:0; width:3px;
        background:var(--accent,var(--brand));
      }
      .kpi .label { font-size:.72rem; text-transform:uppercase; letter-spacing:.06em; color:var(--text-2); font-weight:600; }
      .kpi .value { font-size:2.2rem; font-weight:680; color:#f6f9fc; line-height:1.1; margin-top:.35rem;
        letter-spacing:-.03em; font-variant-numeric:tabular-nums; }
      .kpi .foot  { font-size:.73rem; color:var(--text-3); margin-top:.25rem; }

      /* ---- Work order card ---- */
      .wocard {
        border:1px solid var(--border); border-left:3px solid var(--accent,var(--brand));
        border-radius:10px; padding:1.1rem 1.25rem .45rem; background:var(--surface);
        margin-bottom:.25rem; transition:border-color .14s ease;
      }
      .wocard:hover { border-color:var(--surface-3); border-left-color:var(--accent,var(--brand)); }
      .wocard .id     { font-family:ui-monospace,"SF Mono",Menlo,monospace; color:var(--text-3); font-size:.76rem; font-weight:600; letter-spacing:.02em; }
      .wocard .ttl    { font-size:1.14rem; font-weight:640; color:#f6f9fc; margin:.15rem 0 .4rem; letter-spacing:-.02em; }
      .wocard .meta   { font-size:.79rem; color:var(--text-2); margin-bottom:.6rem; }
      .wocard .meta b { color:var(--text); font-weight:600; }
      .wocard .desc   { font-size:.9rem; color:#cbd5dd; line-height:1.55; }

      .chip {
        display:inline-block; font-size:.72rem; font-weight:700; padding:.24rem .65rem;
        border-radius:999px; color:#0b0f12; letter-spacing:.01em;
      }
      .badge-safety {
        display:inline-block; font-size:.7rem; font-weight:750; padding:.22rem .55rem; border-radius:6px;
        background:var(--safety-soft); color:var(--safety); border:1px solid var(--safety-bd); letter-spacing:.04em;
      }
      .kw {
        display:inline-block; font-size:.7rem; padding:.14rem .5rem; border-radius:6px; margin:.1rem .25rem .1rem 0;
        background:var(--amber-soft); color:var(--amber); border:1px solid rgba(251,191,36,.28); font-weight:600;
      }
      .reason {
        font-size:.84rem; color:var(--text-2); font-style:italic; border-left:2px solid var(--brand-dim);
        padding-left:.75rem; margin:.55rem 0;
      }

      /* confidence meter */
      .confwrap { margin-top:.25rem; }
      .conflabel { font-size:.71rem; color:var(--text-2); display:flex; justify-content:space-between; }
      .conftrack { height:7px; background:var(--surface-2); border-radius:999px; overflow:hidden; margin-top:.25rem; }
      .conffill  { height:100%; border-radius:999px; }

      .kv { font-size:.72rem; text-transform:uppercase; letter-spacing:.06em; color:var(--text-2); font-weight:650; }
      .kvval { font-size:.93rem; color:var(--text); font-weight:650; }

      /* sidebar */
      section[data-testid="stSidebar"] { background:#0f131a; border-right:1px solid var(--border); }
      .sb-h { font-size:.73rem; text-transform:uppercase; letter-spacing:.08em; color:var(--text-2); font-weight:750; margin:.2rem 0 .45rem; }
      .sb-item { font-size:.83rem; color:#c1ccd4; padding:.14rem 0; }
      .sb-tag  { font-size:.68rem; padding:.1rem .42rem; border-radius:6px; background:var(--surface-2); border:1px solid var(--border); color:var(--text-2); }
      hr { margin:.85rem 0; border:none; border-top:1px solid var(--border-soft); }

      /* controls */
      .stButton>button {
        border-radius:9px; font-weight:600; border:1px solid var(--border); transition:all .12s ease;
      }
      .stButton>button:hover { border-color:var(--brand); color:var(--brand); }
      .stButton>button[kind="primary"] {
        background:var(--brand); color:#ffffff; border-color:var(--brand); font-weight:600;
      }
      .stButton>button[kind="primary"]:hover { background:var(--brand-dim); border-color:var(--brand-dim); color:#ffffff; }
      [data-testid="stTextInput"] input, [data-testid="stTextArea"] textarea,
      [data-baseweb="select"] > div {
        border-radius:9px !important;
      }
      .stTabs [data-baseweb="tab-list"] { gap:.35rem; }
      .stTabs [data-baseweb="tab"] { font-weight:600; color:var(--text-2); }
      .stTabs [aria-selected="true"] { color:var(--brand) !important; }
      .stTabs [data-baseweb="tab-highlight"] { background:var(--brand) !important; }

      /* Readability safety net for Streamlit-native text on the dark canvas */
      .stApp, [data-testid="stMarkdownContainer"], [data-testid="stMarkdownContainer"] p,
      .stSelectbox label, .stTextInput label, .stTextArea label, .stMultiSelect label,
      [data-testid="stWidgetLabel"] p { color:var(--text) !important; }
      [data-testid="stCaptionContainer"], [data-testid="stCaptionContainer"] p { color:var(--text-2) !important; }
      .stTextInput input, .stTextArea textarea, [data-baseweb="select"] div { color:var(--text) !important; }
      .stTextInput input::placeholder, .stTextArea textarea::placeholder { color:var(--text-3) !important; }

      /* ---- Brand mark + app-bar meta ---- */
      .brandwrap { display:flex; align-items:center; gap:.9rem; }
      .brandmark {
        width:42px; height:42px; border-radius:10px; display:grid; place-items:center; flex:none;
        background:linear-gradient(140deg, var(--brand), var(--brand-dim)); color:#ffffff;
      }
      .appbar-meta { display:flex; flex-direction:column; align-items:flex-end; gap:.5rem; }
      .metaline { font-size:.73rem; color:var(--text-2); display:flex; gap:1rem; align-items:center; }
      .metaline b { color:var(--text); font-weight:600; font-variant-numeric:tabular-nums; }
      .envbadge {
        font-size:.64rem; font-weight:700; letter-spacing:.09em; padding:.22rem .55rem; border-radius:5px;
        background:var(--surface-2); color:var(--text-2); border:1px solid var(--border); text-transform:uppercase;
      }

      /* ---- Section eyebrow ---- */
      .eyebrow {
        font-size:.76rem; font-weight:750; letter-spacing:.13em; text-transform:uppercase; color:var(--text-2);
        display:flex; align-items:center; gap:.7rem; margin:.4rem 0 .75rem;
      }
      .eyebrow::after { content:""; flex:1; height:1px; background:linear-gradient(90deg,var(--border),transparent); }

      /* ---- Queue composition strip ---- */
      .dist {
        background:var(--surface); border:1px solid var(--border); border-radius:10px;
        padding:.9rem 1.05rem; margin-bottom:1rem;
      }
      .dist-head { display:flex; justify-content:space-between; align-items:baseline; margin-bottom:.6rem; }
      .dist-title { font-size:.82rem; font-weight:700; color:var(--text); }
      .dist-sub { font-size:.72rem; color:var(--text-3); }
      .dist-track { display:flex; height:10px; border-radius:999px; overflow:hidden; background:var(--surface-2); gap:2px; }
      .dist-seg { height:100%; transition:width .3s ease; }
      .dist-legend { display:flex; gap:1.3rem; flex-wrap:wrap; margin-top:.65rem; }
      .dist-item { font-size:.75rem; color:var(--text-2); display:flex; align-items:center; gap:.42rem; }
      .dist-dot { width:9px; height:9px; border-radius:3px; display:inline-block; }
      .dist-item b { color:var(--text); font-weight:700; font-variant-numeric:tabular-nums; }

      /* ---- Card action zone ---- */
      .actzone-label { font-size:.7rem; text-transform:uppercase; letter-spacing:.07em; color:var(--text-2);
        font-weight:650; margin:.35rem 0 -.1rem; }

      /* ---- Status footer ---- */
      .statusbar {
        display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:.7rem;
        margin-top:1.6rem; padding:.75rem 1.15rem; border:1px solid var(--border-soft); border-radius:12px;
        background:rgba(20,26,31,.55); font-size:.72rem; color:var(--text-3);
      }
      .statusbar .grp { display:flex; align-items:center; gap:.5rem; }
      .statusbar b { color:var(--text-2); font-weight:600; }
      .statusbar .sdot { width:7px; height:7px; border-radius:999px; background:var(--green);
        display:inline-block; }

      /* ---- Autonomous dispatcher feed ---- */
      .agentbar {
        display:flex; align-items:center; justify-content:space-between; gap:1rem; flex-wrap:wrap;
        border:1px solid var(--border); border-left:3px solid var(--brand); border-radius:10px;
        padding:.85rem 1.1rem; margin-bottom:1rem; background:var(--surface);
      }
      .agentbar .lead { display:flex; align-items:center; gap:.7rem; }
      .agentbar .glyph { width:30px; height:30px; border-radius:8px; display:grid; place-items:center; flex:none;
        background:var(--brand-soft); color:var(--brand); font-size:1rem; }
      .agentbar .h { font-size:.92rem; font-weight:680; color:#f6f9fc; letter-spacing:-.01em; }
      .agentbar .s { font-size:.75rem; color:var(--text-3); margin-top:1px; }
      .agentbar .live { font-size:.7rem; font-weight:700; letter-spacing:.05em; text-transform:uppercase;
        color:var(--brand); display:inline-flex; align-items:center; gap:.4rem; }
      .agentbar .live .rec { width:8px; height:8px; border-radius:999px; background:var(--brand);
        display:inline-block; animation:pulse 1.3s ease-in-out infinite; }
      @keyframes pulse { 0%,100%{opacity:.35} 50%{opacity:1} }
      .agentbar .metric { text-align:right; }
      .agentbar .metric b { color:#f6f9fc; font-weight:700; font-variant-numeric:tabular-nums; }
      .agentbar .metric span { font-size:.72rem; color:var(--text-3); }

      .feedrow { display:flex; align-items:flex-start; gap:.6rem; padding:.28rem 0; font-size:.85rem;
        color:var(--text-2); line-height:1.5; }
      .feedrow .ti { font-family:ui-monospace,"SF Mono",Menlo,monospace; font-size:.72rem; font-weight:700;
        padding:.12rem .5rem; border-radius:6px; flex:none; margin-top:1px; }
      .feedrow.call .ti  { background:var(--brand-soft); color:var(--brand); border:1px solid rgba(107,124,255,.28); }
      .feedrow.ok .ti    { background:rgba(63,185,80,.12); color:var(--green); border:1px solid rgba(63,185,80,.3); }
      .feedrow.err .ti   { background:var(--safety-soft); color:var(--safety); border:1px solid var(--safety-bd); }
      .feedrow.say       { color:#cbd5dd; font-style:italic; }
      .feedrow b { color:var(--text); font-weight:600; }
    </style>
    """,
    unsafe_allow_html=True,
)


# --------------------------------------------------------------------------- #
# Connectivity gate
# --------------------------------------------------------------------------- #
online = backend_online()
if not online:
    st.markdown(
        """
        <div class="appbar">
          <div><div class="title">🔧 Maintenance Work Order Triage</div>
          <div class="subtitle">Dispatcher console</div></div>
          <div class="pillrow"><span class="pill off"><span class="dot">●</span>Database offline</span></div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.error(f"Cannot reach the database at **{DB_HOST}**.")
    have_env = bool(os.getenv("DATABASE_URL"))
    if not have_env and not SECRET_HAS_DB:
        st.info(
            "**No `DATABASE_URL` found.** On Streamlit Cloud: open **Manage app → "
            "⋮ → Settings → Secrets**, paste your `DATABASE_URL` and "
            "`ANTHROPIC_API_KEY` (see `.streamlit/secrets.toml.example`), click "
            "**Save**, then **Reboot** the app."
        )
    elif SECRET_HAS_DB and not have_env:
        st.warning(
            "`DATABASE_URL` is in Secrets but wasn't loaded into this session — "
            "**Reboot** the app (Manage app → ⋮ → Reboot) so it starts fresh with the secret."
        )
    else:
        st.warning(
            "`DATABASE_URL` is set but the database isn't reachable. Double-check the "
            "host, port (`4000` for TiDB), user, and password, and that the database exists."
        )
    st.stop()

meta = get_meta()
CREWS = meta["crews"]
SAFETY_KEYWORDS = meta.get("safety_keywords", [])


# --------------------------------------------------------------------------- #
# Header
# --------------------------------------------------------------------------- #
# Map a subsystem's reported status to a pill visual state.
_PILL_CLASS = {"up": "on", "configured": "on", "fallback": "warn", "degraded": "warn", "down": "off"}


def status_pill(label, comp):
    """Render a header pill coloured by a real /health/full component result."""
    comp = comp or {}
    status = comp.get("status", "down")
    cls = _PILL_CLASS.get(status, "off")
    detail = comp.get("detail", "")
    tip = f"{label} — {status}" + (f": {detail}" if detail else "")
    return f'<span class="pill {cls}" title="{tip}"><span class="dot">●</span>{label}</span>'


health = get_health()
comps = (health or {}).get("components", {})
# Backend is reachable (the connectivity gate already passed), so mark it up.
comps.setdefault("backend", {"status": "up", "detail": "FastAPI"})

ENV_LABEL = "Local" if any(h in _DB_URL for h in ("localhost", "127.0.0.1")) else "Cloud"
_LOGO_SVG = (
    '<svg width="24" height="24" viewBox="0 0 24 24" fill="none" '
    'stroke="currentColor" stroke-width="2.1" stroke-linecap="round" stroke-linejoin="round">'
    '<path d="M14.7 6.3a4 4 0 0 0-5.4 5.3L3 18l3 3 6.4-6.3a4 4 0 0 0 5.3-5.4l-2.6 2.6-2.1-.5-.5-2.1z"/></svg>'
)

st.markdown(
    f"""
    <div class="appbar">
      <div class="brandwrap">
        <div class="brandmark">{_LOGO_SVG}</div>
        <div>
          <div class="title">Maintenance Triage Console</div>
          <div class="subtitle">Autonomous agent · Claude reads the queue, triages &amp; dispatches each order to a crew itself</div>
        </div>
      </div>
      <div class="appbar-meta">
        <div class="pillrow">
          {status_pill("Backend API", comps.get("backend"))}
          {status_pill("Database", comps.get("database"))}
          {status_pill("Queue MCP", comps.get("queue_mcp"))}
          {status_pill("Assignment MCP", comps.get("assignment_mcp"))}
          {status_pill("Claude Agent", comps.get("claude"))}
        </div>
        <div class="metaline">
          <span class="envbadge">● {ENV_LABEL}</span>
          <span>Model <b>{os.getenv("CLAUDE_MODEL", "claude-opus-4-8")}</b></span>
          <span>Synced <b>{datetime.now().strftime("%H:%M:%S")}</b></span>
        </div>
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)


# --------------------------------------------------------------------------- #
# KPI tiles
# --------------------------------------------------------------------------- #
stats = api_get("/stats")


def kpi(col, label, value, accent, foot=""):
    col.markdown(
        f"""
        <div class="kpi" style="--accent:{accent}">
          <div class="label">{label}</div>
          <div class="value">{value}</div>
          <div class="foot">{foot}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

st.markdown('<div class="eyebrow">Operations overview</div>', unsafe_allow_html=True)
k = st.columns(5)
kpi(k[0], "Open Orders", stats["open_orders"], BRAND, f'{stats["pending_triage"]} awaiting triage')
kpi(k[1], "Safety Cases", stats["safety_cases"], "#f87171", "force-escalated hazards")
kpi(k[2], "Awaiting Review", stats["awaiting_review"], "#fbbf24", "need a dispatcher decision")
kpi(k[3], "Assigned", stats["assigned"], "#4ade80", "committed to a crew")
kpi(k[4], "Rejected", stats["rejected"], "#7c8895", "proposals declined")

st.write("")


# --------------------------------------------------------------------------- #
# Sidebar
# --------------------------------------------------------------------------- #
with st.sidebar:
    st.markdown("### 🛠️ Triage Console")
    # Remember the dispatcher name across reruns (persists in session state).
    st.session_state.setdefault("approver", "dispatcher")
    approver = st.text_input("Dispatcher on record", key="approver",
                             help="Recorded as the approver on assignments the agent commits.")

    st.markdown(
        '<div class="sb-item" style="color:var(--text-2);line-height:1.5">'
        '🤖 <b>Autonomous mode.</b> Claude drives the tools itself — it reads the queue, '
        'triages, and dispatches each order to a crew with no button in the loop. New work '
        'is picked up automatically.</div>',
        unsafe_allow_html=True,
    )

    with st.expander("➕ File a new work order"):
        with st.form("new_wo", clear_on_submit=True):
            t = st.text_input("Title")
            d = st.text_area("Description")
            loc = st.text_input("Machine / location")
            rep = st.text_input("Reported by")
            if st.form_submit_button("File work order", width="stretch") and t and d:
                with st.spinner("Filing and auto-triaging with Claude…"):
                    wo = api_post("/work-orders", json={
                        "title": t, "description": d,
                        "location": loc or None, "reported_by": rep or None,
                    })
                if wo.get("status") == "triaged":
                    st.success("Filed and triaged — the dispatcher will pick it up.")
                else:
                    st.warning("Filed, but auto-triage didn't complete — the dispatcher will still handle it.")
                st.cache_data.clear()
                st.rerun()

    st.markdown("<hr>", unsafe_allow_html=True)

    st.markdown('<div class="sb-h">🚨 Safety rules (auto-escalate)</div>', unsafe_allow_html=True)
    st.caption("Any work order mentioning these is force-classified **safety-critical**, regardless of the model.")
    with st.expander(f"{len(SAFETY_KEYWORDS)} keyword triggers"):
        st.markdown(
            " ".join(f'<span class="kw">{kw}</span>' for kw in SAFETY_KEYWORDS),
            unsafe_allow_html=True,
        )

    st.markdown("<hr>", unsafe_allow_html=True)

    st.markdown('<div class="sb-h">👷 Crew directory</div>', unsafe_allow_html=True)
    for c in CREWS:
        st.markdown(f'<div class="sb-item">• {c}</div>', unsafe_allow_html=True)

    st.markdown("<hr>", unsafe_allow_html=True)

    st.markdown('<div class="sb-h">📜 Recent activity</div>', unsafe_allow_html=True)
    recent_assigns = api_get("/assignments")[:5]
    rejected = [w for w in api_get("/work-orders", status="rejected")]
    rejected.sort(key=lambda w: w.get("rejected_at") or "", reverse=True)
    if not recent_assigns and not rejected:
        st.caption("No approvals or rejections yet.")
    for a in recent_assigns:
        st.markdown(
            f'<div class="sb-item">✅ <b>WO-{a["work_order_id"]}</b> → {a["crew"]} '
            f'<span class="sb-tag">{ago(a["approved_at"])}</span></div>',
            unsafe_allow_html=True,
        )
    for w in rejected[:5]:
        st.markdown(
            f'<div class="sb-item">⛔ <b>WO-{w["id"]}</b> rejected '
            f'<span class="sb-tag">{ago(w.get("rejected_at"))}</span></div>',
            unsafe_allow_html=True,
        )


# --------------------------------------------------------------------------- #
# Autonomous dispatcher — Claude drives the tools; the feed streams live
# --------------------------------------------------------------------------- #
_TOOL_LABEL = {
    "read_queue": "READ", "get_crew_load": "LOAD", "submit_triage": "TRIAGE",
    "assign_order": "ASSIGN", "reject_order": "REJECT",
}


def _fmt_args(name, inp):
    inp = inp or {}
    if name == "read_queue":
        return f' <b>status={inp.get("status")}</b>'
    if "work_order_id" in inp:
        extra = ""
        if inp.get("crew"):
            extra = f' → <b>{inp["crew"]}</b>'
        elif inp.get("urgency"):
            extra = f' · <b>{inp["urgency"]}</b>'
        return f' <b>WO-{inp["work_order_id"]}</b>{extra}'
    return ""


def _feed_html(ev):
    """Render one agent event as an HTML feed row (or None to skip)."""
    t = ev.get("type")
    if t == "text":
        return f'<div class="feedrow say">💬 {ev["text"]}</div>'
    if t == "tool_call":
        name = ev["name"]
        lbl = _TOOL_LABEL.get(name, name.upper())
        return (f'<div class="feedrow call"><span class="ti">{lbl}</span>'
                f'<span>calls <b>{name}</b>{_fmt_args(name, ev.get("input"))}</span></div>')
    if t == "tool_result":
        ok = ev.get("ok", True)
        cls, icon = ("ok", "✓") if ok else ("err", "✕")
        return (f'<div class="feedrow {cls}"><span class="ti">{icon}</span>'
                f'<span>{ev.get("summary", "")}</span></div>')
    if t == "error":
        return f'<div class="feedrow err"><span class="ti">✕</span><span>{ev.get("error", "")}</span></div>'
    return None


def run_dispatch_live(actor):
    """Consume the dispatcher stream, rendering each event into a live status feed."""
    log = []
    with st.status("🤖 Autonomous dispatcher — working the queue…", expanded=True) as status:
        for ev in api.dispatch_stream(actor=actor, limit=25):
            t = ev.get("type")
            if t == "start":
                continue
            if t == "busy":
                status.update(label="Another dispatch run is already in progress…", state="error")
                log.append(ev)
                break
            if t == "done":
                c = ev["counts"]
                status.update(
                    label=f"Dispatch complete — {c['assigned']} assigned · "
                          f"{c['triaged']} triaged · {c['rejected']} rejected",
                    state="complete",
                )
                log.append(ev)
                continue
            html = _feed_html(ev)
            if html:
                st.markdown(html, unsafe_allow_html=True)
            if t == "error":
                status.update(label="Dispatcher hit an error", state="error")
            log.append(ev)
    return log


def _log_counts(log):
    for ev in reversed(log or []):
        if ev.get("type") in ("done", "error") and ev.get("counts"):
            return ev["counts"]
    return None


def render_dispatch_idle(have_key, work_to_do):
    """Static dispatcher bar shown when the agent isn't actively running."""
    log = st.session_state.get("dispatch_log")
    counts = _log_counts(log)
    if not have_key:
        head = "Autonomous dispatch disabled"
        sub = "No ANTHROPIC_API_KEY set — add it in Secrets to let Claude drive the queue."
    elif work_to_do > 0:
        head = "Orders still open"
        sub = (f"{work_to_do} order(s) outstanding. Refresh to let the dispatcher take "
               "another pass, or act on them manually below.")
    else:
        head = "Queue clear — dispatcher idle"
        sub = "Claude has dispatched everything. New work orders are picked up automatically."
    metric = ""
    if counts:
        metric = (
            f'<div class="metric"><b>{counts["assigned"]}</b> <span>assigned</span>'
            f'&nbsp;&nbsp;<b>{counts["triaged"]}</b> <span>triaged</span>'
            f'&nbsp;&nbsp;<b>{counts["rejected"]}</b> <span>rejected</span></div>'
        )
    st.markdown(
        f'<div class="agentbar"><div class="lead"><div class="glyph">🤖</div>'
        f'<div><div class="h">{head}</div><div class="s">{sub}</div></div></div>{metric}</div>',
        unsafe_allow_html=True,
    )
    if log:
        with st.expander("View last dispatch run — Claude's tool activity"):
            for ev in log:
                html = _feed_html(ev)
                if html:
                    st.markdown(html, unsafe_allow_html=True)


st.markdown('<div class="eyebrow">Autonomous dispatcher</div>', unsafe_allow_html=True)

# Auto-run the agent whenever there's NEW work (more outstanding than we last
# observed). Tracking the last-seen count self-throttles the Streamlit rerun
# loop: a completed run drops the count to ~0, so it won't re-fire until fresh
# orders arrive. `approver` (from the sidebar) is recorded as the agent's actor.
_have_key = bool(os.getenv("ANTHROPIC_API_KEY"))
_work_to_do = stats["pending_triage"] + stats["awaiting_review"]
_prev_seen = st.session_state.get("dispatch_seen", 0)
_should_run = _have_key and _work_to_do > 0 and _work_to_do > _prev_seen
st.session_state["dispatch_seen"] = _work_to_do

if _should_run:
    st.markdown(
        f'<div class="agentbar"><div class="lead"><div class="glyph">🤖</div>'
        f'<div><div class="h">Claude is dispatching the queue</div>'
        f'<div class="s">{_work_to_do} order(s) outstanding · driving read → triage → assign</div>'
        f'</div></div><span class="live"><span class="rec"></span>Live</span></div>',
        unsafe_allow_html=True,
    )
    st.session_state["dispatch_log"] = run_dispatch_live(approver)
    st.cache_data.clear()
    st.rerun()
else:
    render_dispatch_idle(_have_key, _work_to_do)


# --------------------------------------------------------------------------- #
# Filter bar
# --------------------------------------------------------------------------- #
st.markdown('<div class="eyebrow">Triage workspace</div>', unsafe_allow_html=True)
f = st.columns([3, 2.4, 2.4, 1.6, 1.1])
search = f[0].text_input("Search", placeholder="title, description, machine…", label_visibility="collapsed")
urg_filter = f[1].multiselect(
    "Urgency", list(URGENCY.keys()),
    format_func=lambda x: u(x)["label"], placeholder="Urgency", label_visibility="collapsed",
)
crew_filter = f[2].multiselect("Crew", CREWS, placeholder="Crew", label_visibility="collapsed")
safety_only = f[3].toggle("Safety only")
if f[4].button("↻ Refresh", width="stretch"):
    st.cache_data.clear()
    st.rerun()


# --------------------------------------------------------------------------- #
# Queue composition strip — at-a-glance urgency mix across the current queue
# --------------------------------------------------------------------------- #
def render_composition(proposals):
    total = len(proposals)
    if not total:
        return
    order = ["safety-critical", "production-stopping", "routine"]
    counts = {k: 0 for k in order}
    other = 0
    for p in proposals:
        key = p["proposed_urgency"]
        if key in counts:
            counts[key] += 1
        else:
            other += 1

    segs, legends = "", ""
    for key in order:
        n = counts[key]
        if n:
            pct = n / total * 100
            c = u(key)["color"]
            segs += f'<div class="dist-seg" style="width:{pct:.2f}%;background:{c}"></div>'
        c = u(key)["color"]
        legends += (
            f'<span class="dist-item"><span class="dist-dot" style="background:{c}"></span>'
            f'{u(key)["label"]} <b>{counts[key]}</b></span>'
        )
    if other:
        c = DEFAULT_URGENCY["color"]
        segs += f'<div class="dist-seg" style="width:{other/total*100:.2f}%;background:{c}"></div>'
        legends += (
            f'<span class="dist-item"><span class="dist-dot" style="background:{c}"></span>'
            f'Unclassified <b>{other}</b></span>'
        )

    st.markdown(
        f'<div class="dist"><div class="dist-head">'
        f'<span class="dist-title">Queue composition</span>'
        f'<span class="dist-sub">{total} proposal(s) awaiting review</span></div>'
        f'<div class="dist-track">{segs}</div>'
        f'<div class="dist-legend">{legends}</div></div>',
        unsafe_allow_html=True,
    )


# --------------------------------------------------------------------------- #
# Card renderer
# --------------------------------------------------------------------------- #
def render_card(p):
    wo_id = p["work_order_id"]
    meta_u = u(p["proposed_urgency"])
    accent = meta_u["color"]
    conf = p.get("confidence")
    conf_pct = int(round(conf * 100)) if isinstance(conf, (int, float)) else None

    safety_badge = '<span class="badge-safety">⚠ SAFETY-CRITICAL</span>' if p["is_safety_critical"] else ""
    chip = f'<span class="chip" style="background:{accent}">{meta_u["dot"]} {meta_u["label"]}</span>'

    with st.container(border=False):
        st.markdown(f'<div class="wocard" style="--accent:{accent}">', unsafe_allow_html=True)

        head = st.columns([6.5, 3.5])
        with head[0]:
            st.markdown(
                f'<div class="id">WO-{wo_id}</div>'
                f'<div class="ttl">{p["title"]} &nbsp;{safety_badge}</div>'
                f'<div class="meta">🏭 <b>{p["location"] or "unspecified"}</b> · '
                f'reported by <b>{p["reported_by"] or "n/a"}</b> · '
                f'submitted {humanize(p.get("created_at"))}</div>'
                f'<div class="desc">{p["description"]}</div>',
                unsafe_allow_html=True,
            )
        with head[1]:
            src = p.get("source", "claude")
            src_txt = {
                "claude": "Claude (single call)",
                "agent": "Claude agent (tool-use)",
                "heuristic": "keyword heuristic",
            }.get(src, src)
            conf_block = ""
            if conf_pct is not None:
                conf_block = (
                    f'<div class="confwrap"><div class="conflabel">'
                    f'<span>Confidence</span><span style="color:{accent};font-weight:700">{conf_pct}%</span></div>'
                    f'<div class="conftrack"><div class="conffill" '
                    f'style="width:{conf_pct}%;background:{accent}"></div></div></div>'
                )
            st.markdown(
                f'<div style="text-align:right">{chip}</div>'
                f'<div style="margin-top:.5rem"><span class="kv">Suggested crew</span><br>'
                f'<span class="kvval">{p["proposed_crew"]}</span></div>'
                f'{conf_block}'
                f'<div style="margin-top:.4rem"><span class="kv">Source</span> '
                f'<span class="kvval" style="font-size:.8rem">{src_txt}</span></div>',
                unsafe_allow_html=True,
            )

        if p.get("reasoning"):
            st.markdown(f'<div class="reason">💭 {p["reasoning"]}</div>', unsafe_allow_html=True)
        if p.get("safety_keywords"):
            st.markdown(
                '🚩 ' + " ".join(f'<span class="kw">{kw}</span>' for kw in p["safety_keywords"]),
                unsafe_allow_html=True,
            )

        # ---- Actions ----
        st.markdown('<div class="actzone-label">Dispatcher action</div>', unsafe_allow_html=True)
        c = st.columns([3.2, 1.6, 1.6, 1.6])
        current = p["proposed_crew"]
        idx = CREWS.index(current) if current in CREWS else 0
        new_crew = c[0].selectbox("Crew override", CREWS, index=idx, key=f"crew_{wo_id}",
                                  label_visibility="collapsed")
        changed = new_crew != current
        if c[1].button("↺ Change crew", key=f"chg_{wo_id}", width="stretch", disabled=not changed):
            api_post(f"/proposals/{wo_id}/change-crew", json={"crew": new_crew})
            st.cache_data.clear()
            st.rerun()
        if c[2].button("✅ Approve", key=f"apr_{wo_id}", width="stretch", type="primary"):
            api_post("/assignments/approve",
                     json={"approved_by": approver, "crew": new_crew}, work_order_id=wo_id)
            st.toast(f"WO-{wo_id} assigned to {new_crew}", icon="✅")
            st.cache_data.clear()
            st.rerun()
        if c[3].button("⛔ Reject", key=f"rej_{wo_id}", width="stretch"):
            st.session_state[f"rejecting_{wo_id}"] = True

        if st.session_state.get(f"rejecting_{wo_id}"):
            with st.form(f"rejform_{wo_id}", clear_on_submit=True):
                reason = st.text_input("Reason for rejection (optional)", key=f"rsn_{wo_id}")
                rc = st.columns([1, 1, 5])
                if rc[0].form_submit_button("Confirm reject", type="primary"):
                    api_post(f"/proposals/{wo_id}/reject",
                             json={"rejected_by": approver, "reason": reason or None})
                    st.session_state[f"rejecting_{wo_id}"] = False
                    st.toast(f"WO-{wo_id} rejected", icon="⛔")
                    st.cache_data.clear()
                    st.rerun()
                if rc[1].form_submit_button("Cancel"):
                    st.session_state[f"rejecting_{wo_id}"] = False
                    st.rerun()

        st.markdown("</div>", unsafe_allow_html=True)


def matches(p):
    if safety_only and not p["is_safety_critical"]:
        return False
    if urg_filter and p["proposed_urgency"] not in urg_filter:
        return False
    if crew_filter and p["proposed_crew"] not in crew_filter:
        return False
    if search:
        blob = f'{p["title"]} {p["description"]} {p.get("location") or ""} {p.get("reported_by") or ""}'.lower()
        if search.lower() not in blob:
            return False
    return True


# --------------------------------------------------------------------------- #
# Main tabs
# --------------------------------------------------------------------------- #
queue_tab, history_tab = st.tabs(["📋  Triage Queue", "🗂️  Assignment History"])

with queue_tab:
    proposals = api_get("/proposals")
    shown = [p for p in proposals if matches(p)]
    n_crit = sum(1 for p in shown if p["is_safety_critical"])

    top = st.columns([6, 2])
    top[0].caption(
        f"Showing **{len(shown)}** of {len(proposals)} awaiting review"
        + (f" · **{n_crit}** safety-critical" if n_crit else "")
    )

    if not proposals:
        st.info("Queue is clear — Claude has dispatched everything. File a new work order and the autonomous dispatcher picks it up automatically.")
    elif not shown:
        st.warning("No proposals match the current filters.")
    else:
        render_composition(shown)
        if n_crit:
            st.markdown(
                f'<div style="background:rgba(248,113,113,.12);border:1px solid rgba(248,113,113,.38);'
                f'border-radius:11px;padding:.65rem .95rem;margin-bottom:.85rem;color:#f87171;'
                f'font-weight:650;font-size:.9rem">'
                f'⚠️ {n_crit} safety-critical order(s) pinned to the top of the queue — review first.</div>',
                unsafe_allow_html=True,
            )
        for p in shown:
            render_card(p)

with history_tab:
    assignments = api_get("/assignments")
    if not assignments:
        st.info("No assignments yet. Approved proposals appear here.")
    else:
        st.caption(f"{len(assignments)} assignment(s) committed — most recent first.")
        st.dataframe(
            [
                {
                    "WO": f'WO-{a["work_order_id"]}',
                    "Crew": a["crew"],
                    "Urgency": u(a["urgency"])["label"],
                    "Safety": "⚠️" if a["is_safety_critical"] else "",
                    "Approved by": a["approved_by"],
                    "Approved": humanize(a["approved_at"]),
                }
                for a in assignments
            ],
            width="stretch",
            hide_index=True,
        )


# --------------------------------------------------------------------------- #
# Status footer — reflects the live /health/full result
# --------------------------------------------------------------------------- #
_overall = (health or {}).get("status")
if _overall == "ok":
    _status_txt, _dot_color = "All systems operational", "var(--green)"
elif _overall == "degraded":
    _down = [k.replace("_", " ") for k, c in comps.items() if c.get("status") in ("down", "degraded")]
    _status_txt = "Degraded — " + (", ".join(_down) if _down else "check components")
    _dot_color = "var(--amber)"
else:
    _status_txt, _dot_color = "Health status unavailable", "var(--text-3)"

st.markdown(
    f"""
    <div class="statusbar">
      <div class="grp"><span class="sdot" style="background:{_dot_color}"></span>
        <b>{_status_txt}</b> · in-process backend · {DB_HOST}</div>
      <div class="grp">
        Autonomous dispatch · Claude drives read → triage → assign
        &nbsp;·&nbsp; Maintenance Triage Console <b>v1.0</b>
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)
