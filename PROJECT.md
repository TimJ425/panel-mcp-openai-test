# Panel + MCP + OpenAI-compatible harness

An experimental example project that gets the following components working together:

- an **OpenAI-compatible model server** that needs an API key and offers several small models
- a **custom MCP server over stdio** that exposes a tool behind credentials
- a **TLS service that needs credentials**, checked against a custom CA certificate (`proxy_username`, `proxy_password`, `proxy_cert`, `proxy_verify`)
- a **Panel chat app started from a Jupyter notebook**, served in its own browser tab through Jupyter's `/proxy/<port>/` URLs instead of a directly exposed port

Every service runs locally, so you can explore the whole stack (and its pitfalls) on one machine.

| Component | Implementation | Where |
|---|---|---|
| OpenAI-compatible model server (API keys, several small models) | FastAPI gateway (checks the Bearer key, allow-lists models, reports context size) → Ollama | `gateway/app.py`, port 8000 |
| Tool that needs credentials | HTTPS "ticket" service with Basic auth and a cert signed by a local CA | `microservice/app.py`, port 8443 |
| `proxy_cert` | `certs/ca.pem` (local CA) | `scripts/make_certs.sh` |
| MCP stdio server | FastMCP server that wraps the ticket service | `mcp_server/server.py` |
| Jupyter with `/proxy/<port>/` URLs | JupyterLab + `jupyter-server-proxy` | `scripts/start.sh`, port 8888 |
| Chat app in a new tab | Panel `ChatInterface` served from the notebook | `create_app()` in the notebook, port 5006 |

## Architecture

```
Browser tab ── http://localhost:8888/proxy/5006/ ──► jupyter-server-proxy ──► Panel (thread in kernel, :5006)
                                                                                  │
                         ┌────────────────────────────────────────────────────────┤
                         ▼                                                        ▼
       OpenAI client (Bearer API key)                                MCPBridge (own event loop/thread)
                         │                                                        │ stdio
                         ▼                                                        ▼
            gateway :8000 /v1 ──► Ollama :11434                       mcp_server/server.py (subprocess)
            qwen2.5:3b, qwen2.5:1.5b, llama3.2:3b                                 │ HTTPS + Basic auth
                                                                                  │ verify=proxy_cert
                                                                                  ▼
                                                                      microservice :8443 (/api/tickets…)
```

## Setup / run

```bash
bash scripts/setup.sh      # uv venv, .env, certs, ollama pull of the 3 models (~5 GB)
bash scripts/start.sh      # ollama, gateway, micro service, jupyter (logs in logs/)
# open http://localhost:8888/lab?token=test → harness.ipynb → run the cell → click the link

bash scripts/stop.sh
```
Run `shutdown()` in a new notebook cell (or restart the kernel) to stop the app and the MCP server.

Quick checks:
```bash
curl -s localhost:8000/v1/models -H "Authorization: Bearer sk-test-123"
curl -s --cacert certs/ca.pem -u testuser:testpass https://localhost:8443/api/tickets
```

## The chat app

- **Model dropdown:** filled from `/v1/models`, along with each model's context window.
- **Context bar:** segments for system + tools, summary, chat and tool results. It also shows the reply reserve, the auto-compact threshold and the server's real prompt token count.
- **Tool calls:** shown as collapsible steps with the arguments and the formatted result. Failed calls are marked "(failed)".
- **Compaction:** each compaction appears in the chat with the token change, the new rolling summary (expanded by default) and the IDs of archived tool results. **Compact now** posts the same report.
- **Answer stats:** a footer under each final answer shows average tok/s, tokens used (in / out, across every model call in the turn) and the time since your message.

## Credentials flow

1. The notebook reads `PROXY_USERNAME`, `PROXY_PASSWORD`, `PROXY_CERT` and `PROXY_VERIFY`.
2. It passes them to the MCP subprocess through `StdioServerParameters(env=...)`. The MCP SDK merges them with a minimal default environment (PATH, HOME…).
3. The MCP server calls the service with `httpx` using `auth=(user, pass)` and `verify = PROXY_CERT if PROXY_VERIFY else False`.
4. The service returns 401 for wrong credentials. With verification on and the wrong CA, the TLS handshake fails.

## Pitfalls and how the notebook handles them

