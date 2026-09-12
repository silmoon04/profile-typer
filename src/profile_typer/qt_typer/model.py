"""Qt list adapter; the document owns the queue and item identities."""
from __future__ import annotations

from PySide6.QtCore import QAbstractListModel, Qt

from profile_typer.typing_document import TypingDocument


class QueueModel(QAbstractListModel):
    IdentityRole = int(Qt.ItemDataRole.UserRole) + 1
    SearchRole = IdentityRole + 1

    def __init__(self, document: TypingDocument, parent=None):
        super().__init__(parent)
        self.document = document
        self._entries = document.entries

    def rowCount(self, parent=None):
        return 0 if parent is not None and parent.isValid() else len(self._entries)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not 0 <= index.row() < len(self._entries):
            return None
        entry = self._entries[index.row()]
        if role == Qt.ItemDataRole.DisplayRole:
            if entry.rows:
                return (f"{entry.title}\n{len(entry.fields)} fields · "
                        f"{sum(field.copies for field in entry.fields)} copies · {sum(field.types for field in entry.fields)} types")
            return f"{entry.title or '(untitled)'}\n{entry.status} · {len(entry.description):,} characters"
        if role == self.IdentityRole:
            return entry.id
        if role == self.SearchRole:
            return "\n".join([entry.title, *(field.title for field in entry.fields)])
        if role == Qt.ItemDataRole.ToolTipRole:
            return entry.title
        return None

    def sync(self) -> None:
        current = self.document.entries
        if current == self._entries:
            return
        if tuple(entry.id for entry in current) != tuple(entry.id for entry in self._entries):
            self.beginResetModel()
            self._entries = current
            self.endResetModel()
        else:
            self._entries = current
            self.dataChanged.emit(self.index(0), self.index(len(current) - 1))
