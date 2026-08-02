# Maintenance Triage Agent — instructions

**Use the `triage-agent` subagent** (`.claude/agents/triage-agent.md`) whenever
asked to triage, clear, or work the maintenance queue — it reads pending work
orders via the `work-order-queue` MCP server and proposes urgency + crew for
each one. It never assigns work: assignment goes through `write_assignment` on
the separate `assignment-writer` MCP server, reached only via human approval,
and the subagent is deliberately never given that tool.

## Architecture

- `backend/services/agent.py` — the API-level triage brain (`propose_triage`
  for one order, `agentic_triage` for the tool-use queue loop). The
  `triage-agent` subagent mirrors `agentic_triage`'s behavior for interactive
  Claude Code use.
- `backend/services/safety_rules.py` — deterministic safety-critical escalation
  layered on top of whatever urgency the model/subagent proposes. Never bypass
  this: any order mentioning injury risk is escalated regardless of the
  model's own urgency call.
- `mcp_servers/queue_server.py` (`read_queue`) / `mcp_servers/assignment_server.py`
  (`write_assignment`) — the two MCP servers declared in `.mcp.json`.

## Development

- Run tests with `pytest`.
- If `ANTHROPIC_API_KEY` is unset, `agent.py` falls back to a keyword
  heuristic so the app still runs end-to-end for demos — don't treat that as
  a bug when testing without a key.
