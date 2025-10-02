#!/usr/bin/env bash
set -euo pipefail

ollama serve > /tmp/ollama-runtime.log 2>&1 &
OLLAMA_PID=$!

cleanup() {
  if ps -p "${OLLAMA_PID}" > /dev/null 2>&1; then
    kill "${OLLAMA_PID}" 2>/dev/null || true
    wait "${OLLAMA_PID}" 2>/dev/null || true
  fi
}

trap cleanup EXIT TERM INT

for _ in $(seq 1 30); do
  if curl -sf http://127.0.0.1:11434/api/tags > /dev/null; then
    break
  fi
  sleep 1
done

exec "$@"
