#!/usr/bin/env bash
# One-off setup: venv, .env, certs, models.
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p logs certs
[[ -f .env ]] || cp .env.example .env
uv sync -q
bash scripts/make_certs.sh
set -a; source .env; set +a
pgrep -x ollama >/dev/null || (ollama serve > logs/ollama.log 2>&1 &) ; sleep 2
for m in ${ALLOWED_MODELS//,/ }; do ollama pull "$m" 2>&1 | tail -1; done
echo "setup done"
