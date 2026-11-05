"""Ticket service. HTTPS (cert signed by a local CA) + HTTP Basic auth.

The MCP server must send proxy_username/proxy_password and verify TLS with
proxy_cert (unless proxy_verify is false).
"""
import os
import secrets

from fastapi import Depends, FastAPI, HTTPException
from fastapi.security import HTTPBasic, HTTPBasicCredentials

USER = os.environ.get("MICRO_EXPECTED_USERNAME", "testuser")
PASS = os.environ.get("MICRO_EXPECTED_PASSWORD", "testpass")

app = FastAPI(title="Fake micro service")
basic = HTTPBasic(auto_error=False)

TICKETS = {
    "T-1001": {"id": "T-1001", "title": "VPN drops every 30 minutes", "status": "open", "priority": "high", "owner": "network"},
    "T-1002": {"id": "T-1002", "title": "Laptop battery replacement", "status": "closed", "priority": "low", "owner": "desktop"},
    "T-1003": {"id": "T-1003", "title": "Jupyter kernel keeps dying", "status": "open", "priority": "medium", "owner": "data-platform"},
    "T-1004": {"id": "T-1004", "title": "Proxy rejects Python requests", "status": "in_progress", "priority": "high", "owner": "network"},
    "T-1005": {"id": "T-1005", "title": "Request access to model gateway", "status": "open", "priority": "medium", "owner": "ai-platform"},
}


def require_creds(creds: HTTPBasicCredentials | None = Depends(basic)) -> str:
    ok = creds is not None and secrets.compare_digest(creds.username, USER) and secrets.compare_digest(creds.password, PASS)
    if not ok:
        raise HTTPException(401, "Proxy credentials missing or invalid", headers={"WWW-Authenticate": "Basic"})
    return creds.username


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/api/whoami")
def whoami(user: str = Depends(require_creds)):
    return {"user": user}


@app.get("/api/tickets")
def list_tickets(status: str | None = None, user: str = Depends(require_creds)):
    items = [t for t in TICKETS.values() if status is None or t["status"] == status]
    return {"count": len(items), "tickets": items}


@app.get("/api/tickets/{ticket_id}")
def get_ticket(ticket_id: str, user: str = Depends(require_creds)):
    if ticket_id.upper() not in TICKETS:
        raise HTTPException(404, f"Ticket {ticket_id} not found")
    return TICKETS[ticket_id.upper()]


@app.get("/api/search")
def search(q: str, user: str = Depends(require_creds)):
    q = q.lower()
    hits = [t for t in TICKETS.values() if q in t["title"].lower() or q in t["owner"]]
    return {"query": q, "count": len(hits), "tickets": hits}
