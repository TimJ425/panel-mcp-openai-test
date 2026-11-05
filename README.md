# Panel + MCP + OpenAI-compatible harness

An experimental example project that wires together an **OpenAI-compatible model server**, a **custom MCP server over stdio**, a **TLS service that needs credentials** and a **Panel chat app launched from a Jupyter notebook**. Everything runs locally, so you can explore the whole stack and its pitfalls on one machine.

![Stack](https://img.shields.io/badge/stack-Panel%20%7C%20MCP%20%7C%20OpenAI%20API%20%7C%20Ollama-6366f1)
![Python](https://img.shields.io/badge/python-3.11%2B-blue)
![Status](https://img.shields.io/badge/status-experimental-orange)

## Contents

- [Features](#features)
- [How it fits together](#how-it-fits-together)
- [Requirements](#requirements)
- [Installation](#installation)
- [Usage](#usage)
- [Configuration](#configuration)
- [Project structure](#project-structure)
- [Development](#development)
- [Troubleshooting](#troubleshooting)
- [Known limitations](#known-limitations)
- [Contributing](#contributing)
- [License](#license)

## Features

- **OpenAI-compatible gateway** in front of Ollama:
  - needs an API key
  - offers three small models (`qwen2.5:3b`, `qwen2.5:1.5b`, `llama3.2:3b`)
  - reports each model's context window
  - rejects prompts that are too long, like vLLM does
- **Custom MCP stdio server** with ticket tools (`whoami`, `list_tickets`, `get_ticket`, `search_tickets`). It reaches a backend over HTTPS using `proxy_username`, `proxy_password`, `proxy_cert` and `proxy_verify`.
- **Ticket service:** HTTPS with Basic auth, using a certificate signed by its own local CA.
- **Panel chat app**, served from a single notebook cell and opened in a new tab through Jupyter's `/proxy/<port>/` URL. It has:
  - a model picker and a light/dark theme toggle
  - a **context window bar** with a segment for each part of the prompt
  - tool calls shown as collapsible steps, with failed calls marked
  - **automatic context compaction** (old tool results shortened, older turns summarised, oldest turns dropped as a last resort). Each compaction's summary is shown in the chat.
  - a **stats footer** under each answer: tok/s, tokens used and response time

## How it fits together

```
Browser tab ── localhost:8888/proxy/5006/ ──► jupyter-server-proxy ──► Panel app (thread in the notebook kernel)
                                                                          │                         │
                                                         OpenAI client (API key)        MCP client (stdio)
                                                                          ▼                         ▼
                                                     gateway :8000 ──► Ollama :11434     mcp_server/server.py
                                                                                                    │ HTTPS + Basic auth
                                                                                                    ▼
                                                                                    ticket service :8443
```

For the design and the problems it solves (event loops, the websocket origin, stderr in Jupyter, how compaction works), see [PROJECT.md](PROJECT.md).

## Requirements

### Install these yourself

| Tool | Version | Why | Install (macOS) |
|---|---|---|---|
| [Python](https://www.python.org/) | 3.11+ | runs everything | `brew install python` (uv can also install it for you) |
| [uv](https://docs.astral.sh/uv/) | 0.5+ | creates the virtualenv and installs Python packages | `brew install uv` or `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| [Ollama](https://ollama.com/) | 0.5+ (tested on 0.40) | runs the local models | `brew install ollama` or the app from ollama.com |
| OpenSSL / LibreSSL | any | generates the local CA and server certificate | preinstalled on macOS and most Linux distros |
| bash, curl | any | setup scripts and quick checks | preinstalled on macOS and most Linux distros |

On Linux, install the same tools with your package manager plus the Ollama install script. On Windows, use **WSL2**: the scripts are written for bash.

### Hardware

- About **6 GB free disk space** for the three models (about 5 GB) and the virtualenv.
- **8 GB+ RAM** is recommended. The models are 1.5B–3B parameters and run on CPU or Apple Silicon / GPU.

### Installed for you by `uv`

You don't need to install these by hand: `scripts/setup.sh` installs them from [pyproject.toml](pyproject.toml).

| Package | Used by |
|---|---|
| `panel` | the chat app |
| `mcp` (`>=1.9,<2`) | MCP client in the notebook and the MCP server |
| `openai` | client for the model gateway |
| `jupyterlab`, `jupyter-server-proxy`, `ipykernel` | the notebook and its `/proxy/<port>/` URLs |
| `fastapi`, `uvicorn`, `httpx` | the gateway, the ticket service and the MCP server's HTTP calls |

### Models pulled by `setup.sh`

`qwen2.5:3b`, `qwen2.5:1.5b`, `llama3.2:3b` (change them with `ALLOWED_MODELS` in `.env`).

## Installation

```bash
git clone <this-repo> panel-mcp-openai-test
cd panel-mcp-openai-test
bash scripts/setup.sh
```

`setup.sh` does the following:

1. creates `logs/` and `certs/`, and copies `.env.example` to `.env`
2. runs `uv sync` to create `.venv` and install the Python packages
3. generates a local CA (`certs/ca.pem`) and a `localhost` server certificate
4. starts Ollama if it isn't running, then pulls the three models

## Usage

1. **Start the services** (Ollama, gateway, ticket service, JupyterLab):

   ```bash
   bash scripts/start.sh
   ```

2. **Open JupyterLab** at <http://localhost:8888/lab?token=test>. The password/token is `test`.
3. Open **`harness.ipynb`** and run its single cell. It starts the MCP server, checks the credentials (`whoami`) and starts the Panel app.
4. **Click the link** the cell prints. The app opens at <http://localhost:8888/proxy/5006/>.
5. Ask about tickets, for example *"what open tickets are there?"* or *"show me T-1003"*.
6. When you're done, run `shutdown()` in a new cell (or restart the kernel), then:

   ```bash
   bash scripts/stop.sh   # stops the gateway, ticket service and Jupyter (Ollama keeps running)
   ```

### Checking the services directly

```bash
curl -s localhost:8000/v1/models -H "Authorization: Bearer sk-test-123"                 # models + context sizes
curl -s localhost:8000/v1/models                                                         # 401 without a key
curl -s --cacert certs/ca.pem -u testuser:testpass https://localhost:8443/api/tickets    # tickets
curl -s --cacert certs/ca.pem -u wrong:creds https://localhost:8443/api/tickets          # 401
```

## Configuration

All settings live in `.env` (template: [.env.example](.env.example)). The services and the notebook all read it.

| Variable | Default | Purpose |
|---|---|---|
| `GATEWAY_API_KEYS` | `sk-test-123,sk-test-456` | API keys the gateway accepts |
| `ALLOWED_MODELS` | `qwen2.5:3b,qwen2.5:1.5b,llama3.2:3b` | models the gateway offers |
| `OLLAMA_CONTEXT_LENGTH` / `MODEL_CONTEXT` | `4096` | context window Ollama uses and the gateway reports (keep them equal) |
| `GATEWAY_ENFORCE_CONTEXT` | `true` | reject over-long prompts with a 400 instead of letting Ollama silently truncate them |
| `OPENAI_BASE_URL`, `OPENAI_API_KEY` | `http://127.0.0.1:8000/v1`, `sk-test-123` | what the notebook uses to reach the gateway |
| `MICRO_EXPECTED_USERNAME` / `_PASSWORD` | `testuser` / `testpass` | credentials the ticket service accepts |
| `PROXY_USERNAME`, `PROXY_PASSWORD` | `testuser`, `testpass` | credentials the notebook passes to the MCP server |
| `PROXY_CERT` | `certs/ca.pem` | CA bundle used to verify the ticket service |
| `PROXY_VERIFY` | `true` | `false` turns off TLS verification (testing only) |
| `PANEL_PORT` | `5006` | port the Panel app listens on |
| `PANEL_WS_ORIGINS` | `localhost:8888,…` | hosts allowed to open the app's websocket (must include the Jupyter host) |

Harness tuning (context reserve, compaction thresholds, `CONTEXT_OVERRIDES`, tool-step limit) is set as constants near the top of [notebooks/harness_cell.py](notebooks/harness_cell.py).

## Project structure

```
.
├── gateway/app.py             OpenAI-compatible gateway (API keys, model allow-list, context limits) → Ollama
├── microservice/app.py        ticket service (HTTPS + Basic auth)
├── mcp_server/server.py       MCP stdio server wrapping the ticket service
├── notebooks/
│   ├── harness_cell.py        source of the harness (the notebook's single cell)
│   └── harness.ipynb          generated from harness_cell.py, don't edit by hand
├── scripts/
│   ├── setup.sh               one-off setup (venv, .env, certs, models)
│   ├── start.sh / stop.sh     start / stop the services
│   ├── make_certs.sh          local CA + server certificate
│   └── build_notebook.py      wraps harness_cell.py into harness.ipynb
├── .env.example               configuration template
├── pyproject.toml             Python dependencies
├── PROJECT.md                 design notes and pitfalls
└── CLAUDE.md                  rules for AI coding assistants working on this repo
```

`certs/`, `logs/`, `.env` and `.venv/` are generated and git-ignored.

## Development

- **Editing the harness:** change `notebooks/harness_cell.py`, then rebuild the notebook:

  ```bash
  python3 scripts/build_notebook.py
  ```

  In JupyterLab, use **File → Reload Notebook from Disk** and re-run the cell.
- **Code style:** Google-style docstrings, built-in / pipe type hints (`str | None`, no `typing` imports), descriptive names (no single-letter variables), single-line comments only where the code is complex.
- **Lint:**

  ```bash
  uvx ruff check --select F,E9,B,N --ignore F821,B008 notebooks/harness_cell.py
  ```

  `F821` is ignored because the cell refers to `server` / `bridge` from earlier runs.
- **Logs:** `logs/gateway.log`, `logs/micro.log`, `logs/jupyter.log`, `logs/mcp_server.log`.
- **MCP server rule:** never print to stdout in `mcp_server/server.py`. Stdout carries the MCP protocol, so log to stderr instead.

## Troubleshooting

| Symptom | Likely cause / fix |
|---|---|
| Jupyter asks for a password | it's `test` (set in `scripts/start.sh`) |
| `500 Internal Server Error` at `/proxy/5006/` | the Panel app isn't running: run the notebook cell (and don't run `shutdown()` straight after) |
| App page is blank / 403 in the browser console | the Jupyter host is missing from `PANEL_WS_ORIGINS` |
| `MCP server failed to start` | read `logs/mcp_server.log`. Check that the ticket service is up and `mcp` is `<2` |
| `CERTIFICATE_VERIFY_FAILED … Missing Authority Key Identifier` | Python 3.13+ strict X.509 checks. Regenerate the certs with `scripts/make_certs.sh` (delete `certs/` first) |
| `401` from the gateway | wrong or missing `OPENAI_API_KEY` |
| `401` from tools (`whoami` fails) | `PROXY_USERNAME` / `PROXY_PASSWORD` don't match `MICRO_EXPECTED_*` |
| Model gives wrong or odd tool calls | expected with 1.5B–3B models. Expand the tool step to see the arguments it sent, or pick `qwen2.5:3b` |
| Port already in use | change `PANEL_PORT`, or run `scripts/stop.sh` and `shutdown()` in the old kernel |

## Known limitations

- The small local models are fast but make mistakes with tools: wrong arguments, repeated calls, sometimes wrong answers.
- Replies are not streamed, so tok/s is an effective rate that includes prompt processing.
- Token counts are estimated (chars ÷ a ratio recalibrated from the server's counts) between calls. The bar can be off by about 10–20% before the first reply.
- The `mcp` package is pinned below 2.0, because 2.x renamed `FastMCP` and changed its APIs.
- The scripts target macOS / Linux (bash). On Windows, use WSL2.
- Credentials, API keys and the Jupyter token are test values: this is a local experiment, not a hardened deployment.

## Contributing

This is an experimental example project. Issues and pull requests that make it clearer or more robust are welcome:

1. Keep the notebook limited to `panel`, `mcp`, `openai` and the standard library.
2. Follow the code style in [Development](#development) and run the lint command.
3. Check your change end to end: run the notebook cell and use the app through `/proxy/5006/`.

## License

No license has been chosen yet. Add one (for example MIT) before publishing or sharing the code.
