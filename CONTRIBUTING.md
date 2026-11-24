# Contributing to Starfarer

Thanks for contributing. This document describes the commit message
convention the repository enforces and how to keep your commits (and reviews)
healthy.

## Commit message convention

Every commit message follows the
[Conventional Commits](https://www.conventionalcommits.org/) format:

```
type(scope): description

body
```

- `type` is one of the allowed types listed below.
- `scope` is an optional short identifier for the area of the code you changed
  (for example `engine`, `api`, `generation`, `multiplayer`). The parentheses
  are omitted when there is no scope.
- `description` is a short, imperative summary of what the change does.

### Allowed types

| Type       | Purpose                                              |
|------------|------------------------------------------------------|
| `feat`     | A new feature or user-facing capability               |
| `fix`      | A bug fix                                             |
| `docs`     | Documentation-only changes                            |
| `style`    | Formatting/whitespace with no behavior change         |
| `refactor` | Code restructuring that neither fixes nor adds        |
| `perf`     | A performance improvement                             |
| `test`     | Adding or correcting tests                            |
| `build`    | Build system or external dependency changes           |
| `ci`       | CI configuration changes                              |
| `chore`    | Routine housekeeping that does not touch product code |
| `revert`   | Reverting a previous commit                           |

### Rules

- Use the **imperative mood** and a **lowercase** description (for example
  `add`, not `added` or `Adds`).
- Keep the subject to **50 characters or fewer** as a soft target, and never
  longer than **72 characters** (the hard limit).
- Do **not** end the subject with a period.
- Put a **blank line** between the subject and the body when a body is present.
- Wrap the body at **72 characters**.

### Describing what changed and why

A feature commit should tell a reviewer what the change does and why, in terms
of the product — not just which PR revision it belongs to.

Bad:

```
fix: pr-revision-206-1
```

Good:

```
feat(engine): add sub-surface exploration blocker messages
```

The good example names the affected area (`engine`), describes the concrete
behavior that changed, and gives a reviewer enough context to understand the
commit without opening the diff.

## Installing the hook

A `commit-msg` hook enforces the convention automatically. Install it once:

```bash
./scripts/install-hooks.sh
```

This symlinks `scripts/hooks/commit-msg` into `.git/hooks/commit-msg`, so
future commits are validated before they are recorded. The hook skips merge
commits, `fixup!`/`squash!`/`amend!` rewrites, and git-generated `Revert`
subjects.

## Validating a message manually

To check a message without committing, run the validator directly:

```bash
python -c "from backend.commit_hygiene import check_commit_message; import sys; print(check_commit_message(sys.stdin.read()))"
```

Or from a file:

```bash
python - <<'EOF'
from backend.commit_hygiene import check_commit_message
from pathlib import Path
import sys
result = check_commit_message(Path(sys.argv[1]).read_text())
for e in result.errors:
    print("ERROR:", e)
for w in result.warnings:
    print("WARNING:", w)
sys.exit(0 if result.ok else 1)
EOF
```

The validator is also covered by `tests/test_commit_hygiene.py`.
