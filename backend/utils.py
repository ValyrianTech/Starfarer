"""Utility functions for the Starfarer backend, including hashing utilities."""

import hashlib
import random


def deterministic_hash(*args: object) -> int:
    """Produce a deterministic integer from the given arguments."""
    parts = []
    for a in args:
        s = str(a)
        escaped = s.replace("\\", "\\\\").replace("|", "\\p")
        parts.append(f"{len(s)}:{escaped}")
    seed_str = "|".join(parts)
    return int(hashlib.sha256(seed_str.encode()).hexdigest(), 16)


def seeded_random(seed: int, *extra: str) -> random.Random:
    """Create a deterministic random number generator from a seed.

    Combines the base seed with any number of extra string arguments
    to produce a reproducible RNG instance.

    :param seed: The base universe seed.
    :type seed: int
    :param extra: Additional strings to mix into the seed for
        independent RNG streams.
    :type extra: str
    :returns: A seeded :class:`random.Random` instance.
    :rtype: random.Random
    """
    rng = random.Random(str(seed) + "".join(str(e) for e in extra))
    return rng
