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
from datetime import datetime, timezone

import requests
import streamlit as st
from dotenv import load_dotenv

load_dotenv()


def _resolve_backend_url():
    """Where the FastAPI backend lives.

    Priority: BACKEND_URL env var (local dev) → Streamlit secret (Community
    Cloud, where the value points at the Render backend) → localhost fallback.
    """
    env = os.getenv("BACKEND_URL")
    if env:
        return env.rstrip("/")
    try:
        return str(st.secrets["BACKEND_URL"]).rstrip("/")
    except Exception:
        return "http://localhost:8000"


BACKEND_URL = _resolve_backend_url()

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
    "safety-critical": {"label": "Safety Critical", "color": "#f87171", "dot": "🔴", "rank": 0},
    "production-stopping": {"label": "Production Stopping", "color": "#fbbf24", "dot": "🟠", "rank": 1},
    "routine": {"label": "Routine", "color": "#4ade80", "dot": "🟢", "rank": 2},
}
DEFAULT_URGENCY = {"label": "Unclassified", "color": "#7c8895", "dot": "⚪", "rank": 3}

# Brand — Teal / Graphite enterprise palette
BRAND = "#2dd4bf"


def u(urgency):
    return URGENCY.get(urgency, DEFAULT_URGENCY)


# --------------------------------------------------------------------------- #
# API helpers
# --------------------------------------------------------------------------- #
def api_get(path, **params):
    r = requests.get(f"{BACKEND_URL}{path}", params=params, timeout=120)
    r.raise_for_status()
    return r.json()


def api_post(path, json=None, **params):
    r = requests.post(f"{BACKEND_URL}{path}", json=json, params=params, timeout=600)
    r.raise_for_status()
    return r.json()


