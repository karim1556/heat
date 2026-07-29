#!/usr/bin/env bash
set -euo pipefail

# Render start command: binds to the port Render assigns via $PORT (falls
# back to 8000 for a local `docker run` without PORT set).
uvicorn backend.main:app --host 0.0.0.0 --port "${PORT:-8000}"
