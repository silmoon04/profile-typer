import importlib.util
import json
from pathlib import Path

import pytest

from profile_typer.view_schema import parse_views

spec = importlib.util.spec_from_file_location("convert_answer_guide", Path(__file__).parents[1] / "scripts/convert_answer_guide.py")
converter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(converter)


def state():
    identities = ["task-id", "codebase-source", "repository-url", "license", "commit", "repository-knowledge", "task-type",
                  "capabilities", "prompt", "realism", "quality-differences", "task-upload", "baseline", "automated-tests",
                  "test-coverage", "job-upload", "trial-a", "patch-a", "trial-b", "patch-b", "verification", "correctness-a",
                  "correctness-b", "correctness-reason", "dimension-1-a", "dimension-1-b", "dimension-1-reason",
                  "rubric-1-statement", "rubric-1-dimension", "rubric-1-source", "rubric-1-a", "rubric-1-b", "rubric-1-reason",
                  "quality-a", "quality-b", "preference", "preference-reason", "evaluation-report", "optional-comments"]
    fields = [{"id": identity, "title": identity, "kind": "text", "value": "original " + identity} for identity in identities]
    for field in fields:
        if field["id"] in {"capabilities", "verification"}:
            field.update(kind="multiselect", value=["One"], options=["One", "Two"])
        elif field["id"] in {"automated-tests", "correctness-a", "correctness-b", "rubric-1-a", "rubric-1-b"}:
            field.update(kind="select", value="YES", options=["YES", "NO"])
        elif field["id"] == "rubric-1-dimension":
            field["value"] = "1"
    return {"title": "Example", "fields": fields}


def html(data):
    return '<script type="application/json" id="answer-state">' + json.dumps(data) + '</script><script>throw "do not execute";</script>'


def test_converter_preserves_metadata_and_uses_latest_answer_text():
    original = state()
    result = converter.convert(html(original), [{"title": "prompt", "description": "latest prompt\n\n"}])
    parsed = parse_views(json.dumps(result))
    fields = {field.id: field for entry in parsed.entries for field in entry.fields}
    assert len(fields) == len(original["fields"])
    assert fields["prompt"].value == "latest prompt\n\n"
    assert fields["repository-url"].actions == ("copy",)
    rubric = next(entry for entry in parsed.entries if entry.id == "rubric-1")
    assert [[field.id for field in row.fields] for row in rubric.rows] == [
        ["rubric-1-statement"], ["rubric-1-dimension", "rubric-1-source"], ["rubric-1-a", "rubric-1-b"], ["rubric-1-reason"]]
    assert fields["verification"].selected == ("One",)


def test_converter_rejects_unmatched_answers_and_ambiguous_data_blocks():
    with pytest.raises(ValueError, match="not found"):
        converter.convert(html(state()), [{"title": "unknown", "description": "text"}])
    with pytest.raises(ValueError, match="exactly one"):
        converter.convert(html(state()) + html(state()), [])
