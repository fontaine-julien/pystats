"""Paramètres et validation des évaluations."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Any


SUPPORTED_OPERATIONS = (
    "addition",
    "subtraction",
    "multiplication",
    "division",
    "complement_10",
    "complement_100",
)


@dataclass(frozen=True)
class AssessmentConfig:
    """Un délai de zéro est désactivé. Le protocole impose deux items d’entraînement."""

    operations: tuple[str, ...] = ("multiplication",)
    operand_1_values: tuple[int, ...] = tuple(range(1, 11))
    operand_2_values: tuple[int, ...] = tuple(range(1, 11))
    n_scored_items: int = 50
    n_practice_items: int = 2
    anchor_count: int = 0
    anchor_source_assessment_id: int | None = None
    global_time_limit_s: float | None = None
    item_time_limit_s: float | None = None
    order_mode: str = "balanced_random"
    assessment_date: str = field(default_factory=lambda: date.today().isoformat())
    academic_period: str = ""
    group_id: str = "classe"
    difficulty_categories: tuple[str, ...] = ("easy", "medium", "hard")
    random_seed: int = 1
    assessment_version: str = "1"
    familiarization_enabled: bool = False
    familiarization_protocol: str = "numpad_copy_v1"
    allow_omissions: bool = False

    def __post_init__(self) -> None:
        if type(self.allow_omissions) is not bool:
            raise ValueError("L’option d’omission doit être un booléen.")
        if type(self.familiarization_enabled) is not bool:
            raise ValueError("L’option de familiarisation doit être un booléen.")
        if self.familiarization_protocol != "numpad_copy_v1":
            raise ValueError("Protocole de familiarisation inconnu.")
        unknown = set(self.operations).difference(SUPPORTED_OPERATIONS)
        if unknown:
            raise ValueError(f"Opérations non prises en charge : {sorted(unknown)}")
        if not self.operations:
            raise ValueError("Choisissez au moins une opération.")
        if not self.operand_1_values or not self.operand_2_values:
            raise ValueError("Renseignez les valeurs des deux opérandes.")
        if self.n_scored_items < 1:
            raise ValueError("Prévoyez au moins un item noté.")
        if self.n_practice_items != 2:
            raise ValueError("Le protocole prévoit exactement deux items d’entraînement.")
        if self.anchor_count < 0 or self.anchor_count > self.n_scored_items:
            raise ValueError("Le nombre d’items d’ancrage doit être compris entre zéro et le nombre d’items notés.")
        if self.global_time_limit_s is not None and self.global_time_limit_s <= 0:
            raise ValueError("La limite de temps globale doit être positive.")
        if self.item_time_limit_s is not None and self.item_time_limit_s <= 0:
            raise ValueError("La limite de temps par item doit être positive.")
        if self.order_mode not in {"balanced_random", "fixed"}:
            raise ValueError("Le mode d’ordre doit être 'balanced_random' ou 'fixed'")

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        for key in ("operations", "operand_1_values", "operand_2_values", "difficulty_categories"):
            data[key] = list(data[key])
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AssessmentConfig":
        """Valide aussi les anciens formats de configuration."""

        raw = dict(data)
        legacy_type = str(raw.get("type", ""))
        if "operations" not in raw:
            if legacy_type == "complements_100":
                raw["operations"] = ["complement_100"]
            else:
                raw["operations"] = ["multiplication"]
        if "operand_1_values" not in raw:
            low = int(raw.get("table_min", 1))
            high = int(raw.get("table_max", 10))
            raw["operand_1_values"] = list(range(min(low, high), max(low, high) + 1))
        raw.setdefault("operand_2_values", list(range(1, 11)))
        raw.setdefault("n_scored_items", int(raw.get("n_eval", 50)))
        raw["n_practice_items"] = 2
        raw.setdefault("global_time_limit_s", raw.get("time_limit_s"))
        raw.setdefault("item_time_limit_s", None)
        raw.setdefault("random_seed", int(raw.get("seed", 1)))
        raw.setdefault("difficulty_categories", ["easy", "medium", "hard"])
        allowed = {field.name for field in cls.__dataclass_fields__.values()}
        raw = {key: value for key, value in raw.items() if key in allowed}
        for key in ("global_time_limit_s", "item_time_limit_s"):
            if raw.get(key) in (0, 0.0, "0", "", None):
                raw[key] = None
            elif key in raw:
                raw[key] = float(raw[key])
        for key in ("operations", "operand_1_values", "operand_2_values", "difficulty_categories"):
            if key in raw:
                caster = int if "operand" in key else str
                raw[key] = tuple(caster(value) for value in raw[key])
        return cls(**raw)


def parse_integer_values(text: str) -> tuple[int, ...]:
    """Lit des entiers et des plages inclusives comme « 1-5,8 »."""

    values: set[int] = set()
    for chunk in (part.strip() for part in text.split(",")):
        if not chunk:
            continue
        if "-" in chunk[1:]:
            left, right = chunk.split("-", 1)
            start, stop = int(left), int(right)
            values.update(range(min(start, stop), max(start, stop) + 1))
        else:
            values.add(int(chunk))
    if not values:
        raise ValueError("Saisissez au moins un entier.")
    return tuple(sorted(values))
