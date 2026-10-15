#!/usr/bin/env bash
# Desktop tests: ../relay (mock device + mock xAI) and the face simulator.
set -euo pipefail
cd "$(dirname "$0")"
( cd ../relay && { [ -d .venv ] || { python3 -m venv .venv && .venv/bin/pip install -q -r requirements-dev.txt; }; } && .venv/bin/python -m pytest -q )
if [ -d "${LVGL_DIR:-../lvgl-sim}" ]; then
  ../relay/.venv/bin/pip install -q pillow && ../relay/.venv/bin/python sim/face/render.py
else
  echo "face sim skipped: git clone -b release/v9.5 --depth 1 https://github.com/lvgl/lvgl.git ../lvgl-sim (or set LVGL_DIR)"
fi
