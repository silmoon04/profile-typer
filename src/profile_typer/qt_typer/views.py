"""Responsive field cards for JSON-authored views. No HTML is executed."""
from __future__ import annotations

import math
from functools import lru_cache

from PySide6.QtCore import Qt, Signal, QSignalBlocker, QTimer, QSize
from PySide6.QtGui import QColor, QPixmap, QIcon, QKeySequence, QTextOption
from PySide6.QtWidgets import (
    QWidget, QFrame, QLabel, QTextEdit, QVBoxLayout, QHBoxLayout, QGridLayout,
    QPushButton, QCheckBox, QRadioButton, QScrollArea, QMenu, QSizePolicy, QPlainTextEdit, QToolButton, QApplication,
)

from profile_typer.view_schema import COLORS
from .theme import ASSETS, MUTED


@lru_cache(maxsize=2)
def usage_icon(kind):
    pixmap = QPixmap(str(ASSETS / ("clipboard.png" if kind == "copy" else "pencil.png")))
    pixmap.setDevicePixelRatio(pixmap.width() / 18)
    return pixmap


class SelectableLabel(QLabel):
    copyRequested = Signal(str)
    activated = Signal()

    def __init__(self, text):
        super().__init__(text)
        self.setTextFormat(Qt.TextFormat.PlainText)
        self.setWordWrap(True)
        self.setMinimumWidth(0)
        self.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse | Qt.TextInteractionFlag.TextSelectableByKeyboard)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def mousePressEvent(self, event):
        self._press_position = event.position()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        if (event.button() == Qt.MouseButton.LeftButton and not self.hasSelectedText()
                and (event.position() - self._press_position).manhattanLength() < 4):
            self.activated.emit()

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
        available = self.width()
        ancestor = self.parentWidget()
        while ancestor is not None:
            if isinstance(ancestor, QScrollArea):
                available = min(available, ancestor.viewport().width() - 4)
                break
            ancestor = ancestor.parentWidget()
        columns = max(1, min(self.columns, (available + 8) // (self.minimum + 8)))
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
        self._syncing = False
        self._copies = 0
        self.setObjectName("field-card")
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(8)
        header = QHBoxLayout()
        header.setSpacing(8)
        title_column = QVBoxLayout()
        title_column.setSpacing(0)
        self.title_label = SelectableLabel(field.title)
        font = self.title_label.font()
        font.setBold(True)
        self.title_label.setFont(font)
        policy = self.title_label.sizePolicy()
        policy.setHorizontalPolicy(QSizePolicy.Policy.Ignored)
        self.title_label.setSizePolicy(policy)
        self.title_label.copyRequested.connect(lambda text: copied(field.id, text))
        title_column.addWidget(self.title_label)
        self.status_label = QLabel(self)
        self.status_label.setWordWrap(True)
        title_column.addWidget(self.status_label)
        header.addLayout(title_column, 1)
        self.copy_button = QPushButton(self)
        self.copy_button.setIcon(QIcon(str(ASSETS / "clipboard.png")))
        self.copy_button.setIconSize(QSize(16, 16))
        self.copy_button.clicked.connect(lambda: copied(field.id, None))
        self.copy_button.setVisible("copy" in field.actions)
        self.type_button = QPushButton(self)
        self.type_button.setIcon(QIcon(str(ASSETS / "pencil-light.png")))
        self.type_button.setIconSize(QSize(16, 16))
        self.type_button.setObjectName("primary")
        self.type_button.clicked.connect(lambda: typed(field.id))
        self.type_button.setVisible("type" in field.actions)
        header.addWidget(self.copy_button, 0, Qt.AlignmentFlag.AlignTop)
        header.addWidget(self.type_button, 0, Qt.AlignmentFlag.AlignTop)
        layout.addLayout(header)
        self._copy_feedback = QTimer(self)
        self._copy_feedback.setSingleShot(True)
        self._copy_feedback.timeout.connect(lambda: self.copy_button.setText(f"Copy {self._copies}"))
        self.option_buttons = []
        self.option_labels = []
        self.option_grid = None
        if field.options:
            short_options = all(len(option) <= 12 for option in field.options)
            self.option_grid = ResponsiveRow(field.option_columns, minimum=72 if short_options else 165)
            for index, option in enumerate(field.options):
                row = QWidget()
                option_layout = QHBoxLayout(row)
                option_layout.setContentsMargins(0, 2, 0, 2)
                option_layout.setSpacing(4)
                button = QCheckBox() if field.multiple else QRadioButton()
                if isinstance(button, QRadioButton):
                    button.setAutoExclusive(False)
                button.setAccessibleName(option)
                button.clicked.connect(lambda checked, index=index: selected(field.id, index, checked))
                label = SelectableLabel(option)
                label.copyRequested.connect(lambda text: copied(field.id, text))
                label.activated.connect(button.click)
                label.setCursor(Qt.CursorShape.PointingHandCursor)
                option_layout.addWidget(button, 0, Qt.AlignmentFlag.AlignTop)
                option_layout.addWidget(label, 1)
                self.option_buttons.append(button)
                self.option_labels.append(label)
                self.option_grid.add(row)
            self.selected_label = QLabel(self)
            self.selected_label.setObjectName("eyebrow")
            self.edit_answer_button = QToolButton(self)
            self.edit_answer_button.setText("Custom text")
            self.edit_answer_button.setObjectName("quiet")
            self.edit_answer_button.setToolTip("Edit the answer as text instead of choosing an option.")
            self.edit_answer_button.setCheckable(True)
            self.edit_answer_button.setChecked(bool(field.text))
            option_line = QHBoxLayout()
            option_line.setSpacing(8)
            if field.multiple:
                layout.addWidget(self.option_grid)
                option_line.addWidget(self.selected_label, 1)
            else:
                option_line.addWidget(self.option_grid, 1)
            option_line.addWidget(self.edit_answer_button, 0, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            layout.addLayout(option_line)
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
        self.sync(field, busy=False)

    def show_copy_feedback(self):
        self.copy_button.setText(f"Copied {self._copies}")
        self._copy_feedback.start(1000)

    def set_active(self, active):
        if self.property("active") != active:
            self.setProperty("active", active)
            self.style().unpolish(self)
            self.style().polish(self)
            self.update()

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
                self.selected_label.setText(f"{len(field.selected)} selected")
                self.selected_label.setVisible(field.multiple)
                self.edit_answer_button.setEnabled(not busy)
            self.editor.setReadOnly(busy)
            self._copies = field.copies
            self.copy_button.setText(f"{'Copied' if self._copy_feedback.isActive() else 'Copy'} {field.copies}")
            self.type_button.setText(f"Type {field.types}")
            self.copy_button.setFixedWidth(max(96, self.copy_button.fontMetrics().horizontalAdvance(f"Copied {field.copies}") + 36))
            self.type_button.setFixedWidth(max(92, self.type_button.fontMetrics().horizontalAdvance(f"Type {field.types}") + 36))
            self.copy_button.setToolTip(f"{field.copies} copy actions. Copy the full answer; selected text can also be copied.")
            self.type_button.setToolTip(f"{field.types} typing starts. Latest status: {field.status}.")
            self.copy_button.setAccessibleName(f"Copy {field.title}: {field.copies} copies")
            self.type_button.setAccessibleName(f"Type {field.title}: {field.types} starts")
            self.copy_button.setEnabled(not busy and bool(field.value))
            self.type_button.setEnabled(not busy and bool(field.value))
            self.status_label.setText(field.status)
            self.status_label.setVisible(field.status != "Ready")
            self.status_label.setStyleSheet(f"color: {'#8a4b17' if field.status == 'Edited' else MUTED}; font-size: 11px;")
            self.status_label.setToolTip("Edited means the answer changed after an earlier action. Counts are action totals.")
            color = field.color
            if color is None and field.options and len(field.selected) == 1:
                color = {"yes": "green", "pass": "green", "no": "red", "fail": "red", "partial": "amber"}.get(field.selected[0].lower())
            accent = QColor(COLORS.get(color or self.view_color or "blue", color or self.view_color or "#2563eb"))
            wash = QColor(*(round(component * 0.09 + 255 * 0.91) for component in (accent.red(), accent.green(), accent.blue())))
            self.setStyleSheet(
                "QFrame#field-card { border: 1px solid #b2b9a6; border-radius: 2px; background: #fffef9; }"
                f"QFrame#field-card:hover, QFrame#field-card[active=\"true\"] {{ border-color: #626b53; background: {wash.name()}; }}"
                "QTextEdit#field-value { background: transparent; border: 0; padding: 2px 0; }")
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
        self._cached_views = {}
        QApplication.instance().focusChanged.connect(self._focus_changed)

    def _focus_changed(self, _previous, current):
        for card in self.cards.values():
            card.set_active(current is not None and (current is card or card.isAncestorOf(current)))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        for row in self.rows:
            row.reflow()

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
                previous.hide()
                previous.setParent(self)
                self._cached_views[self.view_id] = (self.layout_key, previous, self.cards, self.rows)
            cached = self._cached_views.pop(entry.id, None)
            if cached is not None and cached[0] == layout_key:
                _, body, self.cards, self.rows = cached
            else:
                if cached is not None:
                    cached[1].deleteLater()
                body = QWidget(self)
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
            while len(self._cached_views) > 4:
                oldest = next(iter(self._cached_views))
                self._cached_views.pop(oldest)[1].deleteLater()
            self.setWidget(body)
            self.view_id = entry.id
            self.layout_key = layout_key
            QTimer.singleShot(0, self, lambda: self.verticalScrollBar().setValue(self.scroll_positions.get(entry.id, 0))
                              if self.view_id == entry.id else None)
        for field in entry.fields:
            self.cards[field.id].sync(field, busy=busy)
        self._focus_changed(None, QApplication.focusWidget())
