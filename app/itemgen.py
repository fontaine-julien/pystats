"""Génération reproductible de listes d’items équilibrées."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, replace
import random
import uuid
from typing import Iterable, Sequence

from app.config import AssessmentConfig


@dataclass(frozen=True)
class Item:
    item_id: str
    op: str
    operand_1: int
    operand_2: int
    expected: int
    evaluated: bool
    kind: str
    is_anchor: bool
    fact_family: str
    difficulty_category: str
    fact_key: str

    @property
    def a(self) -> int:
        """Accès conservé pour l’ancienne interface."""

        return self.operand_1

    @property
    def b(self) -> int:
        """Accès conservé pour l’ancienne interface."""

        return self.operand_2


def _difficulty(op: str, first: int, second: int, expected: int) -> str:
    """Utilise des catégories descriptives pour équilibrer la liste."""

    magnitude = abs(first) + abs(second) + abs(expected)
    if op in {"multiplication", "division"}:
        if min(abs(first), abs(second)) in {0, 1, 2, 5, 10}:
            return "easy"
        if max(abs(first), abs(second)) >= 8 or magnitude >= 60:
            return "hard"
        return "medium"
    if op.startswith("complement"):
        if expected % 10 == 0 or first % 10 == 0:
            return "easy"
        if expected < 10 or first > 85:
            return "hard"
        return "medium"
    if magnitude <= 20:
        return "easy"
    if magnitude >= 80:
        return "hard"
    return "medium"


def _candidate(op: str, first: int, second: int) -> Item | None:
    """Renvoie une paire d’opérandes valide ou None."""

    if op == "addition":
        expected = first + second
        family = f"addition_{first}"
    elif op == "subtraction":
        if first < second:
            return None
        expected = first - second
        family = f"subtraction_{second}"
    elif op == "multiplication":
        expected = first * second
        family = f"table_{first}"
    elif op == "division":
        if first == 0:
            return None
        expected = second
        second, first = first, first * second
        family = f"division_by_{second}"
    elif op == "complement_10":
        target = 10
        if not 0 <= first <= target:
            return None
        second = target
        expected = target - first
        family = "complements_10"
    elif op == "complement_100":
        target = 100
        if not 0 <= first <= target:
            return None
        second = target
        expected = target - first
        family = "complements_100"
    else:
        return None
    fact_key = f"{op}:{first}:{second}:{expected}"
    return Item(
        item_id="",
        op=op,
        operand_1=int(first),
        operand_2=int(second),
        expected=int(expected),
        evaluated=True,
        kind="scored",
        is_anchor=False,
        fact_family=family,
        difficulty_category=_difficulty(op, first, second, expected),
        fact_key=fact_key,
    )


def build_candidate_pool(config: AssessmentConfig) -> list[Item]:
    candidates: dict[str, Item] = {}
    for op in config.operations:
        for first in config.operand_1_values:
            for second in config.operand_2_values:
                item = _candidate(op, first, second)
                if item is not None:
                    candidates[item.fact_key] = item
    if not candidates:
        raise ValueError("Les opérandes choisis ne permettent de créer aucun item valide.")
    return sorted(candidates.values(), key=lambda item: item.fact_key)


def _selection_score(
    item: Item,
    position: int,
    selected: Sequence[Item],
    family_counts: Counter[str],
    operand_counts: Counter[int],
    difficulty_counts: Counter[str],
    answer_length_counts: Counter[int],
    fact_counts: Counter[str],
) -> float:
    """Un score bas favorise l’équilibre des opérations et des opérandes."""

    answer_length = len(str(abs(item.expected)))
    score = (
        3.0 * fact_counts[item.fact_key]
        + 12.0 * family_counts[item.fact_family]
        + 1.2 * operand_counts[item.operand_2]
        + 1.0 * difficulty_counts[item.difficulty_category]
        + 0.7 * answer_length_counts[answer_length]
    )
    if selected and selected[-1].fact_key == item.fact_key:
        score += 1000.0
    if selected and selected[-1].fact_family == item.fact_family:
        score += 4.0
    if len(selected) >= 2 and selected[-2].fact_family == item.fact_family:
        score += 1.5
    # La pénalité croissante évite d’accumuler les items difficiles en fin d’épreuve.
    if item.difficulty_category == "hard" and position > 0:
        score += 0.2 * position / max(1, position + 1)
    return score


def _balanced_select(
    pool: Sequence[Item],
    count: int,
    rng: random.Random,
    random_ties: bool = True,
) -> list[Item]:
    """Choisit à chaque étape l’item qui améliore le plus l’équilibre."""

    selected: list[Item] = []
    family_counts: Counter[str] = Counter()
    operand_counts: Counter[int] = Counter()
    difficulty_counts: Counter[str] = Counter()
    answer_length_counts: Counter[int] = Counter()
    fact_counts: Counter[str] = Counter()
    for position in range(count):
        scored = [
            (
                _selection_score(
                    item,
                    position,
                    selected,
                    family_counts,
                    operand_counts,
                    difficulty_counts,
                    answer_length_counts,
                    fact_counts,
                ),
                rng.random() if random_ties else 0.0,
                item,
            )
            for item in pool
        ]
        _, _, chosen = min(scored, key=lambda row: (row[0], row[1], row[2].fact_key))
        selected.append(chosen)
        family_counts[chosen.fact_family] += 1
        operand_counts[chosen.operand_2] += 1
        difficulty_counts[chosen.difficulty_category] += 1
        answer_length_counts[len(str(abs(chosen.expected)))] += 1
        fact_counts[chosen.fact_key] += 1
    return selected


def _spread_anchor_positions(total: int, count: int) -> set[int]:
    """Répartit les ancrages à intervalles réguliers dans les items notés."""

    if count <= 0:
        return set()
    return {
        min(total - 1, max(0, round((index + 1) * (total + 1) / (count + 1)) - 1))
        for index in range(count)
    }


def generate_assessment_items(
    config: AssessmentConfig,
    anchors: Iterable[Item] = (),
) -> list[Item]:
    """La configuration, la graine et les ancrages déterminent les essais et l’ordre des items notés."""

    rng = random.Random(config.random_seed)
    pool = build_candidate_pool(config)
    anchor_items = list(anchors)[: config.anchor_count]
    if len(anchor_items) < config.anchor_count:
        raise ValueError("L’évaluation source contient trop peu d’items pour les ancrages demandés.")
    anchor_items = [replace(item, evaluated=True, kind="scored", is_anchor=True) for item in anchor_items]
    renewed_count = config.n_scored_items - len(anchor_items)
    random_ties = config.order_mode == "balanced_random"
    renewed = _balanced_select(pool, renewed_count, rng, random_ties=random_ties)

    anchor_positions = _spread_anchor_positions(config.n_scored_items, len(anchor_items))
    scored: list[Item] = []
    anchor_iter = iter(anchor_items)
    renewed_iter = iter(renewed)
    for position in range(config.n_scored_items):
        source = next(anchor_iter) if position in anchor_positions else next(renewed_iter)
        scored.append(source)

    practice_pool = [item for item in pool if item.fact_key not in {row.fact_key for row in scored}]
    if len(practice_pool) < config.n_practice_items:
        practice_pool = pool
    practice = _balanced_select(practice_pool, config.n_practice_items, rng, random_ties=random_ties)
    items = [replace(item, evaluated=False, kind="practice", is_anchor=False) for item in practice] + scored

    finalized: list[Item] = []
    for position, item in enumerate(items):
        deterministic_id = uuid.uuid5(
            uuid.NAMESPACE_URL,
            f"pystats:{config.random_seed}:{position}:{item.kind}:{item.fact_key}:{int(item.is_anchor)}",
        )
        finalized.append(replace(item, item_id=str(deterministic_id)))
    return finalized


def generate_complements_100(
    n_evaluated: int,
    n_trials: int,
    n_examples: int,
    seed: int | None = None,
) -> list[Item]:
    """Les anciens paramètres d’entraînement sont ramenés à deux essais."""

    del n_trials, n_examples
    config = AssessmentConfig(
        operations=("complement_100",),
        operand_1_values=tuple(range(1, 100)),
        operand_2_values=(100,),
        n_scored_items=max(1, int(n_evaluated)),
        n_practice_items=2,
        random_seed=int(seed if seed is not None else random.SystemRandom().randrange(1, 2**63)),
    )
    return generate_assessment_items(config)


def generate_multiplications(
    n_evaluated: int,
    n_trials: int,
    n_examples: int,
    table_min: int,
    table_max: int,
    factor_min: int = 1,
    factor_max: int = 10,
    seed: int | None = None,
) -> list[Item]:
    """Ancien point d’entrée pour les multiplications."""

    del n_trials, n_examples
    low, high = sorted((int(table_min), int(table_max)))
    factor_low, factor_high = sorted((int(factor_min), int(factor_max)))
    config = AssessmentConfig(
        operations=("multiplication",),
        operand_1_values=tuple(range(low, high + 1)),
        operand_2_values=tuple(range(factor_low, factor_high + 1)),
        n_scored_items=max(1, int(n_evaluated)),
        n_practice_items=2,
        random_seed=int(seed if seed is not None else random.SystemRandom().randrange(1, 2**63)),
    )
    return generate_assessment_items(config)
