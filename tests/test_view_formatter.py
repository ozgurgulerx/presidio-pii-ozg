import pathlib
import sys
from dataclasses import dataclass

sys.path.append(str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from presidio_pii.view_formatter import build_view


@dataclass
class DummyEntity:
    type: str
    score: float
    start: int
    end: int
    text: str
    source: str | None
    explanation: str | None


def test_build_view_merges_overlapping_entities():
    text = "John Doe met Jane."
    entities = [
        DummyEntity(
            type="PERSON",
            score=0.92,
            start=0,
            end=4,
            text="John",
            source="presidio",
            explanation="Presidio recognizer default scored 0.92.",
        ),
        DummyEntity(
            type="PERSON",
            score=0.81,
            start=3,
            end=8,
            text="n Do",
            source="llm",
            explanation="LLM fallback predicted PERSON with confidence 0.81.",
        ),
    ]

    view = build_view(text, entities, masked_text="[REDACTED_PERSON] met Jane.")

    assert view["stats"]["total"] == 1
    finding = view["findings"][0]
    assert finding["type"] == "PERSON"
    assert finding["origin"] == "Presidio"
    assert "[PERSON]" in finding["text_excerpt"]


def test_build_view_applies_canonical_label_and_origin():
    text = "Doğum tarihi 1990-01-01"
    entity = DummyEntity(
        type="Doğum Tarihi",
        score=0.77,
        start=0,
        end=12,
        text="Doğum tarihi",
        source="llm",
        explanation="LLM fallback predicted DATE with confidence 0.77.",
    )

    view = build_view(text, [entity], masked_text="[REDACTED_DATE] 1990-01-01")

    finding = view["findings"][0]
    assert finding["type"] == "DATE"
    assert finding["label"] == "Date of Birth"
    assert finding["origin"] == "LLM"


def test_build_view_tidy_masked_preview_collapses_single_character_lines():
    tidy = build_view(
        text="Rand",
        entities=[],
        masked_text="R\na\nn\nd\nLine two\n",
    )["masked_preview"]

    assert tidy.startswith("Rand\n")
    assert "Line two" in tidy
