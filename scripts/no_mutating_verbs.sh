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

hits="$(grep -PRn --binary-files=without-match \
        --exclude-dir=.git --exclude-dir=__pycache__ --exclude-dir=node_modules \
        --exclude-dir=.venv --exclude-dir=venv --exclude="$self" \
        "(?=.*${verb})(?=.*${path})" "$root" || true)"

if [ -n "$hits" ]; then
  echo "READ-ONLY GUARANTEE VIOLATED: a mutating HTTP verb appears beside an n8n path." >&2
  echo "$hits" >&2
  exit 1
fi
echo "read-only guard: clean — no mutating verb appears beside an n8n path."
