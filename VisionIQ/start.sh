#!/usr/bin/env bash
# Start VisionIQ on one port: Python backend (API + Socket.IO) + built React frontend + NH5 Highway models (one website).
#   ./start.sh            -> http://<this-machine>:8080
set -e
cd "$(dirname "$0")"
NH5_DIR="${NH5_DIR:-../NH5 Highway}"
PY="$NH5_DIR/.venv/bin/python"
if [ ! -x "$PY" ]; then
  echo "Python venv not found at $PY -- set NH5_DIR to the NH5 Highway folder" >&2
  exit 1
fi
if [ ! -f dist/index.html ]; then
  echo "Building the frontend (first run)..."
  npm ci --no-audit --no-fund && npm run build
fi
GUNICORN="$NH5_DIR/.venv/bin/gunicorn"
if [ -x "$GUNICORN" ]; then
  # production server: one worker (models on the GPU), threads for requests/streams/websockets
  exec "$GUNICORN" -c backend/gunicorn.conf.py
fi
echo "gunicorn not installed in $NH5_DIR/.venv -- falling back to the development server" >&2
exec "$PY" backend/server.py
