# ─────────────── base image ───────────────
FROM python:3.11-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app/src \
    OLLAMA_MODELS=/root/.ollama/models

WORKDIR /app

# ── layer 1: install system libs + Python deps (cache-able) ──
COPY requirements.txt ./
RUN set -e; \
    apt-get update; \
    apt-get install -y --no-install-recommends build-essential gcc g++ curl ca-certificates; \
    pip install --no-cache-dir -r requirements.txt; \
    python -m spacy download en_core_web_sm; \
    curl -fsSL https://ollama.com/install.sh | OLLAMA_SKIP_BOOTSTRAP=1 sh; \
    /bin/sh -c 'ollama serve > /tmp/ollama.log 2>&1 & pid=$!; \
        for i in $(seq 1 30); do \
            if curl -sf http://127.0.0.1:11434/api/tags > /dev/null; then break; fi; \
            sleep 1; \
        done; \
        ollama pull qwen2.5:1.5b-instruct-q4_0; \
        kill "${pid}"; \
        wait "${pid}" 2>/dev/null || true'; \
    apt-get purge -y build-essential gcc g++; \
    apt-get autoremove -y; \
    rm -rf /var/lib/apt/lists/*

# ── layer 2: copy application source ──
COPY src/ ./src
COPY Dockerfile/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# ── runtime ──
EXPOSE 8000
ENTRYPOINT ["/entrypoint.sh"]
CMD ["uvicorn", "presidio_pii.main:app", "--host", "0.0.0.0", "--port", "8000", "--timeout-keep-alive", "30"]
