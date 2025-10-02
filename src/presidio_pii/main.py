from __future__ import annotations

import json
import logging
import os
from functools import lru_cache
from typing import Dict, Iterable, List, Tuple

import httpx
from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from presidio_analyzer import AnalyzerEngine, RecognizerRegistry, RecognizerResult
from presidio_analyzer.nlp_engine import NlpEngineProvider
from presidio_anonymizer import AnonymizerEngine
from presidio_anonymizer.entities import OperatorConfig

try:
    from presidio_analyzer.predefined_recognizers.nlp_engine_recognizers.transformers_recognizer import (
        TransformersRecognizer,
    )
except ImportError:  # pragma: no cover - optional HF dependency
    TransformersRecognizer = None

logger = logging.getLogger("presidio-pii")

DEFAULT_MODEL_ID = os.getenv("PII_TRANSFORMER_MODEL", "dslim/bert-base-NER")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:1.5b-instruct-q4_0")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
MAX_TEXT_LENGTH = int(os.getenv("PII_MAX_TEXT_LENGTH", "5000"))
DETERMINISTIC_THRESHOLD = float(os.getenv("PII_DETERMINISTIC_THRESHOLD", "0.85"))
LLM_TRIGGER_THRESHOLD = float(os.getenv("PII_LLM_TRIGGER_THRESHOLD", "0.6"))
LLM_TIMEOUT_SECONDS = float(os.getenv("PII_LLM_TIMEOUT_SECONDS", "15"))


def _allowed_origins() -> List[str]:
    raw = os.getenv("PII_ALLOWED_ORIGINS", "*")
    values = [item.strip() for item in raw.split(",") if item.strip()]
    return ["*"] if not values else values


class TextRequest(BaseModel):
    """Incoming payload requesting a PII scan."""

    text: str = Field(..., min_length=1, max_length=MAX_TEXT_LENGTH, description="Arbitrary text to scan for PII")


class PIIEntity(BaseModel):
    """Details about a detected PII entity."""

    type: str = Field(..., description="Type of detected entity")
    score: float = Field(..., ge=0.0, le=1.0, description="Confidence score from Presidio or fallback")
    start: int = Field(..., ge=0, description="Start index of the entity in the original text")
    end: int = Field(..., ge=0, description="End index (exclusive) of the entity")
    text: str = Field(..., description="Original text snippet that was detected")


class AnalysisResponse(BaseModel):
    """API response containing the scan results."""

    entities: List[PIIEntity] = Field(default_factory=list, description="List of detected entities")
    has_pii: bool = Field(..., description="Whether any PII entities were detected")
    redacted_text: str | None = Field(default=None, description="Source text with detected PII anonymized")


class OllamaClient:
    """Thin client for interacting with a local Ollama runtime."""

    def __init__(self, base_url: str, model: str, timeout: float) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout = timeout

    async def analyze(self, text: str) -> List[PIIEntity]:
        prompt = (
            "You extract PII entities. Return JSON with a single key 'entities' containing a list of objects "
            "with keys type, text, start, end, score (0-1). Do not include any extra text. If none, return {\"entities\": []}."
        )
        payload = {
            "model": self._model,
            "prompt": f"{prompt}\nInput: {text}",
            "stream": False,
            "options": {"temperature": 0},
        }

        timeout = httpx.Timeout(self._timeout, connect=min(5.0, self._timeout))
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(f"{self._base_url}/api/generate", json=payload)
            response.raise_for_status()

        response_payload = response.json()
        raw_output = response_payload.get("response", "").strip()
        if not raw_output:
            return []

        try:
            parsed = json.loads(raw_output)
        except json.JSONDecodeError as exc:  # pragma: no cover - defensive
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Fallback LLM returned invalid JSON",
            ) from exc

        entities = []
        for item in parsed.get("entities", []):
            try:
                entity = PIIEntity(
                    type=str(item["type"]),
                    text=str(item["text"]),
                    start=int(item["start"]),
                    end=int(item["end"]),
                    score=float(item["score"]),
                )
            except (KeyError, TypeError, ValueError):  # pragma: no cover - validation guard
                continue
            entities.append(entity)
        return entities


