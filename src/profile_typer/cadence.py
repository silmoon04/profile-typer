"""Measured timing sampler and correction planner extracted from the original simulator."""
from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Mapping

from .profiles import MistakeProfile

@dataclass(frozen=True, slots=True)
class CharacterTiming:
    dwell_ms: float
    interval_ms: float
    rhythm_interval_ms: float | None = None
    model_dwell_ms: float | None = None


@dataclass(frozen=True, slots=True)
class EditAction:
    kind: str
    character: str | None = None
    delay_ms: float = 0.0
    correction_start: bool = False


class Mulberry32:
    """Small deterministic generator matching the former browser fixture."""

    def __init__(self, seed: int) -> None:
        self.state = int(seed) & 0xFFFFFFFF

    def random(self) -> float:
        self.state = (self.state + 0x6D2B79F5) & 0xFFFFFFFF
        value = self.state
        value = self._imul(value ^ (value >> 15), value | 1)
        value ^= value + self._imul(value ^ (value >> 7), value | 61)
        return ((value ^ (value >> 14)) & 0xFFFFFFFF) / 4_294_967_296

    @staticmethod
    def _imul(left: int, right: int) -> int:
        value = (left & 0xFFFFFFFF) * (right & 0xFFFFFFFF)
        return value & 0xFFFFFFFF


def _sample_empirical(
    values: tuple[float, ...] | tuple[int, ...],
    probabilities: tuple[float, ...],
    random: Mulberry32,
    *,
    maximum: float,
) -> float:
    draw = random.random()
    if draw <= probabilities[0]:
        return min(maximum, float(values[0]))
    for upper in range(1, len(probabilities)):
        if draw <= probabilities[upper]:
            lower = upper - 1
            width = probabilities[upper] - probabilities[lower]
            fraction = (draw - probabilities[lower]) / width if width else 0.0
            sampled = float(values[lower]) + (float(values[upper]) - float(values[lower])) * fraction
            return min(maximum, sampled)
    return min(maximum, float(values[-1]))


def _preserve_case(source: str, variant: str) -> str:
    if source.isupper():
        return variant.upper()
    if source[:1].isupper():
        return variant[:1].upper() + variant[1:]
    return variant


def _common_prefix_length(left: str, right: str) -> int:
    length = 0
    for left_character, right_character in zip(left, right, strict=False):
        if left_character != right_character:
            break
        length += 1
    return length


def _generic_word_variant(
    word: str,
    random: Mulberry32,
    profile: MistakeProfile,
) -> str:
    if len(word) < 2:
        return word + word
    choice = int(random.random() * 4)
    if choice == 0:
        candidates = [index for index, character in enumerate(word) if character.casefold() in profile.replacement_choices]
        if candidates:
            index = candidates[int(random.random() * len(candidates))]
            replacements = profile.replacement_choices[word[index].casefold()]
            replacement = replacements[int(random.random() * len(replacements))]
            if word[index].isupper():
                replacement = replacement.upper()
            return word[:index] + replacement + word[index + 1 :]
    if choice == 1 or len(word) == 2:
        index = min(len(word) - 2, int(random.random() * (len(word) - 1)))
        return word[:index] + word[index + 1] + word[index] + word[index + 2 :]
    if choice == 2:
        index = int(random.random() * len(word))
        return word[:index] + word[index] + word[index:]
    index = int(random.random() * len(word))
    return word[:index] + word[index + 1 :]


def _correction_actions(
    intended: str,
    variant: str,
    random: Mulberry32,
    profile: MistakeProfile,
) -> list[EditAction]:
    common_prefix = _common_prefix_length(variant, intended)
    sampled_run = max(
        1,
        round(
            _sample_empirical(
                profile.correction_run_lengths,
                profile.correction_run_probabilities,
                random,
                maximum=8.0,
            )
        ),
    )
    if random.random() < profile.word_rewrite_share:
        retained = 0
    else:
        retained = min(common_prefix, max(0, len(variant) - sampled_run))
    detection_delay = _sample_empirical(
        profile.detection_delays_ms,
        profile.correction_run_probabilities,
        random,
        maximum=2_500.0,
    )
    restart_delay = _sample_empirical(
        profile.restart_delays_ms,
        profile.correction_run_probabilities,
        random,
        maximum=1_500.0,
    )
    actions = [EditAction("insert", character) for character in variant]
    actions.append(EditAction("pause", delay_ms=detection_delay, correction_start=True))
    actions.extend(EditAction("delete") for _ in range(len(variant) - retained))
    actions.append(EditAction("pause", delay_ms=restart_delay))
    actions.extend(EditAction("insert", character) for character in intended[retained:])
    return actions


