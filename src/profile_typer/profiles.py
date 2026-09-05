"""Validated, bundled recording aggregates shared by every input backend."""
from __future__ import annotations

import json
import math
from dataclasses import dataclass
from functools import lru_cache
from importlib.resources import files
from typing import Any, Mapping

_QUANTILE_POINTS = (0.01, 0.05, 0.10, 0.25, 0.50, 0.75, 0.90, 0.95, 0.99)
_INTERVAL_MAX_MS = 2500.0
_DWELL_MAX_MS = 500.0
_KEY_CATEGORIES = frozenset({"digit", "editing", "layout", "letter", "other", "punctuation", "space"})
_PROFILE_SOURCES = frozenset({"local-aggregate"})

@dataclass(frozen=True, slots=True)
class MistakeProfile:
    printable_events: int
    correction_runs: int
    deleted_characters: int
    report_characters: int
    correction_run_lengths: tuple[int, ...]
    correction_run_probabilities: tuple[float, ...]
    detection_delays_ms: tuple[float, ...]
    restart_delays_ms: tuple[float, ...]
    word_rewrite_share: float
    word_variants: dict[str, tuple[str, ...]]
    replacement_choices: dict[str, tuple[str, ...]]

    @property
    def correction_runs_per_character(self) -> float:
        return self.correction_runs / self.printable_events

    @property
    def deleted_character_rate(self) -> float:
        return self.deleted_characters / self.report_characters


def validate_mistake_profile(profile: MistakeProfile) -> None:
    if profile.printable_events <= 0 or profile.correction_runs < 0:
        raise ValueError("mistake profile event totals are invalid")
    if profile.report_characters <= 0 or profile.deleted_characters < 0:
        raise ValueError("mistake profile character totals are invalid")
    if not 0.0 <= profile.word_rewrite_share <= 1.0:
        raise ValueError("mistake profile word rewrite share is invalid")
    if len(profile.correction_run_lengths) != len(profile.correction_run_probabilities):
        raise ValueError("mistake profile run distribution does not align")
    if len(profile.detection_delays_ms) != len(profile.correction_run_probabilities):
        raise ValueError("mistake profile detection distribution does not align")
    if len(profile.restart_delays_ms) != len(profile.correction_run_probabilities):
        raise ValueError("mistake profile restart distribution does not align")
    if tuple(sorted(profile.correction_run_probabilities)) != profile.correction_run_probabilities:
        raise ValueError("mistake profile probabilities are not monotonic")
    if any(not 0.0 <= value <= 1.0 for value in profile.correction_run_probabilities):
        raise ValueError("mistake profile probability is outside its bound")
    for values in (
        profile.correction_run_lengths,
        profile.detection_delays_ms,
        profile.restart_delays_ms,
    ):
        if any(not math.isfinite(float(value)) or value < 0 for value in values):
            raise ValueError("mistake profile distribution contains an invalid value")
    for correct, variants in profile.word_variants.items():
        if not correct or not variants or any(not variant or variant == correct for variant in variants):
            raise ValueError("mistake profile word variants are invalid")

def _validate_distribution(value: object, *, maximum_ms: float) -> None:
    if not isinstance(value, Mapping) or set(value) != {"count", "quantiles_ms"}:
        raise ValueError("timing distribution fields do not match")
    count = value["count"]
    quantiles = value["quantiles_ms"]
    if isinstance(count, bool) or not isinstance(count, int) or count < 0:
        raise ValueError("timing distribution count is invalid")
    if not isinstance(quantiles, list) or len(quantiles) != len(_QUANTILE_POINTS):
        raise ValueError("timing distribution quantiles do not match the schema")
    normalized: list[float] = []
    for item in quantiles:
        if isinstance(item, bool) or not isinstance(item, (int, float)):
            raise ValueError("timing distribution quantile is not numeric")
        number = float(item)
        if not math.isfinite(number) or not 0 <= number <= maximum_ms:
            raise ValueError("timing distribution quantile is outside its bound")
        normalized.append(number)
    if normalized != sorted(normalized):
        raise ValueError("timing distribution quantiles are not monotonic")


def _validate_distribution_map(
    value: object,
    *,
    maximum_ms: float,
    allowed_keys: frozenset[str] | None = None,
    category_pairs: bool = False,
    numeric_keys: bool = False,
    numeric_pairs: bool = False,
) -> None:
    if not isinstance(value, Mapping):
        raise ValueError("timing distribution map is invalid")
    for key, distribution in value.items():
        if not isinstance(key, str):
            raise ValueError("timing distribution key is invalid")
        if allowed_keys is not None and key not in allowed_keys:
            raise ValueError("timing distribution category is invalid")
        if category_pairs:
            parts = key.split(":")
            if len(parts) != 2 or any(part not in _KEY_CATEGORIES for part in parts):
                raise ValueError("timing category pair is invalid")
        if numeric_keys and (not key.isdecimal() or not 0 <= int(key) <= 255):
            raise ValueError("timing distribution key ID is invalid")
        if numeric_pairs:
            parts = key.split(":")
            if len(parts) != 2 or any(not part.isdecimal() or not 0 <= int(part) <= 255 for part in parts):
                raise ValueError("timing distribution key pair is invalid")
        _validate_distribution(distribution, maximum_ms=maximum_ms)


