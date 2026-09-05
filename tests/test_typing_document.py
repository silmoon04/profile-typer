from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from profile_typer.typing_document import TypingDocument
from profile_typer.typing_queue import TypingItem, dump_queue, load_queue


class TypingDocumentTests(unittest.TestCase):
    def test_reordering_preserves_identity_selection_and_exact_edits(self):
        document = TypingDocument()
        document.update("first", "  café 👋\n\n")
        first_id = document.selected_id
        document.add(duplicate=True)
        second_id = document.selected_id
        document.move(-1)
        self.assertEqual(document.selected_id, second_id)
        self.assertEqual(document.entries[1].id, first_id)
        self.assertEqual(document.selected.description, "  café 👋\n\n")
        document.navigate(1)
        self.assertEqual(document.selected_id, first_id)
        self.assertTrue(document.dirty)

    def test_import_validation_is_atomic(self):
        document = TypingDocument()
        document.update("work", "unsaved")
        before = document.entries
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.json"
            path.write_text('[{"title":"ok","description":"valid"},{}]', encoding="utf-8")
            with self.assertRaises(ValueError):
                document.load(path)
        self.assertEqual(document.entries, before)
        self.assertTrue(document.dirty)

    def test_save_and_append_round_trip(self):
        document = TypingDocument()
        document.update("hello", "description\n\n")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "queue.json"
            document.save(path)
            self.assertEqual(load_queue(path), [TypingItem("hello", "description\n\n")])
            self.assertFalse(document.dirty)
            document.load(path, append=True)
            self.assertEqual(len(document.entries), 2)
            self.assertEqual(document.selected_index, 1)
            self.assertNotEqual(document.entries[0].id, document.entries[1].id)
            self.assertTrue(document.dirty)

    def test_pasted_json_can_replace_or_append_without_a_file(self):
        document = TypingDocument()
        document.paste('{"title":"hello","description":"café 👋\\n\\n"}')
        self.assertEqual(document.selected.title, "hello")
        self.assertEqual(document.selected.description, "café 👋\n\n")
        self.assertTrue(document.dirty)
        self.assertIsNone(document.path)
        first_id = document.selected_id
        document.paste('[{"title":"next","description":"second"}]', append=True)
        self.assertEqual(len(document.entries), 2)
        self.assertEqual(document.entries[0].id, first_id)
        self.assertEqual(document.selected.title, "next")
        before = document.entries
        with self.assertRaises(ValueError):
            document.paste('[{"title":"valid","description":"ok"},{}]')
        self.assertEqual(document.entries, before)

    def test_failed_save_preserves_existing_file(self):
        document = TypingDocument()
        document.update("hello", "new")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "queue.json"
            path.write_text("original", encoding="utf-8")
            with patch("profile_typer.typing_document.os.replace", side_effect=OSError("denied")), self.assertRaises(OSError):
                document.save(path)
            self.assertEqual(path.read_text(encoding="utf-8"), "original")
            self.assertEqual(list(Path(directory).iterdir()), [path])
        self.assertTrue(document.dirty)
        self.assertIsNone(document.path)

    def test_run_locks_all_document_mutations_and_only_completion_advances(self):
        document = TypingDocument()
        document.update("first", "text")
        document.add()
        document.navigate(-1)
        entry = document.begin_run()
        for action in (lambda: document.update("x", "y"), document.add, document.remove,
                       lambda: document.navigate(1), lambda: document.move(1),
                       lambda: document.select(document.entries[1].id)):
            with self.assertRaises(ValueError):
                action()
        document.finish_run(entry.id, "Stopped", advance=True)
        self.assertEqual(document.selected_id, entry.id)
        document.begin_run()
        document.finish_run(entry.id, "Done", advance=True)
        self.assertEqual(document.selected_index, 1)

    def test_empty_description_does_not_lock_document(self):
        document = TypingDocument()
        with self.assertRaisesRegex(ValueError, "description"):
            document.begin_run()
        self.assertFalse(document.locked)

    def test_remove_last_item_keeps_editable_blank_document(self):
        document = TypingDocument()
        document.remove()
        self.assertEqual(document.selected.description, "")
        self.assertEqual(len(document.entries), 1)

    def test_loading_a_replacement_clears_dirty_state_and_run_statuses(self):
        document = TypingDocument()
        document.update("old", "old")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "queue.json"
            path.write_text(dump_queue([TypingItem("new", "new")]), encoding="utf-8-sig")
            document.load(path)
        self.assertEqual(document.selected.title, "new")
        self.assertEqual(document.selected.status, "Ready")
        self.assertFalse(document.dirty)
