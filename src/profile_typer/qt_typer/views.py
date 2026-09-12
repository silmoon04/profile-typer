"""Responsive field cards for JSON-authored views. No HTML is executed."""
from __future__ import annotations

import math
from functools import lru_cache

from PySide6.QtCore import Qt, Signal, QSignalBlocker, QTimer
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap, QKeySequence, QTextOption
from PySide6.QtWidgets import (
    QWidget, QFrame, QLabel, QTextEdit, QVBoxLayout, QHBoxLayout, QGridLayout,
    QPushButton, QCheckBox, QRadioButton, QScrollArea, QMenu, QSizePolicy, QPlainTextEdit,
)

from profile_typer.view_schema import COLORS


@lru_cache(maxsize=2)
def usage_icon(kind):
    pixmap = QPixmap(18, 18)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(QPen(QColor("#526175"), 1.5))
    if kind == "copy":
        painter.drawRoundedRect(4, 4, 11, 12, 2, 2)
        painter.drawRoundedRect(7, 2, 5, 4, 1, 1)
    else:
        painter.drawLine(4, 12, 12, 4)
        painter.drawLine(7, 15, 15, 7)
        painter.drawLine(12, 4, 15, 7)
        painter.drawLine(4, 12, 3, 16)
        painter.drawLine(3, 16, 7, 15)
    painter.end()
    return pixmap


class SelectableLabel(QLabel):
    copyRequested = Signal(str)

    def __init__(self, text):
        super().__init__(text)
        self.setTextFormat(Qt.TextFormat.PlainText)
        self.setWordWrap(True)
        self.setMinimumWidth(0)
        self.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse | Qt.TextInteractionFlag.TextSelectableByKeyboard)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def keyPressEvent(self, event):
        if event.matches(QKeySequence.StandardKey.Copy) and self.hasSelectedText():
            self.copyRequested.emit(self.selectedText())
            event.accept()
        else:
            super().keyPressEvent(event)

    def contextMenuEvent(self, event):
        menu = QMenu(self)
        action = menu.addAction("Copy selection", lambda: self.copyRequested.emit(self.selectedText()))
        action.setEnabled(self.hasSelectedText())
        menu.exec(event.globalPos())


class FieldTextEdit(QTextEdit):
    copyRequested = Signal(str)
    cursorMoved = Signal()

    def __init__(self):
        super().__init__()
        self.setAcceptRichText(False)
        self.setObjectName("field-value")
        self.setWordWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.document().setDocumentMargin(4)
        self.document().documentLayout().documentSizeChanged.connect(self._fit)
        self.cursorPositionChanged.connect(lambda: self.cursorMoved.emit() if self.hasFocus() else None)

    def _fit(self, *_args):
        extra = max(2, self.height() - self.viewport().height())
        height = max(34, math.ceil(self.document().size().height()) + extra)
        if self.height() != height:
            self.setFixedHeight(height)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        QTimer.singleShot(0, self, self._fit)

    def copy_selection(self):
        cursor = self.textCursor()
        if cursor.hasSelection():
            self.copyRequested.emit(cursor.selectedText().replace("\u2029", "\n"))

    def keyPressEvent(self, event):
        if event.matches(QKeySequence.StandardKey.Copy):
            self.copy_selection()
            event.accept()
        else:
            super().keyPressEvent(event)

    def contextMenuEvent(self, event):
        menu = QMenu(self)
        for title, callback, enabled in (
            ("Undo", self.undo, self.document().isUndoAvailable()),
            ("Redo", self.redo, self.document().isRedoAvailable()),
            ("Cut", self.cut, self.textCursor().hasSelection()),
            ("Copy", self.copy_selection, self.textCursor().hasSelection()),
            ("Paste", self.paste, self.canPaste()),
            ("Select all", self.selectAll, bool(self.toPlainText())),
        ):
            menu.addAction(title, callback).setEnabled(enabled)
        menu.exec(event.globalPos())


class LegacyTextEdit(QPlainTextEdit):
    copyRequested = Signal(str)

    def copy_selection(self):
        cursor = self.textCursor()
        if cursor.hasSelection():
            self.copyRequested.emit(cursor.selectedText().replace("\u2029", "\n"))

    def keyPressEvent(self, event):
        if event.matches(QKeySequence.StandardKey.Copy):
            self.copy_selection()
            event.accept()
        else:
            super().keyPressEvent(event)

    contextMenuEvent = FieldTextEdit.contextMenuEvent


