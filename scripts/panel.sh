#!/usr/bin/env bash
# Start the local control panel on http://127.0.0.1:8000 (override with PORT=9000)
cd "$(dirname "$0")/.."
echo "Control panel: http://127.0.0.1:${PORT:-8000}   (Ctrl+C to stop)"
exec .venv/bin/python app/server.py
