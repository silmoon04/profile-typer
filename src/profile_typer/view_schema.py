"""Small JSON view format and immutable values, with no Qt dependency."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from uuid import uuid4

from .typing_queue import parse_queue

COLORS = {"blue": "#2563eb", "green": "#15803d", "amber": "#b7791f", "red": "#b42318",
          "purple": "#7c3aed", "teal": "#0f766e", "orange": "#c2410c", "gray": "#64748b"}
STATUSES = {"Ready", "Copied", "Edited", "Starting", "Typing", "Done", "Stopped", "Failed"}


@dataclass(frozen=True)
class ViewField:
    id: str
    title: str
    text: str = ""
    options: tuple[str, ...] = ()
    selected: tuple[str, ...] = ()
    multiple: bool = False
    option_columns: int = 1
    actions: tuple[str, ...] = ("copy", "type")
    color: str | None = None
    copies: int = 0
    types: int = 0
    status: str = "Ready"

    @property
    def value(self):
        return "\n".join(option for option in self.options if option in self.selected) if self.options and not self.text else self.text


@dataclass(frozen=True)
class ViewRow:
    columns: int
    fields: tuple[ViewField, ...]


@dataclass(frozen=True)
class QueueEntry:
    id: str
    title: str
    description: str = ""
    status: str = "Ready"
    rows: tuple[ViewRow, ...] = ()
    color: str | None = None
    copies: int = 0
    types: int = 0

    @property
    def fields(self):
        return tuple(field for row in self.rows for field in row.fields)


@dataclass(frozen=True)
class ViewFile:
    entries: tuple[QueueEntry, ...]
    title: str = "Typing views"
    custom: bool = False


def _text(value, where, *, nonempty=False):
    if not isinstance(value, str) or (nonempty and not value.strip()):
        raise ValueError(f"{where} must be {'a nonempty' if nonempty else 'a'} string.")
    if len(value) > 250_000:
        raise ValueError(f"{where} is too long (maximum 250,000 characters).")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as error:
        raise ValueError(f"{where} contains invalid Unicode.") from error
    return value


def _integer(value, where, low=0, high=1_000_000_000):
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise ValueError(f"{where} must be an integer from {low} to {high}.")
    return value


def _color(value, where):
    if value is None:
        return None
    if isinstance(value, str) and (value.lower() in COLORS or re.fullmatch(r"#[0-9a-fA-F]{6}", value)):
        return value.lower()
    raise ValueError(f"{where} must be a named color ({', '.join(COLORS)}) or #RRGGBB.")


def _keys(value, allowed, where):
    if not isinstance(value, dict):
        raise ValueError(f"{where} must be an object.")
    extra = set(value) - allowed
    if extra:
        raise ValueError(f"{where} has unknown fields: {', '.join(sorted(extra))}.")


def _status(value, where):
    if not isinstance(value, str) or value not in STATUSES:
        raise ValueError(f"{where} has an invalid status.")
    return "Stopped" if value in {"Starting", "Typing"} else value


def _unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key: {key}.")
        result[key] = value
    return result


def parse_views(source: str) -> ViewFile:
    if len(source) > 5_000_000:
        raise ValueError("The queue is too large (maximum 5 MB of JSON text).")
    try:
        data = json.loads(source.lstrip("\ufeff"), object_pairs_hook=_unique_pairs)
    except json.JSONDecodeError as error:
        raise ValueError(f"Invalid JSON at line {error.lineno}, column {error.colno}: {error.msg}") from error
    except RecursionError as error:
        raise ValueError("The JSON is nested too deeply.") from error
    identities = set()

    def identity(raw, where):
        value = _text(raw.get("id", uuid4().hex), where + ".id", nonempty=True)
        if value in identities:
            raise ValueError(f"Duplicate id {value!r}; use unique ids or omit them.")
        identities.add(value)
        return value

    if not isinstance(data, dict) or "views" not in data:
        items = parse_queue(source.lstrip("\ufeff"))
        raw_items = data if isinstance(data, list) else [data]
        if len(items) > 500:
            raise ValueError("A queue can contain at most 500 items or views.")
        entries = []
        for index, (item, raw) in enumerate(zip(items, raw_items, strict=True)):
            where = f"items[{index}]"
            _text(item.title, where + ".title", nonempty=True)
            _text(item.description, where + ".description")
            entries.append(QueueEntry(identity(raw, where), item.title, item.description,
                                      _status(raw.get("status", "Ready"), where),
                                      copies=_integer(raw.get("copies", 0), where + ".copies"),
                                      types=_integer(raw.get("types", 0), where + ".types")))
        return ViewFile(tuple(entries))

    _keys(data, {"schema_version", "title", "views"}, "document")
    if type(data.get("schema_version", 1)) is not int or data.get("schema_version", 1) != 1:
        raise ValueError("Unsupported view schema_version; use 1.")
    title = _text(data.get("title", "Typing views"), "document.title", nonempty=True)
    views = data["views"]
    if not isinstance(views, list) or not 1 <= len(views) <= 500:
        raise ValueError("views must contain 1 to 500 view objects.")
    entries = []
    field_count = 0
    for vi, raw_view in enumerate(views):
        where = f"views[{vi}]"
        _keys(raw_view, {"id", "title", "rows", "color"}, where)
        view_id = identity(raw_view, where)
        view_title = _text(raw_view.get("title"), where + ".title", nonempty=True)
        raw_rows = raw_view.get("rows")
        if not isinstance(raw_rows, list) or not 1 <= len(raw_rows) <= 100:
            raise ValueError(f"{where}.rows must contain 1 to 100 rows.")
        rows = []
        for ri, raw_row in enumerate(raw_rows):
            row_path = f"{where}.rows[{ri}]"
            if isinstance(raw_row, list):
                raw_row = {"fields": raw_row, "columns": min(4, len(raw_row))}
            _keys(raw_row, {"columns", "fields"}, row_path)
            columns = _integer(raw_row.get("columns", 1), row_path + ".columns", 1, 4)
            raw_fields = raw_row.get("fields")
            if not isinstance(raw_fields, list) or not 1 <= len(raw_fields) <= 100:
                raise ValueError(f"{row_path}.fields must contain 1 to 100 fields.")
            fields = []
            for fi, raw in enumerate(raw_fields):
                field_count += 1
                if field_count > 5000:
                    raise ValueError("A view document can contain at most 5,000 fields.")
                path = f"{row_path}.fields[{fi}]"
                _keys(raw, {"id", "title", "text", "description", "options", "selected", "multiple", "option_columns",
                            "actions", "color", "copies", "types", "status"}, path)
                field_id = identity(raw, path)
                field_title = _text(raw.get("title"), path + ".title", nonempty=True)
                actions = raw.get("actions", ["copy", "type"])
                if not isinstance(actions, list) or any(action not in ("copy", "type") for action in actions) or len(set(actions)) != len(actions):
                    raise ValueError(f"{path}.actions must be a list containing copy and/or type.")
                options = raw.get("options", [])
                if not isinstance(options, list) or len(options) > 200:
                    raise ValueError(f"{path}.options must be a list with at most 200 labels.")
                options = tuple(_text(option, path + ".options", nonempty=True) for option in options)
                if len(options) != len(set(options)):
                    raise ValueError(f"{path}.options contains duplicate labels.")
                selected = raw.get("selected", [])
                if isinstance(selected, str):
                    selected = [selected]
                if not isinstance(selected, list) or any(not isinstance(option, str) or option not in options for option in selected):
                    raise ValueError(f"{path}.selected must name options from this field.")
                multiple = raw.get("multiple", False)
                if not isinstance(multiple, bool) or (not multiple and len(selected) > 1):
                    raise ValueError(f"{path}: set multiple to true to select more than one option.")
                if len(set(selected)) != len(selected):
                    raise ValueError(f"{path}.selected contains duplicate labels.")
                if "text" in raw and "description" in raw:
                    raise ValueError(f"{path}: use text or description, not both.")
                value = _text(raw.get("text", raw.get("description", "")), path + ".text")
                if options and value and selected:
                    raise ValueError(f"{path}: use selected options or a custom text answer, not both.")
                fields.append(ViewField(field_id, field_title, value, options, tuple(selected), multiple,
                                        _integer(raw.get("option_columns", 1), path + ".option_columns", 1, 4), tuple(actions),
                                        _color(raw.get("color"), path + ".color"),
                                        _integer(raw.get("copies", 0), path + ".copies"),
                                        _integer(raw.get("types", 0), path + ".types"),
                                        _status(raw.get("status", "Ready"), path)))
            rows.append(ViewRow(columns, tuple(fields)))
        entries.append(QueueEntry(view_id, view_title, rows=tuple(rows), color=_color(raw_view.get("color"), where + ".color")))
    return ViewFile(tuple(entries), title, True)


def dump_views(document: ViewFile) -> str:
    if not document.custom and all(not entry.rows for entry in document.entries):
        items = []
        for entry in document.entries:
            raw = {"title": entry.title, "description": entry.description}
            if entry.copies or entry.types or entry.status != "Ready":
                raw.update(id=entry.id, copies=entry.copies, types=entry.types, status=entry.status)
            items.append(raw)
        data = items
    else:
        views = []
        used_ids = {identity for entry in document.entries for identity in [entry.id, *(field.id for field in entry.fields)]}
        for entry in document.entries:
            rows = entry.rows
            if not rows:
                field_id = entry.id + "-description"
                suffix = 1
                while field_id in used_ids:
                    field_id = entry.id + f"-description-{suffix}"
                    suffix += 1
                used_ids.add(field_id)
                rows = (ViewRow(1, (ViewField(field_id, "Description", entry.description,
                                             copies=entry.copies, types=entry.types, status=entry.status),)),)
            raw_view = {"id": entry.id, "title": entry.title, "rows": []}
            if entry.color:
                raw_view["color"] = entry.color
            for row in rows:
                raw_row = {"columns": row.columns, "fields": []}
                for field in row.fields:
                    raw = {"id": field.id, "title": field.title}
                    if field.options:
                        raw.update(options=list(field.options), selected=list(field.selected))
                        if field.text:
                            raw["text"] = field.text
                        if field.multiple:
                            raw["multiple"] = True
                        if field.option_columns != 1:
                            raw["option_columns"] = field.option_columns
                    else:
                        raw["text"] = field.text
                    if field.actions != ("copy", "type"):
                        raw["actions"] = list(field.actions)
                    if field.color:
                        raw["color"] = field.color
                    if field.copies or field.types or field.status != "Ready":
                        raw.update(copies=field.copies, types=field.types, status=field.status)
                    raw_row["fields"].append(raw)
                raw_view["rows"].append(raw_row)
            views.append(raw_view)
        data = {"schema_version": 1, "title": document.title, "views": views}
    source = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    parse_views(source)
    return source
