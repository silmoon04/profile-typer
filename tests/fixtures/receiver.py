"""Private Xvfb text receiver for input integration tests."""
import json
import sys
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QPlainTextEdit

app = QApplication([])
field = QPlainTextEdit()
field.setWindowTitle("Profile Typer isolated test receiver")
field.setTabChangesFocus(False)
field.resize(500, 240)
field.show()
field.activateWindow()
field.setFocus()
output = Path(sys.argv[1])
history = []


def save():
    history.append(field.toPlainText())
    temporary = output.with_suffix(".tmp")
    temporary.write_text(json.dumps({"text": field.toPlainText(), "history": history[-100:]}), encoding="utf-8")
    temporary.replace(output)


field.textChanged.connect(save)
save()
app.processEvents()
print(int(field.winId()), flush=True)
QTimer.singleShot(15000, app.quit)
app.exec()