def backend_online():
    try:
        api_get("/health")
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
        --bg:#0b0f12; --surface:#141a1f; --surface-2:#1b232a; --surface-3:#212b33;
        --border:#26313a; --border-soft:#1e262d;
        --text:#e6edf2; --text-2:#93a1ac; --text-3:#64727d;
        --brand:#2dd4bf; --brand-dim:#14b8a6; --brand-soft:rgba(45,212,191,.12);
        --safety:#f87171; --safety-soft:rgba(248,113,113,.12); --safety-bd:rgba(248,113,113,.38);
        --amber:#fbbf24; --amber-soft:rgba(251,191,36,.12);
        --green:#4ade80;
        --shadow:0 1px 2px rgba(0,0,0,.4), 0 8px 24px -12px rgba(0,0,0,.6);
        --font:"Inter",-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
      }
      html, body, [class*="css"] { font-family:var(--font); }
      .stApp { background:
          radial-gradient(1200px 500px at 85% -8%, rgba(45,212,191,.06), transparent 60%),
          var(--bg); }
      .block-container { padding-top: 2rem; padding-bottom: 3rem; max-width: 1420px; }
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
        padding:1.05rem 1.4rem; margin-bottom:1.3rem; border-radius:16px;
        background:linear-gradient(115deg, rgba(45,212,191,.14) 0%, rgba(20,26,31,.4) 42%), var(--surface);
        border:1px solid var(--border); box-shadow:var(--shadow); position:relative; overflow:hidden;
      }
      .appbar::after {
        content:""; position:absolute; left:0; right:0; bottom:0; height:2px;
        background:linear-gradient(90deg, var(--brand), transparent 70%);
      }
      .appbar .title { font-size:1.42rem; font-weight:760; letter-spacing:-.015em; color:#f4f8fb;
        display:flex; align-items:center; gap:.5rem; }
      .appbar .subtitle { font-size:.83rem; color:var(--text-2); margin-top:3px; }
      .pillrow { display:flex; gap:.45rem; flex-wrap:wrap; justify-content:flex-end; }
      .pill {
        font-size:.71rem; font-weight:600; padding:.3rem .65rem; border-radius:999px;
        border:1px solid var(--border); color:var(--text-2); background:rgba(11,15,18,.6);
        white-space:nowrap; display:inline-flex; align-items:center; gap:.35rem;
      }
      .pill.on   { border-color:rgba(45,212,191,.4); color:var(--brand); background:var(--brand-soft); }
      .pill.warn { border-color:rgba(251,191,36,.4); color:var(--amber); background:var(--amber-soft); }
      .pill.off  { border-color:var(--safety-bd); color:var(--safety); background:var(--safety-soft); }
      .pill .dot { font-size:.6rem; line-height:1; }
      .pill.warn .dot, .pill.off .dot { animation:pulse 1.6s ease-in-out infinite; }
      @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:.35} }

      /* ---- KPI tiles ---- */
      .kpi {
        border:1px solid var(--border); border-radius:15px; padding:1.05rem 1.15rem; background:var(--surface);
        position:relative; overflow:hidden; height:100%; box-shadow:var(--shadow);
        transition:transform .14s ease, border-color .14s ease;
      }
      .kpi:hover { transform:translateY(-2px); border-color:var(--surface-3); }
      .kpi::before {
        content:""; position:absolute; left:0; top:0; bottom:0; width:3px;
        background:var(--accent,var(--brand)); box-shadow:0 0 14px 0 var(--accent,var(--brand));
      }
      .kpi .label { font-size:.72rem; text-transform:uppercase; letter-spacing:.07em; color:var(--text-2); font-weight:650; }
      .kpi .value { font-size:2.15rem; font-weight:780; color:#f4f8fb; line-height:1.1; margin-top:.3rem;
        font-variant-numeric:tabular-nums; }
      .kpi .foot  { font-size:.73rem; color:var(--text-3); margin-top:.2rem; }

      /* ---- Work order card ---- */
      .wocard {
        border:1px solid var(--border); border-left:4px solid var(--accent,var(--brand));
        border-radius:14px; padding:1.1rem 1.25rem .45rem; background:var(--surface);
        margin-bottom:.25rem; box-shadow:var(--shadow); transition:border-color .14s ease;
      }
      .wocard:hover { border-color:var(--surface-3); border-left-color:var(--accent,var(--brand)); }
      .wocard .id     { font-family:ui-monospace,"SF Mono",Menlo,monospace; color:var(--brand); font-size:.76rem; font-weight:650; letter-spacing:.02em; }
      .wocard .ttl    { font-size:1.1rem; font-weight:720; color:#f4f8fb; margin:.15rem 0 .4rem; letter-spacing:-.01em; }
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

      .kv { font-size:.7rem; text-transform:uppercase; letter-spacing:.06em; color:var(--text-3); font-weight:650; }
      .kvval { font-size:.92rem; color:var(--text); font-weight:650; }

      /* sidebar */
      section[data-testid="stSidebar"] { background:#0e141a; border-right:1px solid var(--border-soft); }
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
        background:var(--brand); color:#06201d; border-color:var(--brand); font-weight:700;
      }
      .stButton>button[kind="primary"]:hover { background:#5fe3d1; border-color:#5fe3d1; color:#06201d; }
      [data-testid="stTextInput"] input, [data-testid="stTextArea"] textarea,
      [data-baseweb="select"] > div {
        border-radius:9px !important;
      }
      .stTabs [data-baseweb="tab-list"] { gap:.35rem; }
      .stTabs [data-baseweb="tab"] { font-weight:600; }
      .stTabs [aria-selected="true"] { color:var(--brand) !important; }
      .stTabs [data-baseweb="tab-highlight"] { background:var(--brand) !important; }

      /* ---- Brand mark + app-bar meta ---- */
      .brandwrap { display:flex; align-items:center; gap:.9rem; }
      .brandmark {
        width:44px; height:44px; border-radius:12px; display:grid; place-items:center; flex:none;
        background:linear-gradient(140deg, var(--brand), var(--brand-dim));
        box-shadow:0 6px 16px -6px rgba(45,212,191,.6); color:#06201d;
      }
      .appbar-meta { display:flex; flex-direction:column; align-items:flex-end; gap:.5rem; }
      .metaline { font-size:.71rem; color:var(--text-3); display:flex; gap:1rem; align-items:center; }
      .metaline b { color:var(--text-2); font-weight:600; font-variant-numeric:tabular-nums; }
      .envbadge {
        font-size:.64rem; font-weight:750; letter-spacing:.09em; padding:.22rem .55rem; border-radius:6px;
        background:var(--brand-soft); color:var(--brand); border:1px solid rgba(45,212,191,.4); text-transform:uppercase;
      }

      /* ---- Section eyebrow ---- */
      .eyebrow {
        font-size:.72rem; font-weight:750; letter-spacing:.14em; text-transform:uppercase; color:var(--text-3);
        display:flex; align-items:center; gap:.7rem; margin:.4rem 0 .75rem;
      }
      .eyebrow::after { content:""; flex:1; height:1px; background:linear-gradient(90deg,var(--border),transparent); }

      /* ---- Queue composition strip ---- */
      .dist {
        background:var(--surface); border:1px solid var(--border); border-radius:13px;
        padding:.9rem 1.05rem; box-shadow:var(--shadow); margin-bottom:1rem;
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
      .actzone-label { font-size:.68rem; text-transform:uppercase; letter-spacing:.07em; color:var(--text-3);
        font-weight:650; margin:.35rem 0 -.1rem; }

      /* ---- Status footer ---- */
      .statusbar {
        display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:.7rem;
        margin-top:1.6rem; padding:.75rem 1.15rem; border:1px solid var(--border-soft); border-radius:12px;
        background:rgba(20,26,31,.55); font-size:.72rem; color:var(--text-3);
      }
      .statusbar .grp { display:flex; align-items:center; gap:.5rem; }
      .statusbar b { color:var(--text-2); font-weight:600; }
      .statusbar .sdot { width:7px; height:7px; border-radius:999px; background:var(--brand);
        box-shadow:0 0 8px var(--brand); display:inline-block; }
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
          <div class="pillrow"><span class="pill off"><span class="dot">●</span>Backend offline</span></div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.error(
        f"Cannot reach the backend at **{BACKEND_URL}**.\n\n"
        "Start it from the project root:\n\n"
        "```bash\nuvicorn backend.main:app --reload\n```"
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

ENV_LABEL = "Local" if any(h in BACKEND_URL for h in ("localhost", "127.0.0.1")) else "Remote"
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
          <div class="subtitle">Claude proposes urgency &amp; crew · a dispatcher approves before anything is assigned</div>
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
    approver = st.text_input("Dispatcher", value="dispatcher", help="Recorded on every approval / rejection.")

    if st.button("🤖 Run triage on pending queue", width="stretch", type="primary"):
        with st.spinner("Claude is triaging the pending queue…"):
            summary = api_post("/triage")
        st.success(f"Triaged {summary['triaged']} of {summary['queue_size']}.")
        st.cache_data.clear()
        st.rerun()

    with st.expander("➕ File a new work order"):
        with st.form("new_wo", clear_on_submit=True):
            t = st.text_input("Title")
            d = st.text_area("Description")
            loc = st.text_input("Machine / location")
            rep = st.text_input("Reported by")
            if st.form_submit_button("File work order", width="stretch") and t and d:
                api_post("/work-orders", json={
                    "title": t, "description": d,
                    "location": loc or None, "reported_by": rep or None,
                })
                st.success("Filed. Run triage to get a proposal.")
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
            src_txt = "Claude agent" if src == "claude" else "keyword heuristic"
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
        st.info("Queue is clear. File work orders and click **Run triage** to have Claude propose assignments.")
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
    _status_txt, _dot_color = "All systems operational", "var(--brand)"
elif _overall == "degraded":
    _down = [k.replace("_", " ") for k, c in comps.items() if c.get("status") in ("down", "degraded")]
    _status_txt = "Degraded — " + (", ".join(_down) if _down else "check components")
    _dot_color = "var(--amber)"
else:
    _status_txt, _dot_color = "Health status unavailable", "var(--text-3)"

st.markdown(
    f"""
    <div class="statusbar">
      <div class="grp"><span class="sdot" style="background:{_dot_color};box-shadow:0 0 8px {_dot_color}"></span>
        <b>{_status_txt}</b> · backend {BACKEND_URL}</div>
      <div class="grp">
        Human-in-the-loop dispatch · no assignment without approval
        &nbsp;·&nbsp; Maintenance Triage Console <b>v1.0</b>
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)
