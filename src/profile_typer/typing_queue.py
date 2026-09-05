"""JSON documents for the typing queue. Titles are labels, descriptions are input."""
from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass
class TypingItem:
    title: str
    description: str


def parse_queue(source: str) -> list[TypingItem]:
    try:
        data = json.loads(source)
    except json.JSONDecodeError as error:
        raise ValueError(f"Invalid JSON at line {error.lineno}, column {error.colno}: {error.msg}") from error
    if isinstance(data, dict):
        data = [data]
    if not isinstance(data, list) or not data:
        raise ValueError("Use an object or a non-empty array of objects with title and description fields.")
    items = []
    for index, entry in enumerate(data, 1):
        if not isinstance(entry, dict):
            raise ValueError(f"Item {index} must be an object with title and description fields.")
        for field in ("title", "description"):
            if not isinstance(entry.get(field), str):
                raise ValueError(f"Item {index}: {field} must be a string.")
            try:
                entry[field].encode("utf-8")
            except UnicodeEncodeError as error:
                raise ValueError(f"Item {index}: {field} contains an invalid Unicode character.") from error
        if not entry["title"].strip():
            raise ValueError(f"Item {index}: title must not be blank.")
        items.append(TypingItem(entry["title"], entry["description"]))
    return items


def load_queue(path: Path) -> list[TypingItem]:
    return parse_queue(path.read_text(encoding="utf-8-sig"))


def dump_queue(items: list[TypingItem]) -> str:
    source = json.dumps([asdict(item) for item in items], ensure_ascii=False, indent=2) + "\n"
    parse_queue(source)
    return source


def bounded_number(value: str, label: str, minimum: float, maximum: float) -> float:
    try:
        number = float(value)
    except ValueError as error:
        raise ValueError(f"{label} must be a number between {minimum:g} and {maximum:g}.") from error
    if not math.isfinite(number) or not minimum <= number <= maximum:
        raise ValueError(f"{label} must be between {minimum:g} and {maximum:g}.")
    return number
