from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from profile_typer.typing_queue import TypingItem, bounded_number, dump_queue, load_queue, parse_queue


class TypingQueueTests(unittest.TestCase):
    def test_single_object_and_array(self):
        source = '{"title": "hello", "description": "text to type out"}'
        expected = [TypingItem("hello", "text to type out")]
        self.assertEqual(parse_queue(source), expected)
        self.assertEqual(parse_queue("[" + source + "]"), expected)

    def test_round_trip_preserves_unicode_whitespace_and_duplicate_titles(self):
        items = [TypingItem("same", "  café 👋\r\n\tend\n\n"), TypingItem("same", "")]
        self.assertEqual(parse_queue(dump_queue(items)), items)

    def test_invalid_input_reports_item_or_json_location(self):
        for source, message in (("{", "line 1"), ("[]", "non-empty"),
                                ('[{"title":"x","description":"ok"},42]', "Item 2"),
                                ('{"title":"x","description":null}', "description must be a string"),
                                ('{"title":" ","description":"x"}', "title must not be blank"),
                                ('{"title":"x","description":"\\ud800"}', "invalid Unicode")):
            with self.subTest(source=source), self.assertRaisesRegex(ValueError, message):
                parse_queue(source)

    def test_windows_utf8_bom(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "queue.json"
            path.write_text(dump_queue([TypingItem("hello", "text")]), encoding="utf-8-sig")
            self.assertEqual(load_queue(path), [TypingItem("hello", "text")])

    def test_numeric_controls_reject_nonfinite_out_of_range_and_partial_values(self):
        for value in ("", "-", "nan", "inf", "121", "14"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                bounded_number(value, "Speed", 15, 120)
        self.assertEqual(bounded_number("75.5", "Speed", 15, 120), 75.5)