app = FastAPI(title="Presidio PII Service", version="0.2.0")
_cors_origins = _allowed_origins()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if _cors_origins == ["*"] else _cors_origins,
    allow_credentials=False,
    allow_methods=["POST", "OPTIONS", "GET"],
    allow_headers=["Authorization", "Content-Type"],
)
anonymizer_engine = AnonymizerEngine()
ollama_client = OllamaClient(base_url=OLLAMA_BASE_URL, model=OLLAMA_MODEL, timeout=LLM_TIMEOUT_SECONDS)


def _build_analyzer() -> AnalyzerEngine:
    nlp_configuration = {
        "nlp_engine_name": "spacy",
        "models": [
            {
                "lang_code": "en",
                "model_name": "en_core_web_sm",
            }
        ],
    }
    provider = NlpEngineProvider(nlp_configuration=nlp_configuration)
    nlp_engine = provider.create_engine()

    registry = RecognizerRegistry()
    registry.load_predefined_recognizers()

    if TransformersRecognizer is not None:
        try:
            transformers_recognizer = TransformersRecognizer()
            registry.add_recognizer(transformers_recognizer)
        except Exception as exc:  # pragma: no cover - defensive safeguard
            logger.warning("Failed to initialize transformers recognizer: %s", exc)
    else:
        logger.info("TransformersRecognizer unavailable; falling back to SpaCy recognizers only")

    return AnalyzerEngine(nlp_engine=nlp_engine, registry=registry, supported_languages=["en"])


@lru_cache(maxsize=1)
def get_analyzer() -> AnalyzerEngine:
    return _build_analyzer()


def _result_to_entity(result: RecognizerResult, source_text: str) -> PIIEntity:
    return PIIEntity(
        type=result.entity_type,
        score=result.score,
        start=result.start,
        end=result.end,
        text=source_text[result.start : result.end],
    )


def _merge_entities(*entity_groups: Iterable[PIIEntity]) -> List[PIIEntity]:
    dedup: Dict[Tuple[int, int, str], PIIEntity] = {}
    for entity in (entity for group in entity_groups for entity in group):
        key = (entity.start, entity.end, entity.type)
        existing = dedup.get(key)
        if existing is None or entity.score > existing.score:
            dedup[key] = entity
    return sorted(dedup.values(), key=lambda item: (item.start, item.end))


def _anonymize_text(text: str, entities: List[PIIEntity]) -> str:
    configs: Dict[str, OperatorConfig] = {}
    for entity in entities:
        if entity.type not in configs:
            configs[entity.type] = OperatorConfig(
                operator_name="replace",
                params={"new_value": f"[REDACTED_{entity.type}]"},
            )
    analyzer_results = [
        RecognizerResult(entity_type=entity.type, start=entity.start, end=entity.end, score=entity.score)
        for entity in entities
    ]

    result = anonymizer_engine.anonymize(text, analyzer_results, configs)
    return result.text


async def _invoke_llm_if_needed(text: str, uncertain_results: List[RecognizerResult]) -> List[PIIEntity]:
    if not uncertain_results:
        return []

    try:
        return await ollama_client.analyze(text)
    except httpx.HTTPError:
        return []


@app.get("/health", tags=["system"])
async def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.post("/analyze", response_model=AnalysisResponse, tags=["pii"])
async def analyze_text(payload: TextRequest) -> AnalysisResponse:
    analyzer = get_analyzer()
    results: List[RecognizerResult] = analyzer.analyze(text=payload.text, language="en")

    deterministic_entities: List[PIIEntity] = []
    uncertain: List[RecognizerResult] = []

    for result in results:
        entity = _result_to_entity(result, payload.text)
        if result.score >= DETERMINISTIC_THRESHOLD:
            deterministic_entities.append(entity)
        elif result.score < LLM_TRIGGER_THRESHOLD:
            uncertain.append(result)
        else:
            deterministic_entities.append(entity)

    fallback_entities: List[PIIEntity] = []
    if not deterministic_entities or uncertain:
        fallback_entities = await _invoke_llm_if_needed(payload.text, uncertain)

    entities = _merge_entities(deterministic_entities, fallback_entities)
    redacted_text = _anonymize_text(payload.text, entities) if entities else payload.text
    return AnalysisResponse(entities=entities, has_pii=bool(entities), redacted_text=redacted_text)
