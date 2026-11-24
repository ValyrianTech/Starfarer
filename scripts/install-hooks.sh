#!/bin/sh
# Install the repository's git hooks into .git/hooks.
#
# Symlinks scripts/hooks/commit-msg into .git/hooks/commit-msg so future
# commits are validated against the conventional-commit convention.

set -e

SCRIPT_DIR=$(dirname "$0")
REPO_ROOT=$(cd "$SCRIPT_DIR/.." && pwd)
HOOKS_SRC="$REPO_ROOT/scripts/hooks"
HOOKS_DST="$REPO_ROOT/.git/hooks"

mkdir -p "$HOOKS_DST"
ln -sf "$HOOKS_SRC/commit-msg" "$HOOKS_DST/commit-msg"
chmod +x "$HOOKS_SRC/commit-msg"

echo "Installed commit-msg hook into .git/hooks/commit-msg."
