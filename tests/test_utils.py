import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from backend.utils import deterministic_hash


class TestDeterministicHash:
    def test_consistent_for_same_inputs(self) -> None:
        assert deterministic_hash("a", "b") == deterministic_hash("a", "b")
        assert deterministic_hash(1, 2, 3) == deterministic_hash(1, 2, 3)
        assert deterministic_hash("hello", "world") == deterministic_hash("hello", "world")

    def test_separator_collision_fixed(self) -> None:
        assert deterministic_hash("a", "b") != deterministic_hash("a|b")

    def test_mixed_types(self) -> None:
        assert deterministic_hash(42, "answer") == deterministic_hash(42, "answer")
        assert isinstance(deterministic_hash(1, "two", 3.0), int)

    def test_no_arguments(self) -> None:
        result = deterministic_hash()
        assert isinstance(result, int)
        assert deterministic_hash() == deterministic_hash()
