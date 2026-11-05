"""Custom MCP server (stdio) that wraps the fake micro service.

Credentials arrive as environment variables set by the notebook via
StdioServerParameters(env=...): PROXY_USERNAME, PROXY_PASSWORD, PROXY_CERT, PROXY_VERIFY.
NEVER print to stdout here -- stdout is the MCP protocol channel. Log to stderr.
"""
import logging
import os
import sys

import httpx
from mcp.server.fastmcp import FastMCP

logging.basicConfig(stream=sys.stderr, level=logging.INFO, format="[mcp] %(message)s")
log = logging.getLogger(__name__)

BASE_URL = os.environ.get("MICRO_URL", "https://localhost:8443").rstrip("/")
USERNAME = os.environ.get("PROXY_USERNAME", "")
PASSWORD = os.environ.get("PROXY_PASSWORD", "")
CERT = os.environ.get("PROXY_CERT", "")
VERIFY_ON = os.environ.get("PROXY_VERIFY", "true").strip().lower() in {"1", "true", "yes", "on"}

# requests/httpx convention: verify=<ca bundle path> | True (system CAs) | False (no check)
VERIFY: str | bool = (CERT or True) if VERIFY_ON else False
log.info("base=%s user=%s verify=%s", BASE_URL, USERNAME or "<none>", VERIFY)

mcp = FastMCP("ticket-tool")


def _get(path: str, **params) -> dict:
    with httpx.Client(base_url=BASE_URL, auth=(USERNAME, PASSWORD), verify=VERIFY, timeout=15) as c:
        r = c.get(path, params={k: v for k, v in params.items() if v is not None})
    if r.status_code >= 400:
        return {"error": r.status_code, "detail": r.text}
    return r.json()


@mcp.tool()
def whoami() -> dict:
    """Check the proxy credentials work. Returns the authenticated user."""
    return _get("/api/whoami")


@mcp.tool()
def list_tickets(status: str | None = None) -> dict:
    """List support tickets. Optional status filter: open, in_progress, closed."""
    return _get("/api/tickets", status=status)


@mcp.tool()
def get_ticket(ticket_id: str) -> dict:
    """Get one ticket by id, e.g. T-1003."""
    return _get(f"/api/tickets/{ticket_id}")


@mcp.tool()
def search_tickets(query: str) -> dict:
    """Search ticket titles and owning teams for a keyword."""
    return _get("/api/search", q=query)


if __name__ == "__main__":
    mcp.run()  # stdio transport
