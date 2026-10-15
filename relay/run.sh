#!/usr/bin/env bash
# Start the relay on the Mac:  ./relay/run.sh   (creates relay/.venv on first run)
set -euo pipefail
cd "$(dirname "$0")"
command -v python3 >/dev/null || { echo "need python3 (brew install python)"; exit 1; }
if [ ! -d .venv ]; then python3 -m venv .venv && .venv/bin/pip install -q -r requirements-dev.txt; fi
if [ -z "${XAI_API_KEY:-}" ] && ! grep -qs '^XAI_API_KEY=.\+' .env; then
  echo "set XAI_API_KEY (export XAI_API_KEY=... or put it in relay/.env, see .env.example)"; fi
exec .venv/bin/python -m tamagroki_relay "$@"
