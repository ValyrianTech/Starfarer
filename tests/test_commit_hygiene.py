import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from backend.commit_hygiene import (
    ALLOWED_TYPES,
    MAX_SUBJECT_LENGTH,
    CommitMessageCheck,
    check_commit_message,
    parse_subject,
    split_subject_body,
    suggest_commit_message,
)


class TestSplitSubjectBody:
    def test_single_line_no_body(self) -> None:
        assert split_subject_body("feat: add feature") == ("feat: add feature", "")

    def test_with_body(self) -> None:
        message = "feat: add feature\n\nThis is the body."
        assert split_subject_body(message) == ("feat: add feature", "This is the body.")

    def test_multiple_blank_lines(self) -> None:
        message = "feat: add feature\n\n\nbody after two blank lines"
        assert split_subject_body(message) == ("feat: add feature", "\nbody after two blank lines")

    def test_subject_trailing_whitespace_stripped(self) -> None:
        assert split_subject_body("feat: add feature   \n\nbody") == ("feat: add feature", "body")

    def test_trailing_newline_no_body(self) -> None:
        assert split_subject_body("feat: add feature\n") == ("feat: add feature", "")


class TestParseSubject:
    def test_valid_with_scope(self) -> None:
        assert parse_subject("feat(engine): add warp drive") == ("feat", "engine", "add warp drive")

    def test_valid_without_scope(self) -> None:
        assert parse_subject("feat: add warp drive") == ("feat", None, "add warp drive")

    def test_breaking_with_scope(self) -> None:
        assert parse_subject("feat(engine)!: add warp drive") == ("feat", "engine", "add warp drive")

    def test_breaking_without_scope(self) -> None:
        assert parse_subject("feat!: add warp drive") == ("feat", None, "add warp drive")

    def test_no_colon(self) -> None:
        assert parse_subject("feat add warp drive") == (None, None, None)

    def test_colon_without_space(self) -> None:
        assert parse_subject("feat:add warp drive") == (None, None, None)

    def test_empty_description(self) -> None:
        assert parse_subject("feat: ") == ("feat", None, "")

    def test_malformed_scope_no_closing_paren(self) -> None:
        assert parse_subject("feat(engine: add warp drive") == (None, None, None)

    def test_missing_type(self) -> None:
        assert parse_subject(": add warp drive") == (None, None, None)

    def test_description_trailing_whitespace_stripped(self) -> None:
        assert parse_subject("feat: add warp drive   ") == ("feat", None, "add warp drive")


class TestCheckCommitMessageErrors:
    def test_empty_message(self) -> None:
        result = check_commit_message("")
        assert result.ok is False
        assert any("empty" in e for e in result.errors)

    def test_whitespace_only_message(self) -> None:
        result = check_commit_message("   \n  \n")
        assert result.ok is False
        assert any("empty" in e for e in result.errors)

    def test_blank_subject(self) -> None:
        result = check_commit_message("\nbody without subject")
        assert result.ok is False
        assert any("blank" in e for e in result.errors)

    def test_missing_separator(self) -> None:
        result = check_commit_message("feat add feature")
        assert result.ok is False
        assert any("separator" in e for e in result.errors)

    def test_unknown_type(self) -> None:
        result = check_commit_message("frobnicate: add feature")
        assert result.ok is False
        assert any("frobnicate" in e and "expected one of" in e for e in result.errors)

    def test_missing_type(self) -> None:
        result = check_commit_message(": add feature")
        assert result.ok is False
        assert any("'' is not allowed" in e for e in result.errors)

    def test_empty_description(self) -> None:
        result = check_commit_message("feat: ")
        assert result.ok is False
        assert any("empty" in e for e in result.errors)

    def test_subject_too_long(self) -> None:
        subject = "feat: " + ("a" * (MAX_SUBJECT_LENGTH + 1))
        result = check_commit_message(subject)
        assert result.ok is False
        assert any("exceeds" in e and str(len(subject)) in e for e in result.errors)

    def test_trailing_period(self) -> None:
        result = check_commit_message("feat: add feature.")
        assert result.ok is False
        assert any("period" in e for e in result.errors)

    def test_custom_max_subject_length(self) -> None:
        result = check_commit_message("feat: abcdef", max_subject_length=5)
        assert result.ok is False
        assert any("exceeds" in e for e in result.errors)


