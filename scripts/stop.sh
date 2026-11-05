#!/usr/bin/env bash
# Stop gateway, micro service and Jupyter (leaves ollama running).
cd "$(dirname "$0")/.."
for s in gateway micro jupyter; do
  [[ -f logs/$s.pid ]] && { pkill -P "$(cat logs/$s.pid)" 2>/dev/null; kill "$(cat logs/$s.pid)" 2>/dev/null; rm -f logs/$s.pid; echo "stopped $s"; }
done
