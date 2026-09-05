"""Editable queue state and persistence, independent of any GUI toolkit."""
from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass, replace
from pathlib import Path
from uuid import uuid4

from .typing_queue import TypingItem, dump_queue, load_queue, parse_queue


@dataclass(frozen=True)
class QueueEntry:
    id: str
    title: str
    description: str
    status: str = "Ready"


class TypingDocument:
    def __init__(self) -> None:
        self._entries = [QueueEntry(uuid4().hex, "Untitled", "")]
        self.selected_id = self._entries[0].id
        self.path: Path | None = None
        self.dirty = False
        self.locked = False

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
        if (entry.title, entry.description) != (title, description):
            status = "Ready" if entry.description != description else entry.status
            self._entries[self.selected_index] = replace(entry, title=title, description=description, status=status)
            self.dirty = True

    def add(self, *, duplicate: bool = False) -> None:
        self._editable()
        previous = self.selected
        entry = QueueEntry(uuid4().hex, previous.title + " (copy)" if duplicate else "Untitled",
                           previous.description if duplicate else "")
        self._entries.insert(self.selected_index + 1, entry)
        self.selected_id = entry.id
        self.dirty = True

    def remove(self) -> None:
        self._editable()
        index = self.selected_index
        self._entries.pop(index)
        if not self._entries:
            self._entries.append(QueueEntry(uuid4().hex, "Untitled", ""))
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
        items = load_queue(path)
        self._import_items(items, append=append, path=path)

    def paste(self, source: str, *, append: bool = False) -> None:
        self._editable()
        items = parse_queue(source.lstrip("\ufeff"))
        self._import_items(items, append=append, path=None)

    def _import_items(self, items, *, append, path):
        imported = [QueueEntry(uuid4().hex, item.title, item.description) for item in items]
        if append:
            self._entries.extend(imported)
            self.dirty = True
        else:
            self._entries = imported
            self.path = path
            self.dirty = path is None
        self.selected_id = imported[0].id

    def save(self, path: Path) -> None:
        self._editable()
        source = dump_queue([TypingItem(entry.title, entry.description) for entry in self._entries])
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

    def begin_run(self) -> QueueEntry:
        self._editable()
        entry = self.selected
        if not entry.description:
            raise ValueError("Enter a description before starting.")
        entry.description.encode("utf-8")
        self.locked = True
        self._entries[self.selected_index] = replace(entry, status="Starting")
        return entry

    def set_run_status(self, entry_id: str, status: str) -> None:
        for index, entry in enumerate(self._entries):
            if entry.id == entry_id:
                self._entries[index] = replace(entry, status=status)
                return
        raise ValueError("The running item no longer exists.")

    def finish_run(self, entry_id: str, status: str, *, advance: bool) -> None:
        self.set_run_status(entry_id, status)
        self.locked = False
        if advance and status == "Done":
            self.navigate(1)
