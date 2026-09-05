"""Portable replay of the bundled recorded cadence and correction model."""
from __future__ import annotations

import random
import time
from dataclasses import dataclass
from typing import Callable, Protocol

from .typing_session import TypingSettings
from .profiles import recorded_profile
from .cadence import build_edit_plan, character_timing, replay_edit_plan


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
    profile_id: str


class InputPort(Protocol):
    def prepare(self, target: int | None) -> None: ...
    def cancelled(self) -> bool: ...
    def insert(self, character: str, *, dwell_ms: float, stop) -> None: ...
    def backspace(self, *, dwell_ms: float, stop) -> None: ...
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
    profile = recorded_profile()
    plan = build_edit_plan(text, randomizer, correction_amount=settings.corrections, profile=profile.mistakes)
    if replay_edit_plan(plan) != text:
        raise ValueError("The correction plan did not reproduce the description.")
    pace = settings.wpm / profile.natural_wpm
    started = clock()
    sent = corrections = 0
    committed: list[str] = []
    previous_character = None
    previous_interval = None
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
        for index, action in enumerate(plan):
            if cancelled or stopped():
                break
            action_started = clock()
            if action.kind == "pause":
                # Preserve the recorded detection/restart pause shape while rescaling pace.
                if not wait(action.delay_ms / pace / 1000):
                    break
            else:
                character = action.character if action.kind == "insert" else "\b"
                timing = character_timing("profile", index, previous_character, character, None,
                                          randomizer, previous_interval, profile.timing,
                                          speed=1, variation=settings.variation / 100)
                previous_interval = timing.rhythm_interval_ms
                dwell = min(450.0, max(8.0, timing.dwell_ms / pace))
                if action.kind == "insert":
                    port.insert(character, dwell_ms=dwell, stop=stop)
                    committed.append(character)
                else:
                    port.backspace(dwell_ms=dwell, stop=stop)
                    corrections += 1
                    if committed:
                        committed.pop()
                sent += 1
                previous_character = character
                elapsed_action = clock() - action_started
                if not wait(max(0, timing.interval_ms / pace / 1000 - elapsed_action)):
                    break
            elapsed = max(clock() - started, 0.001)
            progress(index + 1, len(plan), len(committed) * 12 / elapsed, corrections)
        elapsed = max(clock() - started, 0.001)
        cancelled = cancelled or stopped()
        if not cancelled and "".join(committed) != text:
            raise ValueError("The replay did not reproduce the description.")
        return TypeResult(cancelled, sent, corrections, round(len(committed) * 12 / elapsed, 1), round(elapsed, 2), profile.id)
    finally:
        port.close()
