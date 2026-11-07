"""Équilibre, ancrages et reproductibilité des items."""

from __future__ import annotations

from collections import Counter
import sqlite3

import pytest

from app.assessment_service import create_assessment
from app.config import AssessmentConfig
from app.itemgen import generate_assessment_items
from conftest import create_sample_assessment


def test_seed_reproduces_exact_items_and_balances_families() -> None:
    config = AssessmentConfig(
        operations=("multiplication",),
        operand_1_values=(2, 3, 4, 5),
        operand_2_values=tuple(range(1, 11)),
        n_scored_items=37,
        random_seed=987654321,
    )
    first = generate_assessment_items(config)
    second = generate_assessment_items(config)
    assert first == second
    assert len(first) == 39
    assert [item.kind for item in first[:2]] == ["practice", "practice"]
    assert all(item.evaluated for item in first[2:])
    family_counts = Counter(item.fact_family for item in first[2:])
    assert max(family_counts.values()) - min(family_counts.values()) <= 1
    assert all(left.fact_key != right.fact_key for left, right in zip(first[2:], first[3:]))


def test_fixed_order_ignores_random_tie_breaking() -> None:
    first = AssessmentConfig(n_scored_items=12, order_mode="fixed", random_seed=1)
    second = AssessmentConfig(n_scored_items=12, order_mode="fixed", random_seed=999)
    first_facts = [item.fact_key for item in generate_assessment_items(first)]
    second_facts = [item.fact_key for item in generate_assessment_items(second)]
    assert first_facts == second_facts


def test_anchor_items_are_reused_and_spread() -> None:
    source_config = AssessmentConfig(n_scored_items=20, random_seed=10)
    source = generate_assessment_items(source_config)
    anchors = source[2:7]
    target_config = AssessmentConfig(
        n_scored_items=20,
        anchor_count=5,
        anchor_source_assessment_id=1,
        random_seed=11,
    )
    target = generate_assessment_items(target_config, anchors)
    anchor_positions = [index for index, item in enumerate(target) if item.is_anchor]
    assert len(anchor_positions) == 5
    assert set(item.fact_key for item in target if item.is_anchor) == set(item.fact_key for item in anchors)
    assert min(anchor_positions) > 2
    assert max(anchor_positions) < len(target) - 1


def test_assessment_is_frozen_and_attempts_copy_same_order(database) -> None:
    db, project_id, student_ids = database
    assessment_id = create_sample_assessment(db, project_id, student_ids)
    attempt_one = db.create_attempt(assessment_id, student_ids[0])
    attempt_two = db.create_attempt(assessment_id, student_ids[1])
    ids_one = [row["item_uuid"] for row in db.load_attempt_items(attempt_one)]
    ids_two = [row["item_uuid"] for row in db.load_attempt_items(attempt_two)]
    assert ids_one == ids_two
    assert db.verify_assessment_integrity(assessment_id)
    with pytest.raises(sqlite3.IntegrityError, match="frozen"):
        db.exec("UPDATE assessment_item SET expected=999 WHERE assessment_id=?", (assessment_id,))
