"""Chronométrage des touches et des validations."""

from __future__ import annotations

import pytest

from app.timing import ResponseTimer


class FakeClock:
    def __init__(self, values: list[int]):
        self.values = iter(values)

    def __call__(self) -> int:
        return next(self.values)


def test_reaction_typing_total_and_corrections() -> None:
    clock = FakeClock([0, 600_000_000, 800_000_000, 900_000_000, 1_100_000_000])
    timer = ResponseTimer(clock_ns=clock, wall_clock=lambda: "2026-01-01T08:00:00.000+00:00")
    timer.start()
    timer.record_digit("1")
    timer.record_correction()
    timer.record_digit("2")
    result = timer.finalize()
    assert result.reaction_time_first_key_ms == 600.0
    assert result.typing_time_ms == 500.0
    assert result.total_response_time_ms == 1100.0
    assert result.keystroke_count == 3
    assert result.correction_count == 1


def test_one_and_multiple_digits_non_numeric_and_double_validation() -> None:
    clock = FakeClock([0, 100_000_000, 200_000_000, 300_000_000])
    timer = ResponseTimer(clock_ns=clock, wall_clock=lambda: "t")
    timer.start()
    timer.record_digit("x")
    timer.record_digit("4")
    timer.record_digit("2")
    result = timer.finalize()
    assert [event.value for event in result.key_events if event.event == "digit"] == ["4", "2"]
    assert result.keystroke_count == 2
    with pytest.raises(RuntimeError, match="déjà terminé"):
        timer.finalize()
