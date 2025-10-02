# Presidio PII Service (FastAPI)

Detect and anonymize PII with Microsoft Presidio. Deterministic rules and transformer NER run first; for low‑confidence cases the service optionally falls back to a local Qwen‑2.5 model via Ollama. Ships with Docker, docker‑compose, and Azure Container Apps deployment scripts.

## Highlights
- **Presidio analyzer + anonymizer** with spaCy and a HF transformer NER model
- **LLM fallback (optional):** Qwen‑2.5 (CPU, quantized) via Ollama for ambiguous cases
- **Simple REST API:** `POST /analyze`, `GET /health`
- **Production‑ready:** pinned deps, CORS, timeouts, input caps, containerized

## Why this stack
- **Presidio** is a battle‑tested PII toolkit with strong regex/checksum recognizers.
- **spaCy** provides reliable tokenization + language tooling.
- **TransformerRecognizer** (default `dslim/bert-base-NER`) improves entity coverage.
- **Qwen‑2.5 via Ollama** keeps sensitive data local while handling edge cases when rule/NER confidence is low (default `qwen2.5:1.5b-instruct-q4_0`).

## Quickstart

### Option A — Docker Compose (backend only, or with optional frontend)
```bash
# In this repo
docker compose up --build
# API is now on http://localhost:8000
```

Test it:
```bash
curl -s -X POST http://localhost:8000/analyze \
  -H 'Content-Type: application/json' \
  -d '{"text":"My email is john.doe@example.com and my phone is +1-202-555-0123"}' | jq
```

### Option B — Local (Python)
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m spacy download en_core_web_sm

export PII_ALLOWED_ORIGINS="*"
uvicorn presidio_pii.main:app --host 0.0.0.0 --port 8000
```

## API

- **GET** `/health`
  - 200 → `{ "status": "ok" }`

- **POST** `/analyze`
  - Request
    ```json
    { "text": "Name: Ada Lovelace, email ada@compute.org" }
    ```
  - Response
    ```json
    {
      "entities": [
        { "type": "PERSON", "score": 0.99, "start": 6, "end": 17, "text": "Ada Lovelace" },
        { "type": "EMAIL_ADDRESS", "score": 0.99, "start": 26, "end": 42, "text": "ada@compute.org" }
      ],
      "has_pii": true,
      "redacted_text": "Name: [REDACTED_PERSON], email [REDACTED_EMAIL_ADDRESS]"
    }
    ```

## Configuration

Environment variables (with defaults):
- `PII_ALLOWED_ORIGINS` — CORS origins (`,` separated). Default: `*`
- `PII_TRANSFORMER_MODEL` — HF model for `TransformerRecognizer`. Default: `dslim/bert-base-NER`
- `PII_MAX_TEXT_LENGTH` — Max input length. Default: `5000`
- `PII_DETERMINISTIC_THRESHOLD` — Score ≥ τ treated as deterministic. Default: `0.85`
- `PII_LLM_TRIGGER_THRESHOLD` — Score < τ_llm considered uncertain. Default: `0.6`
- `PII_LLM_TIMEOUT_SECONDS` — Ollama request timeout. Default: `15`
- `OLLAMA_BASE_URL` — Ollama base URL. Default: `http://127.0.0.1:11434`
- `OLLAMA_MODEL` — Fallback model id. Default: `qwen2.5:1.5b-instruct-q4_0`

## How it works

```mermaid
graph TD
  A[Client] -->|POST /analyze| B[Presidio Analyzer\n(spaCy + regex + TransformerRecognizer)]
  B --> C{Score >= τ?}
  C -- yes --> E[Entities]
  C -- no  --> D[Ollama Qwen‑2.5 Fallback]
  D --> E
  E --> F[Presidio Anonymizer]
  F --> G[Response JSON]
```

## Deployment

- Azure Container Apps quick start: see `QUICKSTART.md`
- Full guide and IaC notes: see `DEPLOYMENT.md`
- CORS: set `PII_ALLOWED_ORIGINS` to your frontend’s URL(s)

## Optional UI

There is a companion Next.js frontend in `presidio-pii-ozg-frontend`. Point it to this API by setting `NEXT_PUBLIC_ANALYZE_URL` to `https://<backend>/analyze`.

## Security & Privacy
- No raw PII is logged.
- Inputs are capped by `PII_MAX_TEXT_LENGTH`.
- Fallback LLM runs locally via Ollama by default.