def validate_timing_profile(profile: Mapping[str, Any]) -> None:
    """Reject a profile that the browser sampler cannot consume safely."""

    required = {
        "schema_version",
        "source",
        "summary",
        "probabilities",
        "interval_global",
        "dwell_global",
        "interval_by_key",
        "interval_by_pair",
        "interval_by_category",
        "interval_by_category_pair",
        "dwell_by_key",
        "dwell_by_category",
        "rhythm_after",
    }
    if set(profile) != required or profile["schema_version"] != 1:
        raise ValueError("timing profile fields do not match schema version 1")
    if profile["source"] not in _PROFILE_SOURCES:
        raise ValueError("timing profile source is invalid")
    if profile["probabilities"] != list(_QUANTILE_POINTS):
        raise ValueError("timing profile probability grid is invalid")
    summary = profile["summary"]
    if not isinstance(summary, Mapping):
        raise ValueError("timing profile summary is invalid")
    expected_summary = {"status", "interval_samples", "dwell_samples", "keys_modelled", "digraphs_modelled"}
    if set(summary) != expected_summary or summary["status"] not in {
        "no_personal_data",
        "profile_unavailable",
        "ready",
    }:
        raise ValueError("timing profile summary fields do not match")
    for name in expected_summary - {"status"}:
        value = summary[name]
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError("timing profile summary count is invalid")
    expected_status = {
        "fallback": "no_personal_data",
        "fallback-error": "profile_unavailable",
        "local-aggregate": "ready",
    }[profile["source"]]
    if summary["status"] != expected_status:
        raise ValueError("timing profile source and status do not agree")
    _validate_distribution(profile["interval_global"], maximum_ms=_INTERVAL_MAX_MS)
    _validate_distribution(profile["dwell_global"], maximum_ms=_DWELL_MAX_MS)
    _validate_distribution_map(
        profile["interval_by_key"],
        maximum_ms=_INTERVAL_MAX_MS,
        numeric_keys=True,
    )
    _validate_distribution_map(
        profile["interval_by_pair"],
        maximum_ms=_INTERVAL_MAX_MS,
        numeric_pairs=True,
    )
    _validate_distribution_map(
        profile["interval_by_category"],
        maximum_ms=_INTERVAL_MAX_MS,
        allowed_keys=_KEY_CATEGORIES,
    )
    _validate_distribution_map(
        profile["interval_by_category_pair"],
        maximum_ms=_INTERVAL_MAX_MS,
        category_pairs=True,
    )
    _validate_distribution_map(
        profile["dwell_by_key"],
        maximum_ms=_DWELL_MAX_MS,
        numeric_keys=True,
    )
    _validate_distribution_map(
        profile["dwell_by_category"],
        maximum_ms=_DWELL_MAX_MS,
        allowed_keys=_KEY_CATEGORIES,
    )
    _validate_distribution_map(
        profile["rhythm_after"],
        maximum_ms=_INTERVAL_MAX_MS,
        allowed_keys=frozenset({"fast", "normal", "pause"}),
    )
    if summary["keys_modelled"] != len(profile["interval_by_key"]):
        raise ValueError("timing profile key count does not match")
    if summary["digraphs_modelled"] != len(profile["interval_by_pair"]):
        raise ValueError("timing profile pair count does not match")
    if summary["interval_samples"] != profile["interval_global"]["count"]:
        raise ValueError("timing profile interval count does not match")
    if summary["dwell_samples"] != profile["dwell_global"]["count"]:
        raise ValueError("timing profile dwell count does not match")


@dataclass(frozen=True)
class RecordedProfile:
    id: str
    name: str
    timing: Mapping[str, Any]
    mistakes: MistakeProfile

    @property
    def natural_wpm(self) -> float:
        return round(12000.0 / self.timing["interval_global"]["quantiles_ms"][4], 1)


@lru_cache(maxsize=1)
def recorded_profile() -> RecordedProfile:
    data = json.loads(files("profile_typer").joinpath("data/silmoon04.json").read_text(encoding="utf-8"))
    if set(data) != {"schema_version", "id", "name", "timing", "mistakes"} or data["schema_version"] != 1:
        raise ValueError("The bundled recorded profile has an unsupported schema.")
    validate_timing_profile(data["timing"])
    if data["timing"]["source"] != "local-aggregate" or not data["timing"]["summary"]["interval_samples"]:
        raise ValueError("The recorded profile is missing its measured timing samples.")
    raw = data["mistakes"]
    for name in ("correction_run_lengths", "correction_run_probabilities", "detection_delays_ms", "restart_delays_ms"):
        raw[name] = tuple(raw[name])
    for name in ("word_variants", "replacement_choices"):
        raw[name] = {key: tuple(values) for key, values in raw[name].items()}
    mistakes = MistakeProfile(**raw)
    validate_mistake_profile(mistakes)
    return RecordedProfile(data["id"], data["name"], data["timing"], mistakes)