class ResponsiveRow(QWidget):
    def __init__(self, columns, *, minimum=245):
        super().__init__()
        self.columns = columns
        self.minimum = minimum
        self.items = []
        self.effective_columns = 0
        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setSpacing(8)

    def add(self, widget):
        self.items.append(widget)
        self.grid.addWidget(widget)
        self.reflow(force=True)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.reflow()

    def reflow(self, *, force=False):
        columns = max(1, min(self.columns, (self.width() + 8) // (self.minimum + 8)))
        if columns == self.effective_columns and not force:
            return
        self.effective_columns = columns
        for i in range(4):
            self.grid.setColumnStretch(i, 1 if i < columns else 0)
            self.grid.setColumnMinimumWidth(i, 0)
        for index, widget in enumerate(self.items):
            self.grid.addWidget(widget, index // columns, index % columns, Qt.AlignmentFlag.AlignTop)


class FieldCard(QFrame):
    def __init__(self, field, view_color, *, edited, selected, copied, typed, cursor_visible):
        super().__init__()
        self.field_id = field.id
        self.view_color = view_color
        self.copied = copied
        self._syncing = False
        self.setObjectName("field-card")
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(6)
        self.title_label = SelectableLabel(field.title)
        font = self.title_label.font()
        font.setBold(True)
        self.title_label.setFont(font)
        self.title_label.copyRequested.connect(lambda text: copied(field.id, text))
        layout.addWidget(self.title_label)
        self.option_buttons = []
        self.option_labels = []
        self.option_grid = None
        if field.options:
            self.option_grid = ResponsiveRow(field.option_columns, minimum=165)
            for index, option in enumerate(field.options):
                row = QWidget()
                option_layout = QHBoxLayout(row)
                option_layout.setContentsMargins(0, 2, 0, 2)
                button = QCheckBox() if field.multiple else QRadioButton()
                if isinstance(button, QRadioButton):
                    button.setAutoExclusive(False)
                button.setAccessibleName(option)
                button.clicked.connect(lambda checked, index=index: selected(field.id, index, checked))
                label = SelectableLabel(option)
                label.copyRequested.connect(lambda text: copied(field.id, text))
                option_layout.addWidget(button, 0, Qt.AlignmentFlag.AlignTop)
                option_layout.addWidget(label, 1)
                self.option_buttons.append(button)
                self.option_labels.append(label)
                self.option_grid.add(row)
            layout.addWidget(self.option_grid)
            self.selected_label = QLabel()
            layout.addWidget(self.selected_label)
            self.edit_answer_button = QPushButton("Edit answer text")
            self.edit_answer_button.setCheckable(True)
            self.edit_answer_button.setChecked(bool(field.text))
            layout.addWidget(self.edit_answer_button, 0, Qt.AlignmentFlag.AlignLeft)
        self.editor = FieldTextEdit()
        self.editor.setAccessibleName(field.title)
        self.editor.setPlaceholderText("Enter an answer…")
        self.editor.textChanged.connect(lambda: edited(field.id, self.editor.toPlainText()) if not self._syncing else None)
        self.editor.copyRequested.connect(lambda text: copied(field.id, text))
        self.editor.cursorMoved.connect(lambda: cursor_visible(self.editor))
        layout.addWidget(self.editor)
        if field.options:
            self.editor.setVisible(bool(field.text))
            self.edit_answer_button.toggled.connect(self.editor.setVisible)
        footer = QHBoxLayout()
        self.copy_count = QLabel()
        self.type_count = QLabel()
        for kind, label in (("copy", self.copy_count), ("type", self.type_count)):
            icon = QLabel()
            icon.setPixmap(usage_icon(kind))
            footer.addWidget(icon)
            footer.addWidget(label)
        self.copy_count.setToolTip("Copy actions for this field, including copied selections.")
        self.type_count.setToolTip("Typing runs started. Check the status for completion or cancellation.")
        self.status_label = QLabel()
        self.status_label.setMinimumWidth(0)
        self.status_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        footer.addWidget(self.status_label, 1)
        self.copy_button = QPushButton("Copy")
        self.copy_button.clicked.connect(lambda: copied(field.id, None))
        self.copy_button.setVisible("copy" in field.actions)
        self.type_button = QPushButton("Type")
        self.type_button.clicked.connect(lambda: typed(field.id))
        self.type_button.setVisible("type" in field.actions)
        footer.addWidget(self.copy_button)
        footer.addWidget(self.type_button)
        layout.insertLayout(1, footer)
        self.sync(field, busy=False)

    def sync(self, field, *, busy):
        self._syncing = True
        try:
            if self.editor.toPlainText() != field.value:
                self.editor.setPlainText(field.value)
                if field.options and field.text:
                    self.edit_answer_button.setChecked(True)
            for option, button in zip(field.options, self.option_buttons, strict=True):
                blocker = QSignalBlocker(button)
                button.setChecked(option in field.selected)
                button.setEnabled(not busy)
                del blocker
            if field.options:
                prefix = "Custom text; " if field.text else ""
                self.selected_label.setText(f"{prefix}{len(field.selected)} / {len(field.options)} selected")
                self.edit_answer_button.setEnabled(not busy)
            self.editor.setReadOnly(busy)
            self.copy_button.setEnabled(not busy and bool(field.value))
            self.type_button.setEnabled(not busy and bool(field.value))
            self.copy_count.setText(str(field.copies))
            self.type_count.setText(str(field.types))
            self.status_label.setText(field.status)
            self.status_label.setStyleSheet("color: #9a6700;" if field.status == "Edited" else "color: #526175;")
            self.status_label.setToolTip("Edited means the answer changed after an earlier action. Counts are action totals.")
            color = field.color
            if color is None and field.options and len(field.selected) == 1:
                color = {"yes": "green", "pass": "green", "no": "red", "fail": "red", "partial": "amber"}.get(field.selected[0].lower())
            accent = QColor(COLORS.get(color or self.view_color or "blue", color or self.view_color or "#2563eb"))
            wash = QColor(*(round(component * 0.06 + 255 * 0.94) for component in (accent.red(), accent.green(), accent.blue())))
            self.setStyleSheet(f"QFrame#field-card {{ border: 1px solid #d6deea; border-left: 3px solid {accent.name()}; border-radius: 5px; background: {wash.name()}; }}")
        finally:
            self._syncing = False


class ViewEditor(QScrollArea):
    def __init__(self, document, *, changed, copy_field, type_field):
        super().__init__()
        self.document = document
        self.changed = changed
        self.copy_field = copy_field
        self.type_field = type_field
        self.cards = {}
        self.rows = []
        self.view_id = None
        self.layout_key = None
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.scroll_positions = {}

    def _edit(self, field_id, text):
        self.document.update_field(field_id, text)
        self.changed()

    def _select(self, field_id, index, checked):
        field = self.document.field(field_id)
        self.document.select_option(field_id, field.options[index], checked)
        self.changed()

    def _show_cursor(self, editor):
        point = editor.viewport().mapTo(self.widget(), editor.cursorRect().bottomLeft())
        self.ensureVisible(point.x(), point.y(), 15, 25)

    def sync(self, entry, *, busy):
        layout_key = (entry.id, entry.color, tuple(
            (row.columns, tuple((field.id, field.title, field.options, field.multiple,
                                 field.option_columns, field.actions) for field in row.fields))
            for row in entry.rows))
        if layout_key != self.layout_key:
            if self.view_id is not None:
                self.scroll_positions[self.view_id] = self.verticalScrollBar().value()
            previous = self.takeWidget()
            if previous is not None:
                previous.deleteLater()
            body = QWidget()
            layout = QVBoxLayout(body)
            layout.setContentsMargins(0, 0, 4, 0)
            layout.setSpacing(10)
            self.cards = {}
            self.rows = []
            for row in entry.rows:
                row_widget = ResponsiveRow(row.columns)
                for field in row.fields:
                    card = FieldCard(field, entry.color, edited=self._edit, selected=self._select,
                                     copied=self.copy_field, typed=self.type_field, cursor_visible=self._show_cursor)
                    self.cards[field.id] = card
                    row_widget.add(card)
                self.rows.append(row_widget)
                layout.addWidget(row_widget)
            layout.addStretch(1)
            self.setWidget(body)
            self.view_id = entry.id
            self.layout_key = layout_key
            QTimer.singleShot(0, self, lambda: self.verticalScrollBar().setValue(self.scroll_positions.get(entry.id, 0))
                              if self.view_id == entry.id else None)
        for field in entry.fields:
            self.cards[field.id].sync(field, busy=busy)
