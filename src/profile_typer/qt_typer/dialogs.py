"""Paste a JSON queue without creating a file first."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QApplication, QComboBox, QDialog, QDialogButtonBox, QHBoxLayout,
    QLabel, QPlainTextEdit, QPushButton, QVBoxLayout,
)

from profile_typer.view_schema import parse_views


class PasteJsonDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Paste JSON queue")
        self.resize(560, 420)
        self.setMinimumSize(340, 320)
        layout = QVBoxLayout(self)
        instructions = QLabel("Paste a title/description queue or a document containing views and rows.")
        instructions.setWordWrap(True)
        layout.addWidget(instructions)
        self.editor = QPlainTextEdit()
        self.editor.setPlaceholderText('[\n  {"title": "hello", "description": "text to type out"}\n]')
        self.editor.setAccessibleName("JSON to import")
        layout.addWidget(self.editor, 1)
        row = QHBoxLayout()
        clipboard_button = QPushButton("Paste from clipboard")
        clipboard_button.clicked.connect(lambda: self.editor.insertPlainText(QApplication.clipboard().text()))
        row.addWidget(clipboard_button)
        self.mode = QComboBox()
        self.mode.addItem("Replace queue", False)
        self.mode.addItem("Append to queue", True)
        row.addWidget(self.mode, 1)
        layout.addLayout(row)
        self.error_label = QLabel()
        self.error_label.setWordWrap(True)
        self.error_label.setStyleSheet("color: #b42318;")
        layout.addWidget(self.error_label)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Import")
        self.buttons.accepted.connect(self._validate)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

    @property
    def source(self):
        return self.editor.toPlainText().lstrip("\ufeff")

    @property
    def append(self):
        return self.mode.currentData()

    def _validate(self):
        try:
            parse_views(self.source)
        except ValueError as error:
            self.error_label.setText(str(error))
            return
        self.accept()
