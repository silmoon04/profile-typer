"""Desktop views and user actions. Typing and document rules live outside Qt."""
from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

from PySide6.QtCore import QItemSelectionModel, QSettings, QSignalBlocker, QSortFilterProxyModel, Qt, QTimer
from PySide6.QtGui import QAction, QCloseEvent, QKeySequence
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
    QDoubleSpinBox, QFileDialog, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
    QListView, QMainWindow, QMenu, QMessageBox, QPlainTextEdit, QProgressBar,
    QPushButton, QScrollArea, QSizePolicy, QSplitter, QStackedWidget, QTabBar,
    QToolButton, QVBoxLayout, QWidget,
)

from profile_typer.typing_backends import PreviewTypingBackend, default_backend
from profile_typer.typing_document import TypingDocument
from profile_typer.view_schema import parse_views, COLORS
from profile_typer.profiles import recorded_profile
from profile_typer.typing_session import Phase, TypingSession, TypingSettings
from .model import QueueModel
from .dialogs import PasteJsonDialog
from .views import ViewEditor, LegacyTextEdit, usage_icon


class PreciseSpinBox(QDoubleSpinBox):
    def wheelEvent(self, event):
        if self.hasFocus():
            super().wheelEvent(event)
        else:
            event.ignore()


class TyperWindow(QMainWindow):
    def __init__(self, *, document=None, backend=None, preferences: QSettings | None = None):
        super().__init__()
        self.document = document if document is not None else TypingDocument()
        self.backend = backend if backend is not None else default_backend()
        self.session = TypingSession(self.document, self.backend)
        self.preferences = preferences
        self._refreshing = False
        self._compact: bool | None = None
        self._closing_requested = False
        self._shown_id: str | None = None
        self.setWindowTitle("Profile Typer")
        self.setMinimumSize(360, 400)
        self.resize(1000, 720)
        self._build_ui()
        self._restore_preferences()
        self.refresh_windows()
        self.refresh()
        self.timer = QTimer(self)
        self.timer.setInterval(30)
        self.timer.timeout.connect(self._tick)
        self.timer.start()

    def _button(self, text, callback, *, editing=True):
        button = QPushButton(text)
        button.clicked.connect(callback)
        if editing:
            self.edit_controls.append(button)
        return button

    def _build_ui(self):
        self.edit_controls = []
        page = QWidget()
        self.setCentralWidget(page)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(10, 6, 10, 6)
        layout.setSpacing(4)
        toolbar = QHBoxLayout()
        toolbar.addWidget(self._button("Open…", self.open_json))
        toolbar.addWidget(self._button("Save…", self.save_json))
        self.paste_button = self._button("Paste JSON", self.paste_json)
        toolbar.addWidget(self.paste_button)
        more = QToolButton()
        more.setText("More")
        more.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu = QMenu(more)
        menu.addAction("Append JSON…", lambda: self.open_json(append=True))
        menu.addAction("JSON format", self.show_format)
        menu.addSeparator()
        menu.addAction("Diagnostics", self.show_diagnostics)
        menu.addAction("Use recorded profile defaults", self._use_recorded_defaults)
        menu.addAction("Reset counters in this view", self.reset_usage)
        if isinstance(self.backend, PreviewTypingBackend):
            menu.addAction("Preview output", lambda: self._show_text("Preview output", self.backend.output))
        more.setMenu(menu)
        toolbar.addWidget(more)
        self.file_label = QLabel()
        self.file_label.setMinimumWidth(0)
        self.file_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.file_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        toolbar.addWidget(self.file_label, 1)
        layout.addLayout(toolbar)
        if isinstance(self.backend, PreviewTypingBackend):
            self.preview_label = QLabel("Preview mode · no keystrokes are sent")
            self.preview_label.setObjectName("preview")
            layout.addWidget(self.preview_label)
        self.tabs = QTabBar()
        self.tabs.addTab("Queue and description")
        self.tabs.addTab("Queue")
        self.tabs.addTab("Settings")
        self.tabs.setExpanding(True)
        self.tabs.currentChanged.connect(self._switch_page)
        layout.addWidget(self.tabs)
        self.pages = QStackedWidget()
        self.pages.setMinimumSize(0, 0)
        self.pages.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Ignored)
        layout.addWidget(self.pages, 1)
        self.write_page = QWidget()
        write_layout = QVBoxLayout(self.write_page)
        write_layout.setContentsMargins(0, 0, 0, 0)
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setChildrenCollapsible(False)
        self.queue_panel = self._build_queue()
        self.editor_panel = self._build_editor()
        self.splitter.addWidget(self.queue_panel)
        self.splitter.addWidget(self.editor_panel)
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setSizes([260, 700])
        write_layout.addWidget(self.splitter)
        self.pages.addWidget(self.write_page)
        self.queue_page = QWidget()
        self.queue_layout = QVBoxLayout(self.queue_page)
        self.queue_layout.setContentsMargins(0, 0, 0, 0)
        self.pages.addWidget(self.queue_page)
        self.settings_page = self._build_settings()
        self.pages.addWidget(self.settings_page)
        self.quick_controls = QWidget()
        self.quick_grid = QGridLayout(self.quick_controls)
        self.quick_grid.setContentsMargins(0, 0, 0, 0)
        self.quick_grid.setHorizontalSpacing(10)
        self.quick_grid.setVerticalSpacing(4)
        self.quick_fields = []
        for name, label in (("wpm", "WPM"), ("delay", "Delay (s)"),
                            ("corrections", "Corrections"), ("variation", "Variation %")):
            field = QWidget()
            field_layout = QHBoxLayout(field)
            field_layout.setContentsMargins(0, 0, 0, 0)
            field_layout.setSpacing(4)
            field_layout.addWidget(QLabel(label), 1)
            self.spins[name].setMaximumWidth(84)
            field_layout.addWidget(self.spins[name])
            self.quick_fields.append(field)
        self._quick_columns = None
        layout.addWidget(self.quick_controls)
        self._layout_quick_controls()
        destination = QHBoxLayout()
        destination.addWidget(QLabel("To"))
        self.target_combo = QComboBox()
        self.target_combo.setMinimumWidth(0)
        self.target_combo.setMinimumContentsLength(1)
        self.target_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.edit_controls.append(self.target_combo)
        destination.addWidget(self.target_combo, 1)
        destination.addWidget(self._button("Refresh", self.refresh_windows))
        layout.addLayout(destination)
        controls = QHBoxLayout()
        self.copy_button = self._button("Copy", self.copy_description)
        controls.addWidget(self.copy_button)
        self.start_button = self._button("Type description", self.start_typing)
        self.start_button.setObjectName("primary")
        self.stop_button = self._button("Stop (Esc)", self.stop_typing, editing=False)
        controls.addWidget(self.start_button)
        controls.addWidget(self.stop_button)
        self.progress = QProgressBar()
        self.progress.setRange(0, 1000)
        self.progress.setTextVisible(False)
        self.progress.setMinimumWidth(20)
        controls.addWidget(self.progress, 1)
        layout.addLayout(controls)
        self.status_label = QLabel()
        self.status_label.setMinimumWidth(0)
        self.status_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.status_label.setFixedHeight(self.fontMetrics().height() + 6)
        layout.addWidget(self.status_label)
        for shortcut, callback in (("Ctrl+O", self.open_json), ("Ctrl+S", self.save_json),
                                    ("Ctrl+Shift+V", self.paste_json),
                                    ("Alt+Left", lambda: self.navigate(-1)), ("Alt+Right", lambda: self.navigate(1)),
                                    ("Escape", self.stop_typing)):
            action = QAction(self)
            action.setShortcut(QKeySequence(shortcut))
            action.triggered.connect(callback)
            self.addAction(action)

    def _build_queue(self):
        panel = QWidget()
        panel.setMinimumWidth(0)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search titles…")
        self.search.setClearButtonEnabled(True)
        layout.addWidget(self.search)
        self.model = QueueModel(self.document, self)
        self.proxy = QSortFilterProxyModel(self)
        self.proxy.setSourceModel(self.model)
        self.proxy.setFilterRole(QueueModel.SearchRole)
        self.proxy.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.list_view = QListView()
        self.list_view.setModel(self.proxy)
        self.list_view.setMinimumSize(0, 30)
        self.list_view.setUniformItemSizes(True)
        self.list_view.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.list_view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.list_view.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.list_view.selectionModel().currentChanged.connect(self._select_item)
        self.list_view.activated.connect(lambda _index: self.tabs.setCurrentIndex(0))
        self.list_view.doubleClicked.connect(lambda _index: self.tabs.setCurrentIndex(0))
        self.search.textChanged.connect(self._filter)
        self.edit_controls.append(self.list_view)
        self.edit_controls.append(self.search)
        layout.addWidget(self.list_view, 1)
        row = QHBoxLayout()
        self.add_button = self._button("Add", self.add_item)
        row.addWidget(self.add_button)
        row.addWidget(self._button("Duplicate", lambda: self.add_item(duplicate=True)))
        row.addWidget(self._button("Remove", self.remove_item))
        layout.addLayout(row)
        row = QHBoxLayout()
        self.up_button = self._button("Move up", lambda: self.move_item(-1))
        self.down_button = self._button("Move down", lambda: self.move_item(1))
        row.addWidget(self.up_button)
        row.addWidget(self.down_button)
        layout.addLayout(row)
        return panel

    def _build_editor(self):
        panel = QWidget()
        panel.setMinimumSize(0, 0)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        row = QHBoxLayout()
        self.back_button = self._button("← Back", lambda: self.navigate(-1))
        self.next_button = self._button("Next →", lambda: self.navigate(1))
        self.position_label = QLabel()
        self.position_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        row.addWidget(self.back_button)
        row.addWidget(self.position_label, 1)
        row.addWidget(self.next_button)
        layout.addLayout(row)
        self.title_edit = QLineEdit()
        self.title_edit.setPlaceholderText("Item title (not typed)")
        self.title_edit.setAccessibleName("Item title")
        self.title_edit.textEdited.connect(self._edit)
        layout.addWidget(self.title_edit)
        self.content_stack = QStackedWidget()
        self.content_stack.setMinimumSize(0, 0)
        self.legacy_editor = QWidget()
        legacy_layout = QVBoxLayout(self.legacy_editor)
        legacy_layout.setContentsMargins(0, 0, 0, 0)
        legacy_layout.setSpacing(2)
        self.description_edit = LegacyTextEdit()
        self.description_edit.setPlaceholderText("Enter the description to type…")
        self.description_edit.setAccessibleName("Description to type")
        self.description_edit.setMinimumSize(0, 50)
        self.description_edit.setTabChangesFocus(False)
        self.description_edit.textChanged.connect(self._edit)
        self.description_edit.copyRequested.connect(lambda text: self.copy_field(self.document.selected.id, text))
        legacy_layout.addWidget(self.description_edit, 1)
        self.stats_label = QLabel()
        self.stats_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        stats = QHBoxLayout()
        stats.setSpacing(4)
        stats.addWidget(self.stats_label, 1)
        self.legacy_copies = QLabel()
        self.legacy_types = QLabel()
        for kind, counter in (("copy", self.legacy_copies), ("type", self.legacy_types)):
            icon = QLabel()
            icon.setPixmap(usage_icon(kind))
            stats.addWidget(icon)
            stats.addWidget(counter)
        self.legacy_copies.setToolTip("Copy actions")
        self.legacy_types.setToolTip("Typing runs started")
        legacy_layout.addLayout(stats)
        self.content_stack.addWidget(self.legacy_editor)
        self.view_editor = ViewEditor(self.document, changed=self.refresh, copy_field=self.copy_field, type_field=self.type_field)
        self.content_stack.addWidget(self.view_editor)
        layout.addWidget(self.content_stack, 1)
        self.edit_controls.extend([self.title_edit, self.description_edit])
        return panel

    def _build_settings(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setContentsMargins(6, 8, 10, 8)
        profile = recorded_profile()
        summary = profile.timing["summary"]
        label = QLabel(f"Profile: {profile.name}\n{summary['interval_samples']:,} intervals · "
                       f"{summary['digraphs_modelled']} key pairs · {summary['dwell_samples']:,} hold times")
        label.setWordWrap(True)
        layout.addWidget(label)
        self.spins = {}
        for name, label, low, high, step, value in (
            ("wpm", "Speed (WPM)", 15, 120, 0.5, profile.natural_wpm),
            ("delay", "Start delay (seconds)", 0, 60, 0.5, 3),
            ("corrections", "Corrections (0–2×)", 0, 2, 0.05, 1),
            ("variation", "Variation (%)", 0, 150, 1, 100),
        ):
            spin = PreciseSpinBox()
            spin.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
            spin.setRange(low, high)
            spin.setSingleStep(step)
            spin.setDecimals(2 if name == "corrections" else 1)
            spin.setValue(value)
            spin.setKeyboardTracking(False)
            spin.valueChanged.connect(self._settings_changed)
            self.spins[name] = spin
            self.edit_controls.append(spin)
            spin.setAccessibleName(label)
            spin.setToolTip(label)
        help_text = QLabel(f"Corrections: 1× uses the recorded rate ({profile.mistakes.correction_runs_per_character:.1%} correction runs per character). "
                          "0 disables corrections. Variation 100% uses the measured timing spread.")
        help_text.setWordWrap(True)
        layout.addWidget(help_text)
        self.advance_check = QCheckBox("Select the next item when done")
        self.advance_check.setChecked(True)
        self.advance_check.toggled.connect(self._settings_changed)
        self.edit_controls.append(self.advance_check)
        layout.addWidget(self.advance_check)
        self.topmost_check = QCheckBox("Keep on top")
        self.topmost_check.toggled.connect(self._set_topmost)
        layout.addWidget(self.topmost_check)
        hint = QLabel(getattr(self.backend, "desktop_note", "Click the destination text field during the countdown.") + "\n\n"
                      "Each description starts manually. Starting a stopped item types it from the beginning.")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        layout.addStretch(1)
        scroll.setWidget(body)
        return scroll

    def _filter(self, text):
        self._refreshing = True
        self.proxy.setFilterFixedString(text)
        self._refreshing = False
        self.refresh()

    def _select_item(self, current, _previous):
        if self._refreshing or self.session.busy or not current.isValid():
            return
        self.document.select(current.data(QueueModel.IdentityRole))
        self.refresh()

    def _edit(self, *_args):
        if not self._refreshing and not self.session.busy:
            self.document.update(self.title_edit.text(), self.description_edit.toPlainText())
            self.refresh()

    def _settings(self):
        for spin in self.spins.values():
            spin.interpretText()
        return TypingSettings(**{name: spin.value() for name, spin in self.spins.items()}, advance=self.advance_check.isChecked())

    def _settings_changed(self, *_args):
        if hasattr(self, "status_label"):
            self.refresh()
        if self.preferences is not None and hasattr(self, "advance_check"):
            for name, spin in self.spins.items():
                self.preferences.setValue(name, spin.value())
            self.preferences.setValue("advance", self.advance_check.isChecked())
            self.preferences.setValue("cadence_profile_id", recorded_profile().id)

    def _set_topmost(self, checked):
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, checked)
        self.show()

    def _restore_preferences(self):
        if self.preferences is None:
            return
        profile = recorded_profile()
        legacy = self.preferences.value("cadence_profile_id") != profile.id
        values = {name: self.preferences.value(name, spin.value()) for name, spin in self.spins.items()}
        if legacy:
            values.update(wpm=profile.natural_wpm, corrections=1, variation=100)
        advance = self.preferences.value("advance", True, type=bool)
        blockers = [QSignalBlocker(widget) for widget in (*self.spins.values(), self.advance_check)]
        for name, value in values.items():
            try:
                self.spins[name].setValue(float(value))
            except (TypeError, ValueError):
                pass
        self.advance_check.setChecked(advance)
        del blockers
        self._settings_changed()
        if legacy:
            self._set_status("Using silmoon04's recorded profile. Corrections are now set to the recorded rate (1×).")

    def _use_recorded_defaults(self):
        if self.session.busy:
            return
        self.spins["wpm"].setValue(recorded_profile().natural_wpm)
        self.spins["corrections"].setValue(1)
        self.spins["variation"].setValue(100)
        self._set_status("Restored silmoon04's recorded timing and correction defaults.")

    def _set_status(self, message):
        self.session.message = message
        self._refresh_status()

    def _refresh_status(self):
        message = self.session.message
        self.status_label.setText(self.status_label.fontMetrics().elidedText(message, Qt.TextElideMode.ElideRight,
                                                                           max(30, self.status_label.width())))
        self.status_label.setToolTip(message)

    def refresh(self):
        self._refreshing = True
        try:
            self.model.sync()
            entry = self.document.selected
            changed_selection = self._shown_id != entry.id
            if changed_selection or self.title_edit.text() != entry.title:
                self.title_edit.setText(entry.title)
                self.title_edit.setCursorPosition(0)
            if not entry.rows and (changed_selection or self.description_edit.toPlainText() != entry.description):
                self.description_edit.setPlainText(entry.description)
            self._shown_id = entry.id
            index = self.proxy.mapFromSource(self.model.index(self.document.selected_index))
            self.list_view.selectionModel().setCurrentIndex(index, QItemSelectionModel.SelectionFlag.ClearAndSelect)
            if changed_selection and index.isValid():
                self.list_view.scrollTo(index)
            busy = self.session.busy
            custom = bool(entry.rows)
            self._update_tab_titles()
            self.add_button.setText("Add view" if self.document.custom else "Add")
            self.search.setPlaceholderText("Search view or field titles…" if self.document.custom else "Search titles…")
            self.content_stack.setCurrentWidget(self.view_editor if custom else self.legacy_editor)
            if custom:
                self.view_editor.sync(entry, busy=busy)
            self.start_button.setVisible(not custom)
            self.copy_button.setVisible(not custom)
            accent = COLORS.get(entry.color or "blue", entry.color or "#2563eb")
            self.title_edit.setStyleSheet(f"QLineEdit {{ border-left: 3px solid {accent}; }}" if custom else "")
            for widget in self.edit_controls:
                widget.setEnabled(not busy)
            self.start_button.setEnabled(not busy and bool(entry.description))
            self.copy_button.setEnabled(not busy and bool(entry.description))
            self.advance_check.setEnabled(not busy and not custom)
            self.advance_check.setToolTip("Custom views advance manually so other fields are not skipped." if custom else "")
            self.stop_button.setEnabled(busy)
            for button in (self.back_button, self.up_button):
                button.setEnabled(not busy and self.document.selected_index > 0)
            for button in (self.next_button, self.down_button):
                button.setEnabled(not busy and self.document.selected_index < len(self.document.entries) - 1)
            self.position_label.setText(f"{self.document.selected_index + 1} / {len(self.document.entries)}")
            text = entry.description
            stats = f"silmoon04 · {len(text):,} characters · {len(text.split()):,} words"
            self.stats_label.setText(stats)
            self.stats_label.setToolTip(stats)
            self.legacy_copies.setText(str(entry.copies))
            self.legacy_types.setText(str(entry.types))
            filename = self.document.path.name if self.document.path else (self.document.title if self.document.custom else "Unsaved queue")
            self.file_label.setText(filename + (" *" if self.document.dirty else ""))
            self.file_label.setToolTip(str(self.document.path or "Unsaved queue"))
            application_name = "Profile Typer [preview]" if isinstance(self.backend, PreviewTypingBackend) else "Profile Typer"
            self.setWindowTitle(f"{application_name} | {filename}{' *' if self.document.dirty else ''}")
            self.progress.setValue(round(self.session.progress * 10))
            self._refresh_status()
            self.title_edit.setToolTip(entry.title)
        finally:
            self._refreshing = False

    def navigate(self, offset):
        if not self.session.busy:
            self.document.navigate(offset)
            self.refresh()

    def add_item(self, _checked=False, *, duplicate=False):
        if not self.session.busy:
            self.document.add(duplicate=duplicate)
            self.search.clear()
            self.tabs.setCurrentIndex(0)
            self.refresh()
            self.title_edit.setFocus()
            self.title_edit.selectAll()

    def move_item(self, offset):
        if not self.session.busy:
            self.document.move(offset)
            self.refresh()

    def remove_item(self):
        if self.session.busy:
            return
        if QMessageBox.question(self, "Remove item", f"Remove {self.document.selected.title!r} from the queue?") == QMessageBox.StandardButton.Yes:
            self.document.remove()
            self.refresh()

    def _discard_changes(self):
        if not self.document.dirty:
            return True
        answer = QMessageBox.question(self, "Unsaved queue", "Save your queue changes first?",
                                      QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel)
        if answer == QMessageBox.StandardButton.Save:
            return self.save_json()
        return answer == QMessageBox.StandardButton.Discard

    def open_json(self, _checked=False, *, append=False, path=None):
        if self.session.busy:
            return
        if path is None:
            chosen, _ = QFileDialog.getOpenFileName(self, "Open typing queue", "", "JSON files (*.json);;All files (*)")
            if not chosen:
                return
            path = Path(chosen)
        try:
            parse_views(path.read_text(encoding="utf-8-sig"))  # Validate before asking to discard the current document.
            if not append and not self._discard_changes():
                return
            self.document.load(path, append=append)
            self.search.clear()
            self.tabs.setCurrentIndex(0)
            self.refresh()
            self._set_status(f"Loaded {path.name}.")
        except (OSError, ValueError) as error:
            QMessageBox.warning(self, "Cannot open queue", str(error))

    def save_json(self, _checked=False):
        if self.session.busy:
            return False
        chosen, _ = QFileDialog.getSaveFileName(self, "Save typing queue", str(self.document.path or "typing-queue.json"), "JSON files (*.json)")
        if not chosen:
            return False
        try:
            self.document.save(Path(chosen))
        except (OSError, ValueError) as error:
            QMessageBox.warning(self, "Cannot save queue", str(error))
            return False
        self.refresh()
        self._set_status(f"Saved {Path(chosen).name}.")
        return True

    def paste_json(self):
        if self.session.busy:
            return
        dialog = PasteJsonDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        if not dialog.append and not self._discard_changes():
            return
        self.document.paste(dialog.source, append=dialog.append)
        self.search.clear()
        self.tabs.setCurrentIndex(0)
        self.refresh()
        self._set_status("Pasted JSON imported. Save the queue to keep these changes.")

    def refresh_windows(self):
        if self.session.busy:
            return
        selected = self.target_combo.currentData()
        try:
            targets = self.backend.targets()
        except Exception as error:
            self._set_status(f"Cannot list windows: {error}")
            return
        self.target_combo.clear()
        self.target_combo.addItem("Window focused after countdown", None)
        for window in targets:
            self.target_combo.addItem(f"{window.title} (PID {window.pid})", window.hwnd)
        index = self.target_combo.findData(selected)
        self.target_combo.setCurrentIndex(max(0, index))

    def start_typing(self):
        try:
            self.session.start(self._settings(), self.target_combo.currentData())
        except (ValueError, OSError) as error:
            self._set_status(str(error))
        self.refresh()

    def type_field(self, field_id):
        if self.session.busy:
            return
        try:
            self.session.start(self._settings(), self.target_combo.currentData(), field_id=field_id)
        except (ValueError, OSError) as error:
            self._set_status(str(error))
        self.refresh()

    def copy_description(self):
        self.copy_field(self.document.selected.id, None)

    def copy_field(self, field_id, text=None):
        if self.session.busy:
            return
        try:
            value = self.document.field(field_id).value if text is None else text
            if not value:
                return
            QApplication.clipboard().setText(value)
            self.document.record_copy(field_id)
            self.refresh()
            self._set_status("Copied to clipboard.")
        except (ValueError, RuntimeError) as error:
            self._set_status(str(error))

    def reset_usage(self):
        if not self.session.busy:
            self.document.reset_usage()
            self.refresh()
            self._set_status("Counters reset for the current view.")

    def stop_typing(self):
        self.session.stop()
        self.refresh()

    def _tick(self):
        before = (self.session.phase, self.session.message, self.session.progress)
        self.session.poll()
        if getattr(self.backend, "minimize_for_countdown", False) and before[0] != self.session.phase:
            if self.session.phase == Phase.COUNTDOWN:
                self.showMinimized()
            elif not self.session.busy:
                self.showNormal()
                self.raise_()
        if before != (self.session.phase, self.session.message, self.session.progress):
            self.refresh()
        if self._closing_requested and not self.session.busy:
            self._closing_requested = False
            self.close()

    def _switch_page(self, index):
        self.pages.setCurrentIndex(index)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if not hasattr(self, "pages"):
            return
        self._layout_quick_controls()
        compact = self.width() < 760
        if compact != self._compact:
            self._compact = compact
            blocker = QSignalBlocker(self.tabs)
            if compact:
                self.queue_layout.addWidget(self.queue_panel)
                self.tabs.setTabText(0, "Description")
                self.tabs.setTabVisible(1, True)
            else:
                if self.tabs.currentIndex() == 1:
                    self.tabs.setCurrentIndex(0)
                self.splitter.insertWidget(0, self.queue_panel)
                self.splitter.setSizes([260, max(300, self.width() - 300)])
                self.tabs.setTabText(0, "Queue and description")
                self.tabs.setTabVisible(1, False)
            del blocker
            self.pages.setCurrentIndex(self.tabs.currentIndex())
            self.queue_panel.show()
        self._refresh_status()
        self._update_tab_titles()

    def _update_tab_titles(self):
        custom = bool(self.document.selected.rows)
        self.tabs.setTabText(0, ("View" if self._compact else "Views") if custom else
                             ("Description" if self._compact else "Queue and description"))
        self.tabs.setTabText(1, "Views" if self.document.custom else "Queue")

    def _layout_quick_controls(self):
        if not hasattr(self, "quick_grid"):
            return
        if hasattr(self, "preview_label"):
            self.preview_label.setVisible(self.height() >= 480)
        columns = 4 if self.width() >= 680 else 2
        if columns == self._quick_columns:
            return
        self._quick_columns = columns
        for column in range(4):
            self.quick_grid.setColumnStretch(column, 1 if column < columns else 0)
        for index, field in enumerate(self.quick_fields):
            self.quick_grid.addWidget(field, index // columns, index % columns)

    def show_format(self):
        self._show_text("JSON format", '[\n  {"title": "hello", "description": "text to type out"}\n]\n\n'
                        "A single object is also accepted. Only descriptions are typed.\n\n"
                        'Custom views: {"title":"My guide","views":[{"title":"Repository","rows":[{"columns":2,"fields":[{"title":"Task ID","text":"task-1"},{"title":"URL","text":"https://example.org","actions":["copy"]}]}]}]}\n\n'
                        "Ctrl+O: open; Ctrl+S: save; Alt+Left/Right: navigate; Escape: stop.")

    def show_diagnostics(self):
        import json
        import platform
        import PySide6
        from profile_typer import __version__
        text = (f"Profile Typer {__version__}\nPython {platform.python_version()} | PySide6 {PySide6.__version__}\n"
                f"Profile: {recorded_profile().name} ({recorded_profile().id})\n"
                f"Recorded samples: {json.dumps(recorded_profile().timing['summary'])}\n"
                f"Backend: {type(self.backend).__name__}\nWindow: {self.width()} × {self.height()}\n"
                f"Settings: {json.dumps(asdict(self._settings()))}\n\n{self.session.message}\n\n"
                + "\n".join(self.session.history) + "\n\n" + self.session.details)
        self._show_text("Diagnostics", text)

    def _show_text(self, title, text):
        dialog = QDialog(self)
        dialog.setWindowTitle(title)
        dialog.resize(min(600, self.screen().availableGeometry().width()), 400)
        layout = QVBoxLayout(dialog)
        editor = QPlainTextEdit(text)
        editor.setReadOnly(True)
        layout.addWidget(editor)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        dialog.exec()

    def closeEvent(self, event: QCloseEvent):
        if self.session.busy:
            self._closing_requested = True
            self.stop_typing()
            event.ignore()
            return
        if not self._discard_changes():
            event.ignore()
            return
        self.timer.stop()
        if self.preferences is not None:
            self.preferences.sync()
        event.accept()


def configure_application(app: QApplication):
    from PySide6.QtCore import QStandardPaths
    from PySide6.QtGui import QColor, QFont, QFontDatabase, QPalette
    # Windows' offscreen plugin needs an explicit font for meaningful screenshots.
    if app.platformName() == "offscreen" and "Segoe UI" not in QFontDatabase.families():
        for directory in QStandardPaths.standardLocations(QStandardPaths.StandardLocation.FontsLocation):
            path = Path(directory) / "segoeui.ttf"
            if path.exists():
                QFontDatabase.addApplicationFont(str(path))
                break
    app.setStyle("Fusion")
    font = QFont("Segoe UI", 10) if "Segoe UI" in QFontDatabase.families() else QFontDatabase.systemFont(QFontDatabase.SystemFont.GeneralFont)
    font.setPointSize(10)
    app.setFont(font)
    palette = app.palette()
    for role, color in ((QPalette.ColorRole.Window, "#f4f6fa"), (QPalette.ColorRole.Base, "#ffffff"),
                         (QPalette.ColorRole.WindowText, "#263244"), (QPalette.ColorRole.Text, "#263244"),
                         (QPalette.ColorRole.Button, "#edf1f7"), (QPalette.ColorRole.ButtonText, "#263244"),
                         (QPalette.ColorRole.PlaceholderText, "#697b91"),
                         (QPalette.ColorRole.Highlight, "#2563eb"), (QPalette.ColorRole.HighlightedText, "#ffffff")):
        palette.setColor(role, QColor(color))
    for role in (QPalette.ColorRole.Text, QPalette.ColorRole.ButtonText, QPalette.ColorRole.WindowText):
        palette.setColor(QPalette.ColorGroup.Disabled, role, QColor("#8793a5"))
    app.setPalette(palette)
    app.setStyleSheet("""
        QPushButton, QToolButton { padding: 5px 9px; }
        QPushButton#primary { background: #2563eb; color: white; border-radius: 5px; }
        QPushButton#primary:disabled { background: #c5cfdf; color: #59677a; }
        QLineEdit { padding: 4px; }
        QDoubleSpinBox { padding: 1px 3px; }
        QPlainTextEdit { border: 1px solid #c8d2e0; border-radius: 5px; padding: 6px; }
        QTextEdit#field-value { border: 1px solid #d6deea; background: white; border-radius: 3px; padding: 3px; }
        QListView { border: 1px solid #c8d2e0; border-radius: 5px; }
        QListView::item { padding: 7px; }
        QTabBar::tab { padding: 6px 12px; border: 0; border-bottom: 2px solid #d4dce8; background: #edf1f7; }
        QTabBar::tab:selected { border-bottom-color: #2563eb; color: #1d4ed8; background: #e4edff; }
        QLabel#preview { color: #245da8; }
        QProgressBar { border: 1px solid #d4dce8; border-radius: 4px; max-height: 12px; }
        QProgressBar::chunk { background: #2563eb; }
    """)
