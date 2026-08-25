#!/usr/bin/env bash
# Enforce the one-way guarantee mechanically, in CI, on every run.
#
# The repository's promise is that no mutating HTTP verb ever appears next to an
# n8n API path anywhere in the tree — not in code, not commented out, not as a
# worked example. Until now that promise lived only in a docstring, which means
# it held exactly as long as nobody edited the file. This script is the check.
#
#   scripts/no_mutating_verbs.sh [root]      # default root: the repo
#
# Exit 0 = clean. Exit 1 = a mutating verb sits on the same line as an n8n API
# path: fail the job. Both halves must match the file's CONTENT — the two
# lookaheads are applied by a single grep so that a *filename* containing
# "/workflows" (this repo has one) cannot satisfy the path half.
set -uo pipefail

root="${1:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
self="$(basename "${BASH_SOURCE[0]}")"

verb='(?i:\b(?:post|put|patch|delete)\b)'
path='(?:/api/v1|/workflows/|/credentials|/executions|/activate|/deactivate|/archive|/unarchive|/transfer)'

# `.raw/` is excluded for two reasons, both about it not being part of the tree
# this guard is making a promise about. It is gitignored, so nothing in it can
# ever be committed; and it holds raw n8n workflow bodies as single multi-megabyte
# JSON lines, where a node's own `method: POST` sits on the same "line" as every
# `/workflows/` reference in the file. That is a guaranteed false positive on
# captured content, and it makes this PCRE (two lookaheads over a 300KB line)
# take minutes. The guard is about THIS repository's code, not about what n8n
# happens to contain.
hits="$(grep -PRn --binary-files=without-match \
        --exclude-dir=.git --exclude-dir=__pycache__ --exclude-dir=node_modules \
        --exclude-dir=.venv --exclude-dir=venv --exclude-dir=.raw --exclude="$self" \
        "(?=.*${verb})(?=.*${path})" "$root" || true)"

if [ -n "$hits" ]; then
  echo "READ-ONLY GUARANTEE VIOLATED: a mutating HTTP verb appears beside an n8n path." >&2
  echo "$hits" >&2
  exit 1
fi
echo "read-only guard: clean — no mutating verb appears beside an n8n path."
