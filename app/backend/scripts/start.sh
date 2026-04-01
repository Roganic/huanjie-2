#!/bin/sh
set -e

HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8000}"

exec uvicorn src.main:app --host "$HOST" --port "$PORT"
