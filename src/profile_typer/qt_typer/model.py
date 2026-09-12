"""Qt list adapter; the document owns the queue and item identities."""
from __future__ import annotations

from PySide6.QtCore import QAbstractListModel, Qt, QSize, QPoint
from PySide6.QtGui import QColor, QPen
from PySide6.QtWidgets import QStyledItemDelegate, QStyle
from .theme import INK, ACCENT, MUTED, mono_font

from profile_typer.typing_document import TypingDocument


class QueueModel(QAbstractListModel):
    IdentityRole = int(Qt.ItemDataRole.UserRole) + 1
    SearchRole = IdentityRole + 1
    TitleRole = SearchRole + 1
    SummaryRole = TitleRole + 1
    PositionRole = SummaryRole + 1

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
        if role == self.TitleRole:
            return entry.title or "Untitled"
        if role == self.PositionRole:
            return index.row() + 1
        if role == self.SummaryRole:
            if entry.rows:
                used = sum(bool(field.copies or field.types) for field in entry.fields)
                return f"{used} / {len(entry.fields)} used" if used else f"{len(entry.fields)} fields"
            return f"{entry.status} · {len(entry.description):,} characters"
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


class QueueDelegate(QStyledItemDelegate):
    def sizeHint(self, option, index):
        return QSize(180, 56 if self.parent().window().height() < 540 else 64)

    def paint(self, painter, option, index):
        painter.save()
        rect = option.rect.adjusted(0, 2, -7, -3)
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        hover = bool(option.state & QStyle.StateFlag.State_MouseOver)
        painter.fillRect(rect, QColor(ACCENT if selected else "#e8ecdf" if hover else "#f4f2e9"))
        if selected:
            painter.setPen(QPen(QColor(INK), 1))
            painter.drawRect(rect.adjusted(0, 0, -1, -1))
        font = option.font
        font.setBold(True)
        painter.setFont(font)
        baseline = rect.y() + 10 + painter.fontMetrics().ascent()
        painter.setPen(QColor(MUTED))
        painter.setFont(mono_font(9))
        painter.drawText(QPoint(rect.x() + 10, baseline), f"{index.data(QueueModel.PositionRole):02d}")
        painter.setFont(font)
        painter.setPen(QColor(INK))
        title = painter.fontMetrics().elidedText(index.data(QueueModel.TitleRole), Qt.TextElideMode.ElideRight, max(0, rect.width() - 55))
        painter.drawText(QPoint(rect.x() + 42, baseline), title)
        font.setBold(False)
        font.setPointSize(9)
        painter.setFont(font)
        painter.setPen(QColor(MUTED))
        summary = painter.fontMetrics().elidedText(index.data(QueueModel.SummaryRole), Qt.TextElideMode.ElideRight, max(0, rect.width() - 55))
        painter.drawText(QPoint(rect.x() + 42, baseline + 20), summary)
        painter.restore()