def build_edit_plan(
    source: str,
    random: Mulberry32,
    *,
    correction_amount: float,
    profile: MistakeProfile,
) -> tuple[EditAction, ...]:
    """Build a deterministic, field-local mistake and correction sequence."""

    amount = min(2.0, max(0.0, float(correction_amount)))
    episode_rate = min(0.5, profile.correction_runs_per_character * amount)
    actions: list[EditAction] = []
    position = 0
    for match in re.finditer(r"[A-Za-z]+|[^A-Za-z]+", source):
        token = match.group(0)
        if match.start() != position:
            raise ValueError("edit-plan tokenization skipped source text")
        position = match.end()
        if token.isascii() and token[0].isalpha():
            correction_probability = 1.0 - (1.0 - episode_rate) ** len(token)
            if random.random() < correction_probability:
                variants = profile.word_variants.get(token.casefold())
                if variants:
                    variant = _preserve_case(token, variants[int(random.random() * len(variants))])
                else:
                    variant = _generic_word_variant(token, random, profile)
                if variant != token:
                    actions.extend(_correction_actions(token, variant, random, profile))
                    continue
            actions.extend(EditAction("insert", character) for character in token)
            continue

        for character in token:
            if character == " " and random.random() < episode_rate * 0.35:
                actions.extend((EditAction("insert", character), EditAction("insert", character)))
                actions.append(
                    EditAction(
                        "pause",
                        delay_ms=_sample_empirical(
                            profile.detection_delays_ms,
                            profile.correction_run_probabilities,
                            random,
                            maximum=1_250.0,
                        ),
                        correction_start=True,
                    )
                )
                actions.append(EditAction("delete"))
            else:
                actions.append(EditAction("insert", character))
    if position != len(source):
        raise ValueError("edit-plan tokenization did not consume source text")
    return tuple(actions)


def replay_edit_plan(actions: tuple[EditAction, ...]) -> str:
    """Apply a plan without timing, for invariant checks and tests."""

    output: list[str] = []
    for action in actions:
        if action.kind == "insert" and action.character is not None:
            output.append(action.character)
        elif action.kind == "delete" and output:
            output.pop()
        elif action.kind != "pause":
            raise ValueError("edit plan contains an unsupported action")
    return "".join(output)


def vk_for_character(character: str) -> int:
    if len(character) != 1:
        return 0
    if character.isascii() and character.isalpha():
        return ord(character.upper())
    if character.isascii() and character.isdecimal():
        return ord(character)
    if character == " ":
        return 32
    if character == "\t":
        return 9
    if character == "\b":
        return 8
    if character in {"\n", "\r"}:
        return 13
    base = {
        ":": ";",
        "+": "=",
        "<": ",",
        "_": "-",
        ">": ".",
        "?": "/",
        "~": "`",
        "{": "[",
        "|": "\\",
        "}": "]",
        '"': "'",
    }.get(character, character)
    return {
        ";": 186,
        "=": 187,
        ",": 188,
        "-": 189,
        ".": 190,
        "/": 191,
        "`": 192,
        "[": 219,
        "\\": 220,
        "]": 221,
        "'": 222,
    }.get(base, 0)


def _key_category(vk: int) -> str:
    if 65 <= vk <= 90:
        return "letter"
    if 48 <= vk <= 57:
        return "digit"
    if vk == 32:
        return "space"
    if vk in {8, 45, 46}:
        return "editing"
    if vk in {9, 13}:
        return "layout"
    if vk in {186, 187, 188, 189, 190, 191, 192, 219, 220, 221, 222}:
        return "punctuation"
    return "other"


