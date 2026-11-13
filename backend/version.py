"""
Deployment version metadata for Starfarer: Echoes of the Void.

Exposes the repository root, the path to the shipped ``HOWTOPLAY.md``
documentation, and the short git commit SHA of the deployed tree. The commit
SHA is resolved lazily (and never raises) so the server can report which
build it is running even when ``git`` is unavailable (for example in a
sandboxed or tarball-only deployment).
"""

import subprocess
from pathlib import Path

REPO_ROOT: Path = Path(__file__).resolve().parents[1]
HOWTOPLAY_PATH: Path = REPO_ROOT / "HOWTOPLAY.md"

_COMMIT_SHA: str | None = None
_COMMIT_SHA_RESOLVED: bool = False


def get_commit_sha() -> str | None:
    """Resolve the short git commit SHA of the repository.

    Runs ``git rev-parse --short HEAD`` in :data:`REPO_ROOT`. Returns the
    stripped stdout on a zero return code with non-empty output, otherwise
    ``None``. Any failure — missing ``git`` binary, ``FileNotFoundError``,
    timeout, or an unreadable working tree — is caught and mapped to
    ``None`` so this function never raises.

    :returns: The short commit SHA as a string, or ``None`` when it cannot
        be determined.
    :rtype: str | None
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except Exception:  # noqa: BLE001 - must never raise regardless of failure
        return None
    if result.returncode != 0:
        return None
    stdout = result.stdout.strip()
    if not stdout:
        return None
    return stdout


def resolve_commit_sha() -> str | None:
    """Return the cached short git commit SHA, resolving it once on demand.

    The first call invokes :func:`get_commit_sha` and caches the result;
    subsequent calls return the cached value without re-running ``git``.

    :returns: The short commit SHA, or ``None`` when it cannot be determined.
    :rtype: str | None
    """
    global _COMMIT_SHA, _COMMIT_SHA_RESOLVED
    if not _COMMIT_SHA_RESOLVED:
        _COMMIT_SHA = get_commit_sha()
        _COMMIT_SHA_RESOLVED = True
    return _COMMIT_SHA


def reset_commit_sha_cache() -> None:
    """Reset the cached commit SHA so the next resolution re-runs ``git``.

    Intended for tests that need to force :func:`resolve_commit_sha` to
    re-resolve after patching :func:`get_commit_sha`.

    :returns: None
    :rtype: None
    """
    global _COMMIT_SHA, _COMMIT_SHA_RESOLVED
    _COMMIT_SHA = None
    _COMMIT_SHA_RESOLVED = False


def ensure_howtoplay_exists() -> Path:
    """Return the HOWTOPLAY.md path, failing loudly if the file is missing.

    This is the "fail loudly at boot" hook: the server must refuse to start
    if the documentation that ships with the deployed code is absent, so
    agents always have matching docs to read.

    :returns: The path to the shipped ``HOWTOPLAY.md`` file.
    :rtype: Path
    :raises RuntimeError: If ``HOWTOPLAY_PATH`` does not exist.
    """
    if not HOWTOPLAY_PATH.exists():
        raise RuntimeError(
            f"HOWTOPLAY.md is missing from the deployed tree at {HOWTOPLAY_PATH}"
        )
    return HOWTOPLAY_PATH
