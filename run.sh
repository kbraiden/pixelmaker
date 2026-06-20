#!/usr/bin/env bash
# PixelMaker launcher (macOS / Linux)
# Creates a virtual environment, installs dependencies, starts the server,
# and opens your browser. Re-run any time to start the app.
set -euo pipefail
cd "$(dirname "$0")"

HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8000}"

if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3 is not installed. Install Python 3.10+ from https://www.python.org/downloads/ and try again." >&2
  exit 1
fi

if [ ! -d ".venv" ]; then
  echo "Creating virtual environment (.venv)..."
  python3 -m venv .venv
fi

VENV_PY=".venv/bin/python"

echo "Installing dependencies..."
"$VENV_PY" -m pip install --quiet --upgrade pip
"$VENV_PY" -m pip install --quiet -r requirements.txt

URL="http://${HOST}:${PORT}"
echo "Starting PixelMaker at ${URL}"
(
  sleep 2
  if command -v open >/dev/null 2>&1; then open "$URL";
  elif command -v xdg-open >/dev/null 2>&1; then xdg-open "$URL";
  fi
) >/dev/null 2>&1 &

exec "$VENV_PY" -m uvicorn app.main:app --host "$HOST" --port "$PORT"
