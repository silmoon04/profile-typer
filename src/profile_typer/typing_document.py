"""Editable queue state and persistence, independent of any GUI toolkit."""
from __future__ import annotations

import os
import tempfile
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

from .view_schema import QueueEntry, ViewField, ViewRow, ViewFile, dump_views, parse_views


class TypingDocument:
    def __init__(self) -> None:
        self._entries = [QueueEntry(uuid4().hex, "Untitled", "")]
        self.selected_id = self._entries[0].id
        self.path: Path | None = None
        self.dirty = False
        self.locked = False
        self.title = "Typing views"
        self.custom = False

    @property
    def entries(self) -> tuple[QueueEntry, ...]:
        return tuple(self._entries)

    @property
    def selected_index(self) -> int:
        return next(i for i, entry in enumerate(self._entries) if entry.id == self.selected_id)

    @property
    def selected(self) -> QueueEntry:
        return self._entries[self.selected_index]

    def _editable(self) -> None:
        if self.locked:
            raise ValueError("Stop typing before changing the queue.")

    def select(self, entry_id: str) -> None:
        self._editable()
        if not any(entry.id == entry_id for entry in self._entries):
            raise ValueError("That queue item no longer exists.")
        self.selected_id = entry_id

    def navigate(self, offset: int) -> None:
        self._editable()
        index = max(0, min(len(self._entries) - 1, self.selected_index + offset))
        self.selected_id = self._entries[index].id

    def update(self, title: str, description: str) -> None:
        self._editable()
        entry = self.selected
        if entry.rows:
            description = entry.description
        if (entry.title, entry.description) != (title, description):
            status = ("Edited" if entry.copies or entry.types else "Ready") if entry.description != description else entry.status
            self._entries[self.selected_index] = replace(entry, title=title, description=description, status=status)
            self.dirty = True

    def add(self, *, duplicate: bool = False) -> None:
        self._editable()
        previous = self.selected
        if duplicate:
            rows = tuple(replace(row, fields=tuple(replace(field, id=uuid4().hex, copies=0, types=0, status="Ready")
                                                   for field in row.fields)) for row in previous.rows)
            entry = replace(previous, id=uuid4().hex, title=previous.title + " (copy)", rows=rows,
                            copies=0, types=0, status="Ready")
        elif self.custom:
            entry = QueueEntry(uuid4().hex, "Untitled", rows=(ViewRow(1, (ViewField(uuid4().hex, "Description"),)),))
        else:
            entry = QueueEntry(uuid4().hex, "Untitled", "")
        self._entries.insert(self.selected_index + 1, entry)
        self.selected_id = entry.id
        self.dirty = True

    def remove(self) -> None:
        self._editable()
        index = self.selected_index
        self._entries.pop(index)
        if not self._entries:
            rows = (ViewRow(1, (ViewField(uuid4().hex, "Description"),)),) if self.custom else ()
            self._entries.append(QueueEntry(uuid4().hex, "Untitled", rows=rows))
        self.selected_id = self._entries[min(index, len(self._entries) - 1)].id
        self.dirty = True

    def move(self, offset: int) -> None:
        self._editable()
        index = self.selected_index
        destination = max(0, min(len(self._entries) - 1, index + offset))
        if index != destination:
            self._entries.insert(destination, self._entries.pop(index))
            self.dirty = True

    def load(self, path: Path, *, append: bool = False) -> None:
        self._editable()
        content = parse_views(path.read_text(encoding="utf-8-sig"))
        self._import_items(content, append=append, path=path)

    def paste(self, source: str, *, append: bool = False) -> None:
        self._editable()
        content = parse_views(source)
        self._import_items(content, append=append, path=None)

    def _import_items(self, content, *, append, path):
        used = {identity for entry in self._entries for identity in [entry.id, *(field.id for field in entry.fields)]} if append else set()

        def identity(value):
            while value in used:
                value = uuid4().hex
            used.add(value)
            return value

        imported = [replace(entry, id=identity(entry.id), rows=tuple(
            replace(row, fields=tuple(replace(field, id=identity(field.id)) for field in row.fields)) for row in entry.rows))
            for entry in content.entries]
        if append:
            self._entries.extend(imported)
            self.dirty = True
            if content.custom and not self.custom:
                self.title = content.title
            self.custom = self.custom or content.custom
        else:
            self._entries = imported
            self.path = path
            self.dirty = path is None
            self.title = content.title
            self.custom = content.custom
        self.selected_id = imported[0].id

    def save(self, path: Path) -> None:
        self._editable()
        source = dump_views(ViewFile(self.entries, self.title, self.custom))
        temporary: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="\n", dir=path.parent,
                                             prefix=".typing-queue-", suffix=".tmp", delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(source)
            os.replace(temporary, path)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
        self.path = path
        self.dirty = False

    def field(self, field_id: str) -> ViewField:
        for entry in self._entries:
            if not entry.rows and entry.id == field_id:
                return ViewField(entry.id, entry.title, entry.description, copies=entry.copies, types=entry.types, status=entry.status)
            for field in entry.fields:
                if field.id == field_id:
                    return field
        raise ValueError("That field no longer exists.")

    def _change_field(self, field_id, transform):
        for index, entry in enumerate(self._entries):
            if not entry.rows and entry.id == field_id:
                field = transform(self.field(field_id))
                self._entries[index] = replace(entry, description=field.text, status=field.status, copies=field.copies, types=field.types)
                return
            if any(field.id == field_id for field in entry.fields):
                rows = tuple(replace(row, fields=tuple(transform(field) if field.id == field_id else field for field in row.fields))
                             for row in entry.rows)
                self._entries[index] = replace(entry, rows=rows)
                return
        raise ValueError("That field no longer exists.")

    def update_field(self, field_id, text):
        self._editable()
        field = self.field(field_id)
        if field.value != text:
            selected = ()
            stored = text
            if field.options:
                candidates = [text] if text in field.options else text.split("\n")
                if all(item in field.options for item in candidates) and (field.multiple or len(candidates) == 1):
                    selected = tuple(option for option in field.options if option in candidates)
                    stored = ""
            self._change_field(field_id, lambda value: replace(value, text=stored, selected=selected,
                                                               status="Edited" if value.copies or value.types else "Ready"))
            self.dirty = True

    def select_option(self, field_id, option, selected):
        self._editable()
        field = self.field(field_id)
        if option not in field.options:
            raise ValueError("That option no longer exists.")
        choices = set(field.selected)
        if selected:
            choices = choices | {option} if field.multiple else {option}
        else:
            choices.discard(option)
        values = tuple(option for option in field.options if option in choices)
        if values != field.selected or field.text:
            self._change_field(field_id, lambda value: replace(value, selected=values, text="",
                                                               status="Edited" if value.copies or value.types else "Ready"))
            self.dirty = True

    def rename_option(self, field_id, index, text):
        self._editable()
        field = self.field(field_id)
        if not text.strip() or (text in field.options and text != field.options[index]):
            raise ValueError("Option labels must be nonempty and unique within their field.")
        old = field.options[index]
        if old != text:
            options = tuple(text if i == index else option for i, option in enumerate(field.options))
            selected = tuple(text if option == old else option for option in field.selected)
            self._change_field(field_id, lambda value: replace(value, options=options, selected=selected,
                                                               status="Edited" if value.copies or value.types else "Ready"))
            self.dirty = True

    def record_copy(self, field_id):
        self._editable()
        self._change_field(field_id, lambda field: replace(field, copies=field.copies + 1, status="Copied"))
        self.dirty = True

    def reset_usage(self):
        self._editable()
        for field_id in [field.id for field in self.selected.fields] or [self.selected.id]:
            self._change_field(field_id, lambda field: replace(field, copies=0, types=0, status="Ready"))
        self.dirty = True

    def begin_run(self, field_id: str | None = None) -> QueueEntry:
        self._editable()
        entry = self.selected
        if entry.rows and field_id not in {field.id for field in entry.fields}:
            raise ValueError("Use the Type button on the field you want to enter.")
        field = self.field(field_id or entry.id)
        if "type" not in field.actions:
            raise ValueError("Typing is not enabled for that field.")
        if not field.value:
            raise ValueError("Enter a description or select an option before starting.")
        field.value.encode("utf-8")
        self._change_field(field.id, lambda value: replace(value, types=value.types + 1, status="Starting"))
        self.dirty = True
        self.locked = True
        return QueueEntry(field.id, field.title, field.value)

    def set_run_status(self, entry_id: str, status: str) -> None:
        self._change_field(entry_id, lambda field: replace(field, status=status))

    def finish_run(self, entry_id: str, status: str, *, advance: bool) -> None:
        self.set_run_status(entry_id, status)
        self.locked = False
        if advance and status == "Done" and not self.selected.rows:
            self.navigate(1)
