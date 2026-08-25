#!/usr/bin/env python3
"""Standalone secret / PII gate for this repository.

Run it over the whole tree (default) or over explicit paths. Exit 1 on any hit,
0 when clean. The GitHub Action runs this BEFORE it commits anything, so a hit
fails the job instead of publishing.

    python3 scripts/leak_check.py            # scan the repo
    python3 scripts/leak_check.py path ...   # scan specific files/dirs
    python3 scripts/leak_check.py --self-test

ALLOWLIST — three mechanisms, all deliberate and all narrow:

1. **Benign shapes, masked before scanning.** Three token shapes are blanked
   out of every line before any detector runs, because this repo publishes them
   deliberately and a detector would otherwise fire on a fragment of one:
   the ``<REDACTED_CATEGORY_N>`` placeholders `scripts/scrub.py` emits; UUIDs,
   which are n8n node ids; and 40- or 64-character lowercase hex digests, which
   are the git and SHA-256 hashes in `exports/manifest.json`. This is shape-based,
   not value-based — it cannot be used to hide a particular secret.
2. **Line marker.** A line containing ``leakcheck:allow`` is skipped. Use it
   for a line that *describes* a shape rather than containing a value, or for a
   known-benign non-personal literal (the CI bot's `users.noreply.github.com`
   commit identity is the only such case in this repo). Always justify it in a
   comment on the same line. Never use it to silence a real value.
3. **Region marker.** Lines between ``leakcheck:allow-region-start`` and
   ``leakcheck:allow-region-end`` are skipped. This exists for exactly one
   reason: the pattern tables in this file and in `scrub.py` spell out the
   shapes they hunt for, and a scanner that flags its own definitions is
   useless. Nothing else in the repo may open a region.

Binary files, `.git/`, and virtualenv/cache directories are skipped.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SKIP_DIRS = {".git", "__pycache__", "node_modules", ".venv", "venv", ".mypy_cache",
             ".pytest_cache", ".ruff_cache"}
SKIP_EXT = {".png", ".jpg", ".jpeg", ".gif", ".pdf", ".zip", ".gz", ".tgz", ".ico",
            ".woff", ".woff2", ".ttf", ".mp4", ".so", ".pyc"}

PLACEHOLDER = re.compile(r"<REDACTED_[A-Z]+_\d+>")
ALLOW_LINE = "leakcheck:allow"
REGION_START = "leakcheck:allow-region-start"
REGION_END = "leakcheck:allow-region-end"

# --- detector table ----------------------------------------------------------
# leakcheck:allow-region-start
CHECKS = (
    ("pem-block", r"-----BEGIN [A-Z ]*(?:PRIVATE KEY|CERTIFICATE)-----"),
    ("jwt", r"eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}"),
    ("openai-key", r"\bsk-(?:proj-|ant-|live-|test-)?[A-Za-z0-9_-]{16,}"),
    ("google-key", r"\bAIza[0-9A-Za-z_-]{30,}"),
    ("github-token", r"\bghp_[A-Za-z0-9]{30,}"),
    ("github-pat", r"\bgithub_pat_[A-Za-z0-9_]{20,}"),
    ("slack-token", r"\bxox[abposr]-[A-Za-z0-9-]{10,}"),
    ("n8n-api-key", r"\bn8n_api_[A-Za-z0-9_-]{16,}"),
    ("bearer-with-value", r"(?i:\bbearer\s+)[A-Za-z0-9._~+/=-]{12,}"),
    ("authorization-header-with-value",
     r"(?i:\bauthorization\s*[\"']?\s*[:=]\s*[\"']?)(?!\s*$)[A-Za-z0-9._~+/=-]{12,}"),
    ("telegram-bot-token", r"\b\d{8,12}:[A-Za-z0-9_-]{30,}"),
    ("google-file-id", r"\b[A-Za-z0-9_-]{28,64}\b"),
    ("email-address", r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
    ("long-digit-run-chat-id", r"(?<![\d.])-?\d{9,}(?![\d.])"),
    ("client-or-case-marker", r"\b(?:MAT|ACT|APR|DRF|EVD|COM)-[A-Za-z0-9][A-Za-z0-9_-]{3,}"),
)
# leakcheck:allow-region-end

# Tokens that are benign *by shape* and are published in this repo on purpose.
# They are masked out of a line before any detector runs, so a detector cannot
# fire on a fragment of one — a SHA-256 digest, for instance, reliably contains
# a nine-digit run and would otherwise trip the chat-id check on every line of
# exports/manifest.json. Masking is length-preserving so reported offsets stay
# meaningful. This is the fourth and last allowlist mechanism, and it is
# shape-based rather than value-based, so it cannot be used to hide a specific
# secret: only a well-formed UUID, a 40/64-char lowercase hex digest, or a
# scrubber placeholder qualifies.
# UUIDs are n8n node ids, not file ids. Checked before google-file-id fires.
UUID = re.compile(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b")
# SHA-256 hex digests and git hashes are published deliberately in the manifest.
HEXDIGEST = re.compile(r"\b[0-9a-f]{40}\b|\b[0-9a-f]{64}\b")

BENIGN_TOKEN = re.compile(
    r"<REDACTED_[A-Z]+_\d+>"
    r"|\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
    r"|\b[0-9a-f]{40}\b|\b[0-9a-f]{64}\b"
)

COMPILED = [(name, re.compile(pat)) for name, pat in CHECKS]


def _benign(name: str, value: str) -> bool:
    if PLACEHOLDER.fullmatch(value):
        return True
    if name == "google-file-id":
        if UUID.fullmatch(value) or HEXDIGEST.fullmatch(value):
            return True
        # A run with no digit and no mixed case is prose, e.g. a long word.
        if value.isalpha() and value.islower():
            return True
    return False


def scan_text(text: str, path: str):
    hits, in_region = [], False
    for lineno, line in enumerate(text.splitlines(), 1):
        if REGION_START in line:
            in_region = True
            continue
        if REGION_END in line:
            in_region = False
            continue
        if in_region or ALLOW_LINE in line:
            continue
        stripped = BENIGN_TOKEN.sub(lambda m: "~" * len(m.group(0)), line)
        for name, rx in COMPILED:
            for m in rx.finditer(stripped):
                val = m.group(0)
                if _benign(name, val):
                    continue
                hits.append((path, lineno, name, val[:18] + ("..." if len(val) > 18 else "")))
                break
    return hits


def iter_files(roots):
    for root in roots:
        if os.path.isfile(root):
            yield root
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
            for fn in sorted(filenames):
                if os.path.splitext(fn)[1].lower() in SKIP_EXT:
                    continue
                yield os.path.join(dirpath, fn)


def scan(roots):
    hits = []
    for path in iter_files(roots):
        try:
            with open(path, "r", encoding="utf-8") as fh:
                text = fh.read()
        except (OSError, UnicodeDecodeError):
            continue
        hits.extend(scan_text(text, path))
    return hits


# --- self test ---------------------------------------------------------------
# leakcheck:allow-region-start
CANARIES = {
    "pem-block": "-----BEGIN RSA PRIVATE KEY-----\nMIIB\n-----END RSA PRIVATE KEY-----",
    "jwt": "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dBjftJeZ4CVPmB92K27uhbUJU1p1r",
    "openai-key": "sk-abcdefghijklmnopqrstuvwxyz0123",
    "google-key": "AIzaSyA0000000000000000000000000000000",
    "github-token": "ghp_0000000000000000000000000000000000",
    "github-pat": "github_pat_00000000000000000000000000",
    "slack-token": "xoxb-0000000000-abcdefghijkl",
    "n8n-api-key": "n8n_api_00000000000000000000",
    "bearer-with-value": "Authorization: Bearer abcdefghijklmnop0123",
    "telegram-bot-token": "1234567890:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
    "google-file-id": "1AbCdEfGhIjKlMnOpQrStUvWxYz0123456789ABCD",
    "email-address": "someone@example.invalid",
    "long-digit-run-chat-id": "1234567890123",
    "client-or-case-marker": "MAT-2026-0042",
}
# leakcheck:allow-region-end


def self_test() -> int:
    tmp = tempfile.mkdtemp(prefix="leakcheck-selftest-")
    failures, passed = [], []
    try:
        for name, canary in CANARIES.items():
            p = os.path.join(tmp, "%s.txt" % name)
            with open(p, "w", encoding="utf-8") as fh:
                fh.write("planted canary follows\n%s\ntrailing\n" % canary)
            found = {h[2] for h in scan([p])}
            if name in found or (name == "bearer-with-value"
                                 and "authorization-header-with-value" in found):  # leakcheck:allow
                passed.append(name)
            else:
                failures.append("%s did NOT fire (detected instead: %s)"
                                % (name, sorted(found) or "nothing"))

        # Negative controls: these must NOT fire.
        neg = os.path.join(tmp, "negative.txt")
        with open(neg, "w", encoding="utf-8") as fh:
            fh.write("placeholder <REDACTED_EMAIL_1> and <REDACTED_FILEID_2>\n"
                     "node id 01234567-89ab-cdef-0123-456789abcdef\n"
                     "sha256 " + "a" * 64 + "\n"
                     "a line with an address but marked  leakcheck:allow  "
                     "someone@example.invalid\n")  # leakcheck:allow
        nhits = scan([neg])
        if nhits:
            failures.append("negative control fired: %s" % nhits)
        else:
            passed.append("negative-controls")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    for name in passed:
        print("  ok    %s" % name)
    for f in failures:
        print("  FAIL  %s" % f)
    print("self-test: %d passed, %d failed (temp dir removed)" % (len(passed), len(failures)))
    return 1 if failures else 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Fail on secrets/PII in the tree.")
    ap.add_argument("paths", nargs="*", default=None)
    ap.add_argument("--self-test", action="store_true",
                    help="plant canaries in a temp dir, assert every category fires, clean up")
    args = ap.parse_args(argv)

    if args.self_test:
        return self_test()

    roots = args.paths or [REPO]
    hits = scan(roots)
    if not hits:
        print("leak-check: clean (%s)" % ", ".join(os.path.relpath(r, REPO) if r != REPO
                                                   else "whole tree" for r in roots))
        return 0
    print("leak-check: %d hit(s) — refusing to proceed" % len(hits), file=sys.stderr)
    for path, lineno, name, sample in hits:
        print("  %s:%d  [%s]  %s" % (os.path.relpath(path, REPO), lineno, name, sample),
              file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