- **No direct server ports.** Panel runs with `pn.serve(..., threaded=True, show=False)` and is reached at `{JUPYTERHUB_SERVICE_PREFIX}proxy/<port>/`. In non-absolute mode, `jupyter-server-proxy` strips the prefix, so Panel serves at `/` without a `prefix=` argument. Bokeh/Panel pages use relative asset URLs, so they work behind the proxy.
- **Websocket origin.** Bokeh rejects websockets from origins it doesn't know. `websocket_origin` must include the *Jupyter* host as the browser sees it, not just localhost. Set it with `PANEL_WS_ORIGINS`. A blank page or a 403 in the browser console usually means this is wrong.
- **Event loops.** Jupyter owns one loop, and the Panel thread has another. The MCP stdio session lives on a third, dedicated loop (`MCPBridge`). It is opened and closed inside one task, which avoids anyio's "cancel scope in a different task" errors. Panel callbacks reach it with `run_coroutine_threadsafe` + `wrap_future`.
- **ipykernel's `stderr` has no `fileno()`.** `stdio_client` gets `errlog=open("logs/mcp_server.log")`. Without this, the server fails to start inside Jupyter.
- **Small models and tools.** The 1.5B–3B models sometimes send bad tool arguments or return empty replies. The agent loop treats invalid JSON as `{}`, caps tool rounds at `MAX_TOOL_STEPS`, passes tool errors back to the model as text, and retries an empty reply once without tools.
- **`mcp` 2.x renamed `FastMCP` and changed APIs.** This project pins `mcp>=1.9,<2`. On 2.x, the server import becomes `from mcp.server.mcpserver import MCPServer`, and other parts of the code need porting too.
- **Python 3.13+ uses strict X.509 checks.** A CA or cert without an Authority/Subject Key Identifier fails with `Missing Authority Key Identifier`, even though curl accepts it. `make_certs.sh` adds both. Don't switch off `PROXY_VERIFY` to get around it.
- **Panel steps.** `ChatStep.title` is a constant parameter: set `success_title` / `failed_title` when the step is created and change only `status`. Steps that shrink to fit wrap their titles mid-word, so they are stretched to full width.
- **One sync OpenAI client** runs in `asyncio.to_thread`, so it can serve every Panel session without tying an async client to one event loop.

## Context window management (`Conversation` in the notebook)

**Without it:** Ollama silently truncates an over-long prompt to about half the window, so the model forgets things with no error (tested: a fact at the start of a 30k-token prompt was lost).
vLLM-style servers return `400 context_length_exceeded` instead. The gateway imitates that (`GATEWAY_ENFORCE_CONTEXT=true`).

`Conversation` keeps the full history, including tool calls and results. Before each model call, if the estimate is over `COMPACT_AT` (70%) of window − `RESERVE_OUTPUT`:
1. Old tool results → 300-char preview. The full text is archived, and the model can fetch it with the local `recall_tool_result` tool, so MCP data is never lost.
2. Turns older than `KEEP_TURNS` → rolling summary, one bullet per ticket/topic, keeping IDs, statuses, numbers and errors. It's done in chunks, so the summarising call can't overflow.
3. Last resort: shorten the current turn's tool results, then drop the oldest turns.

- If the server still rejects a prompt as too long, the harness reads the real limit from the error message, compacts with a more pessimistic estimate and retries once. If that still fails, it shows a clear message and doesn't crash.
- The token estimate is chars ÷ `chars_per_token`, recalibrated after every call from `usage.prompt_tokens`.
- The context size per model comes from `/v1/models` (`context_length` / `max_model_len`). Use `CONTEXT_OVERRIDES` if a server doesn't report it.

## Pointing it at other services (config only)

| Setting | Change to |
|---|---|
| `OPENAI_BASE_URL`, `OPENAI_API_KEY` | another OpenAI-compatible server and its key |
| `MCP_SERVER_SCRIPT` | path to a different MCP stdio server |
| `MCP_ENV` | the credentials / settings that server reads |
| `PANEL_PORT` | any free port the Jupyter proxy can reach |
| `PANEL_WS_ORIGINS` | the Jupyter hostname(s) as seen by the browser |

`load_env(...)` reads `.env`. Replace it with a secrets store if you have one.

## Layout

```
gateway/app.py             OpenAI-compatible gateway (API keys → Ollama)
microservice/app.py        ticket service (HTTPS + Basic auth)
mcp_server/server.py       MCP stdio server (tools: whoami, list_tickets, get_ticket, search_tickets)
notebooks/harness_cell.py  the harness source (one notebook cell)
notebooks/harness.ipynb    GENERATED from it by scripts/build_notebook.py
scripts/                   setup / start / stop / make_certs / build_notebook
certs/ logs/ .env          generated, not committed
```
