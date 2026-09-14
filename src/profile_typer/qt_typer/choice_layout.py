"""Wrap choices using the space their labels and controls actually need."""
from PySide6.QtCore import QRect, QSize, Qt
from PySide6.QtWidgets import QLayout, QWidget, QSizePolicy


class ChoiceLayout(QLayout):
    def __init__(self, parent):
        super().__init__(parent)
        self._items = []
        self.setContentsMargins(0, 0, 0, 0)
        self.setSpacing(6)

    def addItem(self, item):
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, index):
        return self._items[index] if 0 <= index < len(self._items) else None

    def takeAt(self, index):
        return self._items.pop(index) if 0 <= index < len(self._items) else None

    def expandingDirections(self):
        return Qt.Orientation(0)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self.arrange(QRect(0, 0, width, 0), apply=False)

    def minimumSize(self):
        return QSize(0, 0)

    def sizeHint(self):
        return QSize(0, self.heightForWidth(max(1, self.parentWidget().width())))

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self.arrange(rect, apply=True)

    @staticmethod
    def natural_width(widget):
        layout = widget.layout()
        button = layout.itemAt(0).widget()
        label = layout.itemAt(1).widget()
        margins = layout.contentsMargins()
        return (button.sizeHint().width() + label.fontMetrics().horizontalAdvance(label.text())
                + layout.spacing() + margins.left() + margins.right() + 2)

    def arrange(self, rect, *, apply):
        x = y = line_height = count = maximum_count = 0
        width = max(1, rect.width())
        for item in self._items:
            widget = item.widget()
            item_width = min(width, self.natural_width(widget))
            if x and x + item_width > width:
                x = 0
                y += line_height + self.spacing()
                line_height = count = 0
            # A word-wrapped label's default hint assumes a narrower width.
            # Use the height for the width we actually assign, including padding.
            height = widget.heightForWidth(item_width)
            if height < 0:
                height = widget.sizeHint().height()
            if apply:
                item.setGeometry(QRect(rect.x() + x, rect.y() + y, item_width, height))
            x += item_width + self.spacing()
            line_height = max(line_height, height)
            count += 1
            maximum_count = max(maximum_count, count)
        if apply:
            self.parentWidget().effective_columns = maximum_count
        return y + line_height


class ChoiceRow(QWidget):
    def __init__(self):
        super().__init__()
        self.items = []
        self.effective_columns = 0
        self.grid = ChoiceLayout(self)
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

    def add(self, widget):
        self.items.append(widget)
        self.grid.addWidget(widget)

    def reflow(self, *, force=False):
        while self.grid.count():
            self.grid.takeAt(0)
        for widget in self.items:
            self.grid.addWidget(widget)
        self.grid.invalidate()
        self.updateGeometry()
