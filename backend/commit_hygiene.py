"""Commit message hygiene validation for the Starfarer repository.

This module provides a self-contained conventional-commit validator used by
the repository's ``commit-msg`` git hook. It never invokes git or any
subprocess: it only parses and validates strings, so it can be unit-tested in
isolation and reused from any environment (hooks, CI, editors, scripts).
"""

from dataclasses import dataclass, field
from pathlib import Path

#: Conventional-commit types accepted by this repository.
ALLOWED_TYPES: frozenset[str] = frozenset(
    {
        "feat",
        "fix",
        "docs",
        "style",
        "refactor",
        "perf",
        "test",
        "build",
        "ci",
        "chore",
        "revert",
    }
)

#: Hard limit (in characters) for a commit subject line.
MAX_SUBJECT_LENGTH: int = 72

#: Soft target (in characters) for a commit subject line.
_SOFT_SUBJECT_LENGTH: int = 50


def _allowed_types_str() -> str:
    """Return a comma-separated, alphabetically-sorted list of allowed types.

    :returns: The allowed types joined with ``", "``.
    :rtype: str
    """
    return ", ".join(sorted(ALLOWED_TYPES))


@dataclass
class CommitMessageCheck:
    """The outcome of validating a commit message.

    :ivar ok: ``True`` when there are no errors (warnings do not affect it).
    :ivar errors: Human-readable error messages (each is a hard violation).
    :ivar warnings: Human-readable warning messages (soft style suggestions).
    """

    ok: bool = False
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def split_subject_body(message: str) -> tuple[str, str]:
    """Split a commit message into its subject and body.

    The subject is the first line (with trailing whitespace stripped). The
    body is everything after the first blank-line separator (the first empty
    line), or the empty string when there is no blank-line separator.

    :param message: The raw commit message.
    :type message: str
    :returns: A ``(subject, body)`` tuple.
    :rtype: tuple[str, str]
    """
    lines = message.split("\n")
    subject = lines[0].rstrip()
    for i in range(1, len(lines)):
        if lines[i] == "":
            return subject, "\n".join(lines[i + 1:])
    return subject, ""


def parse_subject(subject: str) -> tuple[str | None, str | None, str | None]:
    """Parse a ``type(scope)!: description`` style subject.

    Returns ``(commit_type, scope, description)`` when the subject matches the
    conventional-commit pattern and ``(None, None, None)`` otherwise. ``scope``
    is ``None`` when no parenthesized scope is present. An optional ``!``
    before the colon marks a breaking change. The description is the text after
    the ``': '`` (colon plus space) separator, trailing-stripped. A colon that
    is not followed by a space is treated as non-conforming.

    :param subject: The subject line to parse.
    :type subject: str
    :returns: A ``(commit_type, scope, description)`` tuple.
    :rtype: tuple[str | None, str | None, str | None]
    """
    idx = subject.find(": ")
    if idx == -1:
        return None, None, None
    header = subject[:idx]
    description = subject[idx + 2:].rstrip()
    header = header.removesuffix("!")
    if "(" in header or ")" in header:
        if "(" not in header or not header.endswith(")"):
            return None, None, None
        open_idx = header.index("(")
        commit_type = header[:open_idx]
        scope = header[open_idx + 1:-1]
    else:
        commit_type = header
        scope = None
    if commit_type == "":
        return None, None, None
    return commit_type, scope, description


def check_commit_message(
    message: str,
    *,
    max_subject_length: int = MAX_SUBJECT_LENGTH,
) -> CommitMessageCheck:
    """Validate a commit message and accumulate errors and warnings.

    Errors are hard violations that make the message invalid; warnings are
    soft style suggestions that do not affect ``ok``. A message is ``ok`` if
    and only if it produces no errors.

    :param message: The raw commit message to validate.
    :type message: str
    :param max_subject_length: The hard limit for the subject length.
    :type max_subject_length: int
    :returns: The accumulated check result.
    :rtype: CommitMessageCheck
    """
    errors: list[str] = []
    warnings: list[str] = []

    if not message or not message.strip():
        errors.append("Commit message is empty.")
        return CommitMessageCheck(ok=False, errors=errors, warnings=warnings)

    lines = message.split("\n")
    raw_subject = lines[0]
    subject = raw_subject.rstrip()

    if subject == "":
        errors.append("Commit subject (first line) is blank.")
        return CommitMessageCheck(ok=False, errors=errors, warnings=warnings)

    sep_idx = raw_subject.find(": ")
    if sep_idx == -1:
        errors.append(
            "Commit subject is missing the ': ' (colon + space) separator "
            "between the type and the description."
        )
    else:
        header = raw_subject[:sep_idx]
        header = header.removesuffix("!")
        if header.endswith(")") and "(" in header:
            commit_type = header[: header.index("(")]
        else:
            commit_type = header
        if commit_type not in ALLOWED_TYPES:
            errors.append(
                f"Commit type {commit_type!r} is not allowed; "
                f"expected one of: {_allowed_types_str()}."
            )
        description = raw_subject[sep_idx + 2:].rstrip()
        if description == "":
            errors.append(
                "Commit description is empty after the 'type(scope):' separator."
            )
        elif description[0].isupper():
            warnings.append(
                "Commit description should start with a lowercase letter "
                "(imperative mood)."
            )

    if subject.endswith("."):
        errors.append("Commit subject must not end with a period ('.').")

    if len(subject) > max_subject_length:
        errors.append(
            f"Commit subject is {len(subject)} characters long, which exceeds "
            f"the {max_subject_length}-character limit."
        )
    elif len(subject) > _SOFT_SUBJECT_LENGTH:
        warnings.append(
            f"Commit subject is {len(subject)} characters long; consider keeping "
            f"it to {_SOFT_SUBJECT_LENGTH} characters or fewer."
        )

    if len(lines) > 1 and lines[1] != "":
        warnings.append(
            "Commit body should be separated from the subject by a blank line."
        )

    return CommitMessageCheck(ok=len(errors) == 0, errors=errors, warnings=warnings)


def suggest_commit_message(
    changed_paths: list[str],
    *,
    commit_type: str = "feat",
    scope: str | None = None,
    summary: str | None = None,
) -> str:
    """Build a conventional-commit message for the given changed paths.

    When ``summary`` is provided it is used verbatim (with a lowercase first
    letter and no trailing period) as the description; otherwise a short
    description is derived from the paths (``update <basename>`` for a single
    path, ``update N files`` for multiple). The scope is inferred from the
    first changed path's top-level directory (``backend``, ``tests``,
    ``frontend``, or ``webui``) unless an explicit scope is given.

    :param changed_paths: The paths changed by the commit.
    :type changed_paths: list[str]
    :param commit_type: The conventional-commit type to use.
    :type commit_type: str
    :param scope: An explicit scope (overrides inference).
    :type scope: str | None
    :param summary: An explicit description (overrides path derivation).
    :type summary: str | None
    :returns: A conventional-commit message that passes validation.
    :rtype: str
    """
    if summary is not None:
        description = summary.strip()
    elif len(changed_paths) == 1:
        description = f"update {Path(changed_paths[0]).name}"
    else:
        description = f"update {len(changed_paths)} files"

    description = description.rstrip(".")
    if description and description[0].isupper():
        description = description[0].lower() + description[1:]

    if scope is None and changed_paths:
        top = Path(changed_paths[0]).parts[0]
        if top in {"backend", "tests", "frontend", "webui"}:
            scope = top

    if scope:
        return f"{commit_type}({scope}): {description}"
    return f"{commit_type}: {description}"