def _sample_distribution(
    distribution: Mapping[str, Any],
    profile: Mapping[str, Any],
    random: Mulberry32,
    variation: float,
) -> float:
    values = distribution["quantiles_ms"]
    probabilities = profile["probabilities"]
    if variation <= 0:
        return float(values[4])
    draw = float(probabilities[0]) + random.random() * (
        float(probabilities[-1]) - float(probabilities[0])
    )
    upper = next(
        (index for index, probability in enumerate(probabilities) if float(probability) >= draw),
        len(probabilities) - 1,
    )
    upper = max(1, upper)
    lower = upper - 1
    width = float(probabilities[upper]) - float(probabilities[lower])
    fraction = (draw - float(probabilities[lower])) / width if width > 0 else 0.0
    sampled = float(values[lower]) + (float(values[upper]) - float(values[lower])) * fraction
    return float(values[4]) + (sampled - float(values[4])) * variation


def _choose_distribution(
    candidates: tuple[tuple[Mapping[str, Any] | None, int], ...],
    random: Mulberry32,
) -> Mapping[str, Any]:
    for distribution, shrinkage in candidates:
        if distribution is not None and (
            shrinkage == 0
            or random.random() < int(distribution["count"]) / (int(distribution["count"]) + shrinkage)
        ):
            return distribution
    raise ValueError("timing profile has no usable fallback distribution")


def _rhythm_band(interval_ms: float) -> str:
    if interval_ms < 100:
        return "fast"
    if interval_ms < 300:
        return "normal"
    return "pause"


def character_timing(
    fixture: str,
    index: int,
    previous_character: str | None,
    character: str,
    next_character: str | None,
    random: Mulberry32,
    previous_interval_ms: float | None,
    profile: Mapping[str, Any],
    *,
    speed: float,
    variation: float,
) -> CharacterTiming:
    speed = min(2.0, max(0.5, float(speed)))
    variation = min(1.5, max(0.0, float(variation)))
    if fixture == "profile":
        current_vk = vk_for_character(character)
        previous_vk = 0 if previous_character is None else vk_for_character(previous_character)
        current_category = _key_category(current_vk)
        previous_category = _key_category(previous_vk)
        interval_distribution = _choose_distribution(
            (
                (profile["interval_by_pair"].get(f"{previous_vk}:{current_vk}"), 80),
                (
                    profile["interval_by_category_pair"].get(
                        f"{previous_category}:{current_category}"
                    ),
                    400,
                ),
                (profile["interval_by_key"].get(str(current_vk)), 100),
                (profile["interval_by_category"].get(current_category), 400),
                (profile["interval_global"], 0),
            ),
            random,
        )
        interval = _sample_distribution(interval_distribution, profile, random, variation)
        if previous_interval_ms is not None:
            rhythm = profile["rhythm_after"].get(_rhythm_band(previous_interval_ms))
            if rhythm is not None:
                interval = interval * 0.8 + _sample_distribution(rhythm, profile, random, variation) * 0.2
        dwell_distribution = _choose_distribution(
            (
                (profile["dwell_by_key"].get(str(current_vk)), 20),
                (profile["dwell_by_category"].get(current_category), 60),
                (profile["dwell_global"], 0),
            ),
            random,
        )
        dwell = _sample_distribution(dwell_distribution, profile, random, variation)
        timing = CharacterTiming(
            dwell_ms=max(8.0, dwell / speed),
            interval_ms=max(15.0, interval / speed),
            rhythm_interval_ms=interval,
            model_dwell_ms=dwell,
        )
    elif fixture == "steady":
        timing = CharacterTiming(34.0 / speed, 92.0 / speed)
    elif fixture == "burst":
        timing = CharacterTiming(
            (29.0 + (index % 4) * 3.0) / speed,
            (430.0 if index > 0 and index % 9 == 0 else 68.0) / speed,
        )
    elif fixture == "variable":
        noise = (((index + 1) * 1_103_515_245 + 12_345) >> 8) % 101
        timing = CharacterTiming((27.0 + noise % 31) / speed, (62.0 + noise) / speed)
    else:
        raise ValueError("unknown timing fixture")

    if next_character is not None and vk_for_character(character) == vk_for_character(next_character):
        interval_ms = max(timing.interval_ms, timing.dwell_ms + 5.0)
        rhythm_interval_ms = timing.rhythm_interval_ms
        if rhythm_interval_ms is not None and timing.model_dwell_ms is not None:
            rhythm_interval_ms = max(rhythm_interval_ms, timing.model_dwell_ms + 10.0)
        timing = CharacterTiming(
            timing.dwell_ms,
            interval_ms,
            rhythm_interval_ms,
            timing.model_dwell_ms,
        )
    return timing
