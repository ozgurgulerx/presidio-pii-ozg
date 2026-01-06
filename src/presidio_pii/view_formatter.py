"""Presentation layer helpers for formatting analysis responses."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Dict, Iterable, List, Sequence

if TYPE_CHECKING:  # pragma: no cover - typing only
    from .main import PIIEntity

_TYPE_CANONICAL_MAP = {
    "ad soyad": "PERSON",
    "adsoyad": "PERSON",
    "ad_soyad": "PERSON",
    "doğum tarihi": "DATE",
    "dogum tarihi": "DATE",
    "adres": "ADDRESS",
}

_TYPE_LABELS = {
    "PERSON": "Name",
    "EMAIL_ADDRESS": "Email",
    "PHONE_NUMBER": "Phone Number",
    "CREDIT_CARD": "Credit Card",
    "IBAN": "IBAN",
    "LOCATION": "Location",
    "ADDRESS": "Address",
    "DATE": "Date of Birth",
    "DATE_TIME": "Date / Time",
    "ORGANIZATION": "Organization",
    "NATIONALID": "National ID",
}

_MAX_EXPLANATION = 120
_CONTEXT_WINDOW = 40
_MERGE_DISTANCE = 2


@dataclass
class _DisplayEntity:
    canonical_type: str
    label: str
    start: int
    end: int
    score: float
    origin: str
    explanation: str


def _canonical_type(raw_type: str) -> str:
    normalised = raw_type.strip().casefold()
    if normalised in _TYPE_CANONICAL_MAP:
        return _TYPE_CANONICAL_MAP[normalised]
    # Preserve existing Presidio naming if already canonical
    return raw_type.strip().upper()


def _friendly_label(canonical_type: str, raw_type: str) -> str:
    if canonical_type in _TYPE_LABELS:
        return _TYPE_LABELS[canonical_type]
    # fallback: create a human friendly label from raw type
    if raw_type:
        candidate = raw_type.replace("_", " ").title()
        return candidate
    return canonical_type.title()


def _origin_display(source: str | None) -> str:
    if source and source.lower() == "presidio":
        return "Presidio"
    if source and source.lower() == "llm":
        return "LLM"
    return "Unknown"


def _truncate_explanation(explanation: str) -> str:
    if len(explanation) <= _MAX_EXPLANATION:
        return explanation
    return explanation[: _MAX_EXPLANATION - 1].rstrip() + "…"


def _context_snippet(text: str, start: int, end: int, canonical_type: str) -> str:
    prefix_start = max(0, start - _CONTEXT_WINDOW)
    suffix_end = min(len(text), end + _CONTEXT_WINDOW)
    before = text[prefix_start:start]
    after = text[end:suffix_end]
    return f"{before}[{canonical_type}]{after}"


def _merge_for_display(entities: Sequence["PIIEntity"]) -> List[_DisplayEntity]:
    sorted_entities = sorted(
        entities,
        key=lambda ent: (
            ent.start,
            -ent.score,
            0 if (ent.source or "").lower() == "presidio" else 1,
        ),
    )

    merged: List[_DisplayEntity] = []

    for entity in sorted_entities:
        canonical = _canonical_type(entity.type)
        label = _friendly_label(canonical, entity.type)
        origin = _origin_display(entity.source)
        explanation = _truncate_explanation(entity.explanation or "")

        current = _DisplayEntity(
            canonical_type=canonical,
            label=label,
            start=entity.start,
            end=entity.end,
            score=entity.score,
            origin=origin,
            explanation=explanation,
        )

        if not merged:
            merged.append(current)
            continue

        previous = merged[-1]
        if (
            previous.canonical_type == current.canonical_type
            and current.start <= previous.end + _MERGE_DISTANCE
        ):
            # Merge display only
            new_start = min(previous.start, current.start)
            new_end = max(previous.end, current.end)
            best = previous if previous.score >= current.score else current
            merged[-1] = _DisplayEntity(
                canonical_type=previous.canonical_type,
                label=previous.label,
                start=new_start,
                end=new_end,
                score=max(previous.score, current.score),
                origin="Presidio" if previous.origin == "Presidio" or current.origin == "Presidio" else best.origin,
                explanation=best.explanation,
            )
        else:
            merged.append(current)

    return merged


def _tidy_masked_preview(masked_text: str) -> str:
    if not masked_text:
        return masked_text

    lines = masked_text.splitlines(True)
    result: List[str] = []
    buffer: List[str] = []
    buffer_newline = ""

    for line in lines:
        content = line.rstrip("\r\n")
        newline = line[len(content) :]

        if content and len(content) <= 1:
            buffer.append(content)
            buffer_newline = newline or buffer_newline
            continue

        if buffer:
            combined = "".join(buffer)
            result.append(combined + (buffer_newline or "\n"))
            buffer.clear()
            buffer_newline = ""

        result.append(line)

    if buffer:
        combined = "".join(buffer)
        result.append(combined + (buffer_newline or "\n"))

    return "".join(result)


def build_view(text: str, entities: Iterable["PIIEntity"], masked_text: str) -> Dict[str, object]:
    aggregate = _merge_for_display(list(entities))

    findings_view = []
    stats: Dict[str, int] = {}

    for display in aggregate:
        stats[display.canonical_type] = stats.get(display.canonical_type, 0) + 1
        snippet = _context_snippet(text, display.start, display.end, display.canonical_type)
        findings_view.append(
            {
                "label": display.label,
                "type": display.canonical_type,
                "text_excerpt": snippet,
                "confidence": round(display.score * 100, 2),
                "origin": display.origin,
                "explanation": display.explanation,
            }
        )

    tidy_preview = _tidy_masked_preview(masked_text)

    return {
        "findings": findings_view,
        "masked_preview": tidy_preview,
        "stats": {"total": len(findings_view), "by_type": stats},
    }
