"""Chronométrage des réponses indépendant de l’interface."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import time
from typing import Callable


def utc_now_iso() -> str:
    """Horodatage UTC à la milliseconde."""

    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


@dataclass(frozen=True)
class KeyTiming:
    """Touche acceptée, datée par rapport à la présentation."""

    event: str
    value: str
    elapsed_ms: float


@dataclass(frozen=True)
class TimingResult:
    presented_at: str
    first_key_at: str | None
    validated_at: str
    reaction_time_first_key_ms: float | None
    typing_time_ms: float | None
    total_response_time_ms: float
    keystroke_count: int
    correction_count: int
    key_events: tuple[KeyTiming, ...]

    def event_dicts(self) -> list[dict[str, object]]:
        return [asdict(event) for event in self.key_events]


class ResponseTimer:
    """Les durées viennent du compteur monotone. L’horloge civile sert aux horodatages."""

    def __init__(
        self,
        clock_ns: Callable[[], int] = time.perf_counter_ns,
        wall_clock: Callable[[], str] = utc_now_iso,
    ) -> None:
        self._clock_ns = clock_ns
        self._wall_clock = wall_clock
        self._start_ns: int | None = None
        self._first_key_ns: int | None = None
        self._presented_at: str | None = None
        self._first_key_at: str | None = None
        self._events: list[KeyTiming] = []
        self._correction_count = 0
        self._finalized = False

    def start(self) -> None:
        if self._start_ns is not None:
            raise RuntimeError("Le chronomètre a déjà démarré.")
        self._presented_at = self._wall_clock()
        self._start_ns = self._clock_ns()

    def _record(self, event: str, value: str, now_ns: int) -> None:
        if self._start_ns is None:
            raise RuntimeError("Le chronomètre est à l’arrêt.")
        elapsed = round((now_ns - self._start_ns) / 1_000_000, 3)
        self._events.append(KeyTiming(event=event, value=value, elapsed_ms=max(0.0, elapsed)))

    def record_digit(self, digit: str) -> None:
        if self._finalized or len(digit) != 1 or not digit.isdigit():
            return
        now_ns = self._clock_ns()
        if self._first_key_ns is None:
            self._first_key_ns = now_ns
            self._first_key_at = self._wall_clock()
        self._record("digit", digit, now_ns)

    def record_correction(self, key: str = "backspace") -> None:
        if self._finalized:
            return
        now_ns = self._clock_ns()
        self._correction_count += 1
        self._record("correction", key, now_ns)

    def elapsed_ms(self) -> float:
        if self._start_ns is None:
            return 0.0
        return max(0.0, (self._clock_ns() - self._start_ns) / 1_000_000)

    def finalize(self, event: str = "validate") -> TimingResult:
        """Calcule une seule fois la latence, le temps de saisie et le temps total."""

        if self._finalized:
            raise RuntimeError("Le chronomètre est déjà terminé.")
        if self._start_ns is None or self._presented_at is None:
            raise RuntimeError("Le chronomètre est à l’arrêt.")
        now_ns = self._clock_ns()
        self._record(event, "", now_ns)
        self._finalized = True
        total_ms = round(max(0, now_ns - self._start_ns) / 1_000_000, 3)
        reaction_ms = None
        typing_ms = None
        if self._first_key_ns is not None:
            reaction_ms = round(max(0, self._first_key_ns - self._start_ns) / 1_000_000, 3)
            typing_ms = round(max(0, now_ns - self._first_key_ns) / 1_000_000, 3)
        return TimingResult(
            presented_at=self._presented_at,
            first_key_at=self._first_key_at,
            validated_at=self._wall_clock(),
            reaction_time_first_key_ms=reaction_ms,
            typing_time_ms=typing_ms,
            total_response_time_ms=total_ms,
            keystroke_count=sum(event.event in {"digit", "correction"} for event in self._events),
            correction_count=self._correction_count,
            key_events=tuple(self._events),
        )
