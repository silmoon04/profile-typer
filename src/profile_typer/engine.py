"""Portable, cancellable text replay using generic timing parameters."""
from __future__ import annotations

import random
import time
from dataclasses import dataclass
from typing import Callable, Protocol

from .typing_session import TypingSettings


@dataclass(frozen=True)
class WindowTarget:
    hwnd: int
    pid: int
    title: str


@dataclass(frozen=True)
class TypeResult:
    cancelled: bool
    keystrokes: int
    corrections: int
    net_wpm: float
    typed_seconds: float


class InputPort(Protocol):
    def prepare(self, target: int | None) -> None: ...
    def cancelled(self) -> bool: ...
    def insert(self, character: str) -> None: ...
    def backspace(self) -> None: ...
    def close(self) -> None: ...


def replay(text: str, port: InputPort, settings: TypingSettings, stop, progress: Callable,
           *, target=None, rng=None, clock=time.monotonic) -> TypeResult:
    settings.validate()
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    if not text:
        raise ValueError("Enter a description before starting.")
    text.encode("utf-8")
    if any(ord(character) < 32 and character not in "\n\t" for character in text):
        raise ValueError("Descriptions may contain tabs and newlines, but no other control characters.")
    randomizer = rng or random.Random()
    started = clock()
    sent = corrections = committed = 0
    cancelled = False

    def stopped():
        nonlocal cancelled
        cancelled = cancelled or stop.is_set() or port.cancelled()
        return cancelled

    def wait(seconds):
        deadline = clock() + seconds
        while not stopped():
            remaining = deadline - clock()
            if remaining <= 0:
                return True
            stop.wait(min(remaining, 0.04))
        return False

    try:
        if stop.is_set():
            cancelled = True
        else:
            port.prepare(target)
        for character in text:
            if cancelled or stopped():
                break
            # Optional, immediately corrected ASCII mistakes; no captured profiles.
            if character.isascii() and character.isalpha() and randomizer.random() < settings.corrections * 0.02:
                typo = "x" if character.lower() != "x" else "z"
                port.insert(typo)
                sent += 1
                if not wait(0.06):
                    break
                port.backspace()
                sent += 1
                corrections += 1
                if stopped():
                    break
            port.insert(character)
            sent += 1
            committed += 1
            elapsed = max(clock() - started, 0.001)
            progress(committed, len(text), committed * 12 / elapsed, corrections)
            base_interval = 12 / settings.wpm
            interval = base_interval * (1 + randomizer.uniform(-0.35, 0.35) * settings.variation / 100)
            if not wait(interval):
                break
        elapsed = max(clock() - started, 0.001)
        return TypeResult(cancelled, sent, corrections, round(committed * 12 / elapsed, 1), round(elapsed, 2))
    finally:
        port.close()
