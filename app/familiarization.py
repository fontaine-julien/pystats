"""Protocole de copie au pavé numérique. La séquence v1 est figée et ses essais sont copiés dans chaque passation."""

from __future__ import annotations

from dataclasses import dataclass


MEASURED_LIMIT_MS = 8000


@dataclass(frozen=True)
class CopyTrial:
    phase: str
    target: str
    initial_text: str = ""


def copy_trials(protocol: str = "numpad_copy_v1") -> tuple[CopyTrial, ...]:
    if protocol != "numpad_copy_v1":
        raise ValueError("Protocole de familiarisation inconnu.")
    # La séquence fixe couvre les dix chiffres et alterne des nombres à un et deux chiffres.
    return (
        CopyTrial("guided", "2"),
        CopyTrial("guided", "45"),
        CopyTrial("guided_correction", "5", "58"),
        *(CopyTrial("measured", value) for value in
          ("7", "24", "0", "63", "5", "18", "2", "90", "8", "47", "3", "56")),
    )
