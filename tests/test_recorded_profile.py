import hashlib
from importlib.resources import files

from profile_typer.cadence import build_edit_plan, character_timing, Mulberry32, replay_edit_plan
from profile_typer.profiles import recorded_profile
from profile_typer.typing_session import TypingSettings


def test_bundle_is_the_exported_recorded_profile_not_a_fallback():
    data = files("profile_typer").joinpath("data/silmoon04.json").read_bytes()
    assert hashlib.sha256(data).hexdigest() == "485cf7530d37a20da8858d2442b5a3c6cc706f1cfa4fb97afb2fb6d2ab99930d"
    profile = recorded_profile()
    assert profile.id == "silmoon04-v1"
    assert profile.timing["source"] == "local-aggregate"
    assert profile.timing["summary"] == {"status": "ready", "interval_samples": 337035, "dwell_samples": 1507,
                                          "keys_modelled": 58, "digraphs_modelled": 643}
    assert profile.mistakes.printable_events == 23470
    assert profile.mistakes.correction_runs == 1398
    assert profile.mistakes.word_variants["the"] == ("teh", "hte", "tghe", "trhe")


def test_recorded_defaults_enable_personal_cadence_and_corrections():
    settings = TypingSettings()
    assert settings.wpm == 81.6
    assert settings.corrections == 1
    assert settings.variation == 100


def test_pair_medians_come_from_the_recording():
    class Zero:
        def random(self):
            return 0

    profile = recorded_profile().timing
    values = []
    for first, second in (("t", "h"), ("h", "e"), ("a", "n")):
        expected = profile["interval_by_pair"][f"{ord(first.upper())}:{ord(second.upper())}"]["quantiles_ms"][4]
        timing = character_timing("profile", 0, first, second, None, Zero(), None, profile, speed=1, variation=0)
        assert timing.interval_ms == max(15, expected)
        values.append(timing.interval_ms)
    assert len(set(values)) > 1


def test_profile_plan_contains_delayed_corrections_and_keeps_unicode_exact():
    source = "the and you " * 30 + "café 👋\n\n"
    plan = build_edit_plan(source, Mulberry32(42), correction_amount=1, profile=recorded_profile().mistakes)
    assert replay_edit_plan(plan) == source
    assert any(action.correction_start and action.delay_ms > 300 for action in plan)
    assert any(first.kind == second.kind == "delete" for first, second in zip(plan, plan[1:], strict=False))
    assert sum(action.character == "\n" for action in plan if action.kind == "insert") == 2
