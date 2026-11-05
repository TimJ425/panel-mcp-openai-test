#!/usr/bin/env bash
# Start ollama, gateway, micro service and Jupyter in the background. Logs -> logs/*.log
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p logs
set -a; source .env; set +a

pgrep -x ollama >/dev/null || (nohup ollama serve > logs/ollama.log 2>&1 &)

nohup uv run uvicorn gateway.app:app --port "$GATEWAY_PORT" > logs/gateway.log 2>&1 &
echo $! > logs/gateway.pid

nohup uv run uvicorn microservice.app:app --port "$MICRO_PORT" \
  --ssl-certfile certs/server.pem --ssl-keyfile certs/server.key > logs/micro.log 2>&1 &
echo $! > logs/micro.pid

# Jupyter with jupyter-server-proxy => apps reachable at http://localhost:8888/proxy/<port>/
nohup uv run jupyter lab --no-browser --port 8888 --IdentityProvider.token=test \
  --notebook-dir=notebooks > logs/jupyter.log 2>&1 &
echo $! > logs/jupyter.pid

sleep 3
echo "gateway : http://127.0.0.1:$GATEWAY_PORT/health"
echo "micro   : $MICRO_URL/health"
echo "jupyter : http://localhost:8888/lab?token=test  (open harness.ipynb)"
