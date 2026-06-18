import hashlib


def deterministic_hash(*args) -> int:
    """Produce a deterministic integer from the given arguments."""
    seed_str = "|".join(str(a) for a in args)
    return int(hashlib.md5(seed_str.encode()).hexdigest(), 16)
