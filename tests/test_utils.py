import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from backend.utils import deterministic_hash, seeded_random


class TestDeterministicHash:
    def test_consistent_for_same_inputs(self) -> None:
        assert deterministic_hash("a", "b") == deterministic_hash("a", "b")
        assert deterministic_hash(1, 2, 3) == deterministic_hash(1, 2, 3)
        assert deterministic_hash("hello", "world") == deterministic_hash("hello", "world")

    def test_separator_collision_fixed(self) -> None:
        assert deterministic_hash("a", "b") != deterministic_hash("a|b")

    def test_specific_collision_case(self) -> None:
        h1 = deterministic_hash("5:hello", "world")
        h2 = deterministic_hash("hello", "world")
        assert h1 != h2

    def test_mixed_types(self) -> None:
        assert deterministic_hash(42, "answer") == deterministic_hash(42, "answer")
        assert isinstance(deterministic_hash(1, "two", 3.0), int)

    def test_no_arguments(self) -> None:
        result = deterministic_hash()
        assert isinstance(result, int)
        assert deterministic_hash() == deterministic_hash()


class TestSeededRandom:
    def test_extra_args_not_concatenated(self) -> None:
        assert seeded_random(1, "2", "3").random() != seeded_random(1, "23").random()

    def test_seed_not_concatenated(self) -> None:
        assert seeded_random(1, "23").random() != seeded_random(12, "3").random()

    def test_deterministic(self) -> None:
        assert seeded_random(42, "a", "b").random() == seeded_random(42, "a", "b").random()

    def test_no_extra_args_deterministic_and_distinct(self) -> None:
        assert seeded_random(7).random() == seeded_random(7).random()
        assert seeded_random(7).random() != seeded_random(8).random()

    def test_returns_random_instance(self) -> None:
        import random
        assert isinstance(seeded_random(1), random.Random)
        assert isinstance(seeded_random(1, "x"), random.Random)
