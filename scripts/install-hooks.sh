#!/usr/bin/env bash
# install-hooks.sh — symlink versioned hooks into .git/hooks/
# Run once after cloning: bash scripts/install-hooks.sh

set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
HOOKS_SRC="$REPO_ROOT/scripts/git-hooks"
HOOKS_DST="$REPO_ROOT/.git/hooks"

if [ ! -d "$HOOKS_SRC" ]; then
    echo "Error: $HOOKS_SRC not found. Run from repo root." >&2
    exit 1
fi

for hook in "$HOOKS_SRC"/*; do
    name="$(basename "$hook")"
    target="$HOOKS_DST/$name"
    if [ -L "$target" ]; then
        rm "$target"
    elif [ -f "$target" ]; then
        echo "Backing up existing $name to $name.bak"
        mv "$target" "$target.bak"
    fi
    ln -s "$hook" "$target"
    chmod +x "$hook"
    echo "Installed: $name -> $hook"
done

echo "Hooks installed."
