import json

import pytest

from profile_typer.typing_document import TypingDocument
from profile_typer.typing_queue import load_queue
from profile_typer.view_schema import parse_views, dump_views, ViewFile


def example():
    return {"title": "Guide", "views": [
        {"id": "first", "title": "Repository", "color": "blue", "rows": [
            {"columns": 2, "fields": [{"id": "task", "title": "Task", "text": "hello\n\n"},
                                       {"id": "url", "title": "URL", "text": "https://example.org", "actions": ["copy"]}]},
            {"fields": [{"id": "options", "title": "Capabilities", "options": ["Code", "Tests", "Docs"],
                         "selected": ["Code", "Tests"], "multiple": True, "option_columns": 2}]},
        ]},
        {"id": "second", "title": "Reason", "rows": [[{"id": "reason", "title": "Reason", "description": "because"}]]},
    ]}


def document():
    document = TypingDocument()
    document.paste(json.dumps(example()))
    return document


def test_round_trip_preserves_layout_values_and_selections():
    original = parse_views(json.dumps(example()))
    restored = parse_views(dump_views(original))
    assert restored == original
    assert restored.entries[0].fields[2].value == "Code\nTests"
    assert restored.entries[0].rows[0].columns == 2


def test_copy_and_type_counters_belong_to_fields_and_survive_save(tmp_path):
    doc = document()
    doc.record_copy("url")
    doc.record_copy("url")
    snapshot = doc.begin_run("task")
    assert snapshot.id == "task" and snapshot.description == "hello\n\n"
    assert doc.field("task").types == 1
    doc.finish_run(snapshot.id, "Done", advance=True)
    assert doc.selected_id == "first", "Typing one field must not skip the rest of its view"
    assert doc.field("url").copies == 2
    assert doc.field("url").types == 0
    doc.navigate(1)
    doc.update_field("reason", "edited")
    doc.navigate(-1)
    assert doc.field("task").status == "Done"
    path = tmp_path / "views.json"
    doc.save(path)
    restored = TypingDocument()
    restored.load(path)
    assert restored.entries == doc.entries


def test_cancelled_runs_count_as_starts_but_are_not_done():
    doc = document()
    snapshot = doc.begin_run("task")
    doc.finish_run(snapshot.id, "Stopped", advance=True)
    assert doc.field("task").types == 1
    assert doc.field("task").status == "Stopped"
    assert doc.selected_id == "first"
    doc.update_field("task", "changed")
    assert doc.field("task").types == 1
    assert doc.field("task").status == "Edited"


def test_invalid_or_copy_only_type_does_not_increment():
    doc = document()
    for target in (None, "url", "reason", "missing"):
        with pytest.raises(ValueError):
            doc.begin_run(target)
        assert not doc.locked
    assert doc.field("url").types == 0


def test_options_and_custom_answers_have_one_value():
    doc = document()
    doc.select_option("options", "Docs", True)
    assert doc.field("options").value == "Code\nTests\nDocs"
    doc.select_option("options", "Tests", False)
    assert doc.field("options").value == "Code\nDocs"
    doc.update_field("options", "Something else\n")
    assert doc.field("options").selected == ()
    assert doc.field("options").value == "Something else\n"
    doc.select_option("options", "Tests", True)
    assert doc.field("options").text == ""
    assert doc.field("options").value == "Tests"


def test_single_choice_replaces_previous_selection():
    data = example()
    field = data["views"][0]["rows"][1]["fields"][0]
    field.update(selected="Code", multiple=False)
    doc = TypingDocument()
    doc.paste(json.dumps(data))
    doc.select_option("options", "Tests", True)
    assert doc.field("options").selected == ("Tests",)


def test_append_remaps_duplicate_ids_and_duplicate_resets_usage():
    doc = document()
    doc.record_copy("task")
    doc.add(duplicate=True)
    assert all(field.copies == field.types == 0 for field in doc.selected.fields)
    doc.paste(json.dumps(example()), append=True)
    ids = [identity for entry in doc.entries for identity in [entry.id, *(field.id for field in entry.fields)]]
    assert len(ids) == len(set(ids))
    parse_views(dump_views(ViewFile(doc.entries, doc.title, doc.custom)))


def test_legacy_queue_stays_compatible_and_can_save_counts(tmp_path):
    doc = TypingDocument()
    doc.paste('{"title":"hello","description":"text"}')
    identity = doc.selected_id
    doc.record_copy(identity)
    run = doc.begin_run()
    doc.finish_run(run.id, "Done", advance=False)
    path = tmp_path / "legacy.json"
    doc.save(path)
    assert load_queue(path)[0].description == "text"
    restored = TypingDocument()
    restored.load(path)
    assert restored.selected.copies == restored.selected.types == 1


@pytest.mark.parametrize("change", [
    lambda data: data["views"][0]["rows"][0].update(columns=0),
    lambda data: data["views"][0]["rows"][0].update(columns=True),
    lambda data: data["views"][0].update(color="red; background: url(remote)"),
    lambda data: data["views"][0]["rows"][0]["fields"][1].update(id="task"),
    lambda data: data["views"][0]["rows"][0]["fields"][0].update(copies=-1),
    lambda data: data["views"][0]["rows"][0]["fields"][0].update(status={}),
    lambda data: data["views"][0]["rows"][1]["fields"][0].update(selected=["missing"]),
    lambda data: data["views"][0]["rows"][1]["fields"][0].update(multiple=False),
    lambda data: data.update(schema_version=1.0),
])
def test_invalid_view_import_is_atomic(change):
    doc = document()
    before = doc.entries
    data = example()
    change(data)
    with pytest.raises(ValueError):
        doc.paste(json.dumps(data))
    assert doc.entries == before


def test_duplicate_json_keys_rejected():
    with pytest.raises(ValueError, match="Duplicate JSON key"):
        parse_views('{"views": [], "views": []}')


def test_explicit_status_with_zero_counters_round_trips():
    data = example()
    data["views"][0]["rows"][0]["fields"][0]["status"] = "Failed"
    parsed = parse_views(json.dumps(data))
    assert parse_views(dump_views(parsed)) == parsed


def test_simple_queue_and_custom_views_can_be_combined_and_saved(tmp_path):
    doc = TypingDocument()
    doc.paste('{"title":"Original","description":"keep me"}')
    doc.paste(json.dumps(example()), append=True)
    path = tmp_path / "mixed.json"
    doc.save(path)
    restored = TypingDocument()
    restored.load(path)
    assert len(restored.entries) == 3
    assert restored.entries[0].title == "Original"
    assert restored.entries[0].fields[0].value == "keep me"


def test_mixed_export_allocates_unique_legacy_field_id():
    doc = TypingDocument()
    doc.paste('{"id":"old","title":"Original","description":"keep me"}')
    data = example()
    data["views"][0]["rows"][0]["fields"][0]["id"] = "old-description"
    doc.paste(json.dumps(data), append=True)
    saved = dump_views(ViewFile(doc.entries, doc.title, doc.custom))
    parsed = parse_views(saved)
    assert parsed.entries[0].fields[0].id != "old-description"
    assert parsed.entries[0].fields[0].value == "keep me"
    assert saved == dump_views(ViewFile(doc.entries, doc.title, doc.custom))
