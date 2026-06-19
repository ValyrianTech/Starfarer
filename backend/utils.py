"""Utility functions for the Starfarer backend, including hashing utilities."""

import hashlib


def deterministic_hash(*args: object) -> int:
    """Produce a deterministic integer from the given arguments."""
    seed_str = "|".join(str(a) for a in args)
    return int(hashlib.sha256(seed_str.encode()).hexdigest(), 16)
