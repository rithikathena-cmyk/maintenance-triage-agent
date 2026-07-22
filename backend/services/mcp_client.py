"""Thin helper for calling a stdio MCP server tool.

The backend acts as an MCP *client*: it spawns a server script over stdio,
initializes a session, calls one tool, and returns the parsed JSON result.
Spawning per call keeps things simple and stateless for this demo.

``run_tool`` is a synchronous wrapper that runs the async MCP session inside a
dedicated thread with its own event loop. On Windows that loop is a Proactor
loop (required for asyncio subprocesses), which keeps this working regardless
of whichever loop the web server is running on.
"""
import asyncio
import json
import os
import sys
import threading

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

# mcp_servers/ lives at the project root, one level above backend/.
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_MCP_DIR = os.path.join(_PROJECT_ROOT, "mcp_servers")

QUEUE_SERVER = os.path.join(_MCP_DIR, "queue_server.py")
ASSIGNMENT_SERVER = os.path.join(_MCP_DIR, "assignment_server.py")


def _server_params(server_script: str) -> StdioServerParameters:
    return StdioServerParameters(
        command=sys.executable,
        args=[server_script],
        cwd=_PROJECT_ROOT,
        env=os.environ.copy(),
    )


async def call_tool(server_script: str, tool_name: str, arguments: dict):
    """Spawn ``server_script`` over stdio, call ``tool_name``, return parsed JSON."""
    async with stdio_client(_server_params(server_script)) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(tool_name, arguments)

    text = next(
        (b.text for b in result.content if getattr(b, "type", None) == "text"), None
    )
    if getattr(result, "isError", False):
        raise RuntimeError(f"MCP tool {tool_name} failed: {text}")
    if text is None:
        raise RuntimeError(f"MCP tool {tool_name} returned no text content")
    return json.loads(text)


async def list_server_tools(server_script: str):
    """Spawn ``server_script``, complete the MCP handshake, list its tools.

    Returns the list of tool names the server advertises. Used as a real
    liveness probe: a server that can't start or handshake will raise.
    """
    async with stdio_client(_server_params(server_script)) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            resp = await session.list_tools()
    return [t.name for t in resp.tools]


def _run_in_loop(coro_factory):
    """Run an async coroutine in a dedicated thread with its own Proactor loop.

    On Windows, asyncio subprocesses require a Proactor loop; giving each call
    its own loop keeps this independent of whatever loop the web server uses.
    """
    box = {}

    def worker():
        try:
            if sys.platform == "win32":
                asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                box["value"] = loop.run_until_complete(coro_factory())
            finally:
                loop.close()
        except Exception as exc:  # surfaced to the caller thread
            box["error"] = exc

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    thread.join()
    if "error" in box:
        raise box["error"]
    return box["value"]


def run_tool(server_script: str, tool_name: str, arguments: dict):
    """Synchronous wrapper: call one MCP tool and return its parsed result."""
    return _run_in_loop(lambda: call_tool(server_script, tool_name, arguments))


def ping_server(server_script: str):
    """Synchronous liveness probe: return the server's advertised tool names."""
    return _run_in_loop(lambda: list_server_tools(server_script))
