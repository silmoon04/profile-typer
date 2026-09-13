"""Explicit card tones and selected-choice colors."""
import math

from PySide6.QtGui import QColor

TONES = {"a": "#edf3fc", "b": "#f3edfa", "statement": "#f1f1df", "reason": "#f5f3ec", "neutral": "#fffef9"}


def choice_color(options, option):
    known = {"yes": "#dcebc8", "pass": "#dcebc8", "no": "#f2d4cc", "fail": "#f2d4cc", "partial": "#efe3b9"}
    if option.lower() in known:
        return known[option.lower()]
    try:
        numbers = [float(value) for value in options]
        if len(numbers) > 1 and all(math.isfinite(n) for n in numbers) and all(a < b for a, b in zip(numbers, numbers[1:], strict=False)):
            fraction = (float(option) - numbers[0]) / (numbers[-1] - numbers[0])
            start, end = QColor("#f2d4cc"), QColor("#dcebc8")
            return QColor(*(round(a + (b - a) * fraction) for a, b in zip(start.getRgb()[:3], end.getRgb()[:3], strict=True))).name()
    except (ValueError, OverflowError):
        pass
    return "#e5ead9"
