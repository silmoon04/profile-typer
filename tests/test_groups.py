import json
from pathlib import Path

import pytest

from profile_typer.typing_document import TypingDocument
from profile_typer.view_schema import parse_views, dump_views


def source():
    return (Path(__file__).parents[1] / "src/profile_typer/examples/groups.json").read_text(encoding="utf-8")


def test_groups_presets_and_dictionary_fields_round_trip():
    document = parse_views(source())
    assert {row.group for row in document.entries[0].rows} == {
        "Dimension 1: Design", "Dimension 2: Testing", "Dimension 3: Communication"}
    a, b = document.entries[0].rows[0].fields
    assert a.title == "A" and b.title == "B"
    assert a.options == ("1", "2", "3", "4", "5")
    assert a.option_columns == 5
    assert not a.custom_text
    assert parse_views(dump_views(document)) == document


def test_grouped_edits_counts_duplicate_and_append_remain_independent(tmp_path):
    document = TypingDocument()
    document.paste(source())
    field = document.selected.fields[0]
    document.select_option(field.id, "5", True)
    document.record_copy(field.id)
    snapshot = document.begin_run(field.id)
    assert snapshot.description == "5"
    document.finish_run(snapshot.id, "Done", advance=True)
    assert document.selected_index == 0
    document.add(duplicate=True)
    assert document.selected.rows[0].group == "Dimension 1: Design"
    assert document.selected.fields[0].value == "5"
    assert document.selected.fields[0].copies == 0
    document.paste(source(), append=True)
    path = tmp_path / "saved.json"
    document.save(path)
    restored = TypingDocument()
    restored.load(path)
    assert restored.entries == document.entries


@pytest.mark.parametrize("fragment", [
    {"groups": {}},
    {"rows": [], "groups": {"One": []}},
    {"groups": {"One": [{"fields": {"A": {"use": "missing"}}}]}},
    {"groups": [{"title": "One", "rows": [[{"title": "A"}]]}, {"title": "One", "rows": [[{"title": "B"}]]}]},
    {"groups": {"One": [{"fields": {"A": {"display": "unknown"}}}]}},
    {"groups": {"One": [{"fields": {"A": {"options": ["yes"], "custom_text": False, "text": "custom"}}}]}},
])
def test_invalid_groups_fail_without_replacing_document(fragment):
    document = TypingDocument()
    before = document.entries
    with pytest.raises(ValueError):
        document.paste(json.dumps({"views": [{"title": "View", **fragment}]}))
    assert document.entries == before