class TestCheckCommitMessageWarnings:
    def test_description_starts_uppercase(self) -> None:
        result = check_commit_message("feat: Add feature")
        assert result.ok is True
        assert result.errors == []
        assert any("lowercase" in w for w in result.warnings)

    def test_subject_over_fifty_within_limit(self) -> None:
        subject = "feat: " + ("a" * 55)
        result = check_commit_message(subject)
        assert result.ok is True
        assert result.errors == []
        assert any("consider keeping" in w for w in result.warnings)

    def test_missing_blank_line_before_body(self) -> None:
        result = check_commit_message("feat: add feature\nthis body has no blank line")
        assert result.ok is True
        assert result.errors == []
        assert any("blank line" in w for w in result.warnings)

    def test_blank_line_before_body_no_warning(self) -> None:
        result = check_commit_message("feat: add feature\n\nthis body has a blank line")
        assert result.ok is True
        assert result.warnings == []


class TestCheckCommitMessageValid:
    def test_fully_valid_message(self) -> None:
        result = check_commit_message("feat(engine): add warp drive")
        assert result.ok is True
        assert result.errors == []
        assert result.warnings == []

    def test_breaking_change_marker(self) -> None:
        result = check_commit_message("feat!: add feature")
        assert result.ok is True
        assert result.errors == []

    def test_returns_commit_message_check(self) -> None:
        result = check_commit_message("feat: add feature")
        assert isinstance(result, CommitMessageCheck)


class TestSuggestCommitMessage:
    def test_single_path_infers_scope_and_description(self) -> None:
        message = suggest_commit_message(["backend/game/engine.py"])
        assert message == "feat(backend): update engine.py"

    def test_multiple_paths(self) -> None:
        message = suggest_commit_message(["backend/a.py", "backend/b.py", "backend/c.py"])
        assert message == "feat(backend): update 3 files"

    def test_explicit_summary(self) -> None:
        message = suggest_commit_message(
            ["backend/game/engine.py"],
            summary="Add sub-surface exploration blocker messages.",
        )
        assert message == "feat(backend): add sub-surface exploration blocker messages"

    def test_explicit_scope(self) -> None:
        message = suggest_commit_message(
            ["backend/game/engine.py"],
            scope="engine",
        )
        assert message == "feat(engine): update engine.py"

    def test_no_scope_inferred_for_unknown_top_dir(self) -> None:
        message = suggest_commit_message(["CONTRIBUTING.md"])
        assert message == "feat: update CONTRIBUTING.md"

    def test_empty_paths_with_summary(self) -> None:
        message = suggest_commit_message([], summary="update docs")
        assert message == "feat: update docs"

    def test_custom_commit_type(self) -> None:
        message = suggest_commit_message(["backend/config.py"], commit_type="fix")
        assert message == "fix(backend): update config.py"

    def test_suggestion_passes_check(self) -> None:
        message = suggest_commit_message(
            ["backend/game/engine.py", "backend/config.py"],
            summary="Refine sub-surface exploration blocker messages",
        )
        result = check_commit_message(message)
        assert result.ok is True
        assert result.errors == []


class TestModuleConstants:
    def test_allowed_types_frozenset(self) -> None:
        assert isinstance(ALLOWED_TYPES, frozenset)
        assert "feat" in ALLOWED_TYPES
        assert "fix" in ALLOWED_TYPES
        assert "revert" in ALLOWED_TYPES
        assert "frobnicate" not in ALLOWED_TYPES

    def test_max_subject_length(self) -> None:
        assert MAX_SUBJECT_LENGTH == 72
