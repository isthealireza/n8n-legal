#!/usr/bin/env python3
"""
scrub.py -- replace real identifiers from a live legal-practice system with
placeholders, in place, across the committed artefacts of this repo.

The literal map lives in .tooling/scrub-map.json so it can be extended without
touching this file.

Properties this script guarantees:

  * IDEMPOTENT. Every replacement is one-way and no replacement value contains
    any key, so running it twice changes nothing on the second pass. The script
    asserts that property before it touches a single file.
  * LONGEST KEY FIRST. A longer literal always wins over a shorter literal that
    happens to be a substring of it.
  * REPORTS PER FILE. Every file that changed is printed with its per-literal
    replacement counts, and a grand total is printed at the end.
  * BYTES ONLY. Files are read and written as UTF-8 text with newlines
    preserved verbatim (newline=''), so JSON stays byte-identical apart from
    the replaced literals. No JSON reserialisation, no reformatting.

Usage:
    .tooling/scrub.py                # scrub in place
    .tooling/scrub.py --dry-run      # report what would change, write nothing
    .tooling/scrub.py --check        # exit 1 if anything would change (CI gate)
"""

import argparse
import glob
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAP_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scrub-map.json")


def load_map():
    with open(MAP_PATH, "r", encoding="utf-8") as fh:
        doc = json.load(fh)
    repl = doc["replacements"]
    targets = doc["targets"]

    # Idempotency proof: no replacement value may contain any key as a substring.
    # If one did, a second pass would rewrite the output of the first.
    for key, val in repl.items():
        for other in repl:
            if other in val:
                sys.exit(
                    "scrub-map is not idempotent: replacement %r for %r contains key %r"
                    % (val, key, other)
                )
    # Longest key first so a longer literal wins over any substring of it.
    order = sorted(repl, key=len, reverse=True)
    return order, repl, targets


def collect(targets):
    files = []
    for pattern in targets:
        for path in glob.glob(os.path.join(ROOT, pattern), recursive=True):
            if os.path.isfile(path):
                files.append(path)
    return sorted(set(files))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true", help="report only, write nothing")
    ap.add_argument("--check", action="store_true",
                    help="write nothing and exit 1 if any replacement is still pending")
    args = ap.parse_args()
    write = not (args.dry_run or args.check)

    order, repl, targets = load_map()
    files = collect(targets)
    if not files:
        sys.exit("no target files matched. patterns: %s" % ", ".join(targets))

    grand = 0
    changed_files = 0
    per_literal = {}

    for path in files:
        with open(path, "r", encoding="utf-8", newline="") as fh:
            text = fh.read()

        counts = {}
        out = text
        for key in order:
            n = out.count(key)
            if n:
                out = out.replace(key, repl[key])
                counts[key] = n
                per_literal[key] = per_literal.get(key, 0) + n

        if not counts:
            continue

        total = sum(counts.values())
        grand += total
        changed_files += 1
        rel = os.path.relpath(path, ROOT)
        print("%-64s %4d" % (rel, total))
        for key in sorted(counts, key=lambda k: (-counts[k], k)):
            print("        %5d  %s -> %s" % (counts[key], key, repl[key]))

        if write:
            with open(path, "w", encoding="utf-8", newline="") as fh:
                fh.write(out)

    print("-" * 72)
    print("%d file(s) scanned, %d file(s) with replacements, %d replacement(s) total"
          % (len(files), changed_files, grand))
    if per_literal:
        print("\nper-literal totals:")
        for key in sorted(per_literal, key=lambda k: (-per_literal[k], k)):
            print("  %5d  %s -> %s" % (per_literal[key], key, repl[key]))
    if grand == 0:
        print("clean: nothing to replace (idempotent no-op)")

    if args.check and grand:
        sys.exit(1)


if __name__ == "__main__":
    main()
