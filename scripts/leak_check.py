#!/usr/bin/env python3
"""Standalone secret / PII gate for this repository.

Run it over the whole tree (default) or over explicit paths. Exit 1 on any hit,
0 when clean. The GitHub Action runs this BEFORE it commits anything, so a hit
fails the job instead of publishing.

    python3 scripts/leak_check.py            # scan the repo
    python3 scripts/leak_check.py path ...   # scan specific files/dirs
    python3 scripts/leak_check.py --self-test

WHAT CAN SWITCH A CHECK OFF — and what deliberately cannot
----------------------------------------------------------
Nothing in the *content* of a scanned file can disable a detector. Earlier
versions honoured ``leakcheck:allow`` line markers and
``leakcheck:allow-region-start`` / ``-end`` regions found in the text. That was
a hole with teeth: most of what this gate scans is fetched from n8n, and an
n8n sticky note, a ``jsCode`` comment, or an LLM prompt is free-form text an
author controls. A note reading ``leakcheck:allow-region-start`` switched the
scanner off for the remainder of that export — silently, and exactly over the
bytes least likely to have been reviewed. Those mechanisms are gone.

What remains is a single **explicit allowlist held in this file** (``ALLOWLIST``
below): a (path glob, detector name, value regex) triple. All three must match.
The path glob is resolved against this repository, so a file outside the repo
is never allowlisted, and ``exports/**`` may never appear in the table at all —
that rule is asserted at import time, so a future edit that tries to allowlist
captured content fails immediately rather than quietly.

Two shapes are still blanked out of a line before the detectors run, because
they are benign *by shape* and this repo publishes them on purpose:

* the ``<REDACTED_CATEGORY_N>`` placeholders `scripts/scrub.py` emits, and
* UUIDs, which are n8n node ids.

A third, 40/64-character lowercase hex, is masked **only in digest context** —
inside ``exports/manifest.json``, or on a line that also carries a
``sha256``/``hash``/``digest``/``checksum`` key, or on a
``uses: owner/repo@<40 hex>`` Action pin. Blanking hex tree-wide (the
previous behaviour) hid an entire secret format: any 64-hex API key, session
token or HMAC anywhere in a capture vanished before a detector could look at it.

LIMITS YOU MUST KNOW ABOUT
--------------------------
This gate matches **shapes, not meaning**. It cannot recognise a client's name,
a case summary, an opposing party, or a paragraph of advice. n8n sticky notes,
``jsCode`` comments and LLM prompt text are free prose and routinely carry
exactly that. A clean run means "no recognisable secret *shape* was found"; it
never means "no confidential information is present". A human must read the
first sync's diff before merging it. See README.md.

Known limitation, not fixed: a long identifier split across concatenated string
literals or across lines (``"1BxiMVs0XRA5" + "nFMdKvBdBZjgmUUqptlbs"``) is not
reassembled, so it is not detected. Detecting it cheaply and without a flood of
false positives is not possible line-by-line; it is on the human reviewer.

Binary files, `.git/`, and virtualenv/cache directories are skipped.
"""

from __future__ import annotations

import argparse
import fnmatch
import os
import re
import shutil
import sys
import tempfile

# The tree the ALLOWLIST path globs are resolved against. CI runs a trusted copy
# of this script (staged from the default branch) over the sync-branch worktree,
# so the two can differ; locally they are the same. A file outside this root can
# never be allowlisted.
REPO = (os.environ.get("N8N_LEAKCHECK_ROOT", "").strip()
        or os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

SKIP_DIRS = {".git", "__pycache__", "node_modules", ".venv", "venv", ".mypy_cache",
             ".pytest_cache", ".ruff_cache"}
SKIP_EXT = {".png", ".jpg", ".jpeg", ".gif", ".pdf", ".zip", ".gz", ".tgz", ".ico",
            ".woff", ".woff2", ".ttf", ".mp4", ".so", ".pyc"}

PLACEHOLDER = re.compile(r"<REDACTED_[A-Z]+_\d+>")

# --- detector table ----------------------------------------------------------
CHECKS = (
    ("pem-block",
     r"(?i:-----BEGIN [A-Z ]*(?:PRIVATE KEY|CERTIFICATE)(?: BLOCK)?-----)"),
    ("jwt", r"eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}"),
    ("openai-key", r"\bsk-(?:proj-|ant-|live-|test-)?[A-Za-z0-9_-]{16,}"),
    ("google-key", r"\bAIza[0-9A-Za-z_-]{30,}"),
    ("github-token", r"\bghp_[A-Za-z0-9]{30,}"),
    ("github-pat", r"\bgithub_pat_[A-Za-z0-9_]{20,}"),
    ("slack-token", r"\bxox[abposr]-[A-Za-z0-9-]{10,}"),
    ("slack-webhook-url",
     r"https://hooks\.slack\.com/(?:services|workflows)/[A-Za-z0-9/_+-]{8,}"),
    ("discord-webhook-url",
     r"https://discord(?:app)?\.com/api/webhooks/[0-9]+/[A-Za-z0-9._-]{8,}"),
    ("n8n-api-key", r"\bn8n_api_[A-Za-z0-9_-]{16,}"),
    ("bearer-with-value", r"(?i:\bbearer\s+)[A-Za-z0-9._~+/=-]{12,}"),
    ("authorization-header-with-value",
     r"(?i:\bauthorization\s*[\"']?\s*[:=]\s*[\"']?)(?!\s*$)[A-Za-z0-9._~+/=-]{12,}"),
    ("telegram-bot-token", r"\b\d{8,12}:[A-Za-z0-9_-]{30,}"),
    ("google-file-id", r"\b[A-Za-z0-9_-]{28,64}\b"),
    # `%40` is `@` once a URL has been encoded; both spellings are an address.
    ("email-address", r"\b[A-Za-z0-9._%+-]+(?:@|%40)[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
    # A `.` before the run is not a reason to skip it: `chat.9000000001` is a
    # chat id with a key in front of it. Only an adjacent digit is.
    ("long-digit-run-chat-id", r"(?<!\d)-?\d{9,}(?!\d)"),
    # The same identifier written with hyphens or spaces in it. `_enough_digits`
    # then requires >= 10 digits total, so an ISO date cannot trip it.
    ("split-digit-run", r"(?<![\d.-])\d{3,}(?:[ -]\d{2,}){2,}(?![\d.-])"),
    # Client / matter markers: any case, hyphen or slash, plus the bare
    # `<year>/<sequence>` docket spelling. `(?<![\w.])` keeps `github.com/x`
    # from looking like a `COM/...` marker.
    ("client-or-case-marker",
     r"(?<![\w.])(?i:(?:MAT|ACT|APR|DRF|EVD|COM)[-/][A-Za-z0-9][A-Za-z0-9_/-]{3,})"),
    ("client-or-case-marker", r"(?<![\d/])(?:19|20)\d{2}/\d{3,6}(?![\d/])"),
)

# --- explicit allowlist ------------------------------------------------------
# (repo-relative path glob, detector name glob, regex the matched value must
# fullmatch). All three must match. This table is the ONLY way to suppress a
# hit, it lives in version control, and it may never name anything under
# exports/ — captured content does not get to argue for itself.
ALLOWLIST = (
    # The CI bot's commit identity. GitHub's noreply domain, not a person.
    (".github/workflows/n8n-sync.yml", "email-address",
     r"n8n-sync@users\.noreply\.github\.com"),
    # This file and scrub.py spell out the shapes they hunt for, and the
    # self-test plants canaries. A scanner that flags its own pattern table is
    # useless — but the suppression is pinned to these two paths and to values
    # that are visibly synthetic.
    ("scripts/leak_check.py", "*", r".*example\.invalid.*"),
    ("scripts/leak_check.py", "*", r"[^\n]*0{6,}[^\n]*"),
    ("scripts/leak_check.py", "*", r"(?i:.*(?:MAT|EVD)-2026-0042.*)"),
    ("scripts/leak_check.py", "*", r"(?:19|20)\d{2}/00\d{2}"),
    ("scripts/leak_check.py", "*", r"[a-z]{20,64}"),
    ("scripts/leak_check.py", "*", r"(?i:.*(?:BEGIN|END)[A-Z ]*(?:PRIVATE KEY|CERTIFICATE).*)"),
    ("scripts/leak_check.py", "*", r".*hooks\.slack\.com.*"),
    ("scripts/leak_check.py", "*", r"(?:9000000001|900-000-0001-22|9000 0000 0122)"),
    ("scripts/leak_check.py", "*", r"eyJ[A-Za-z0-9_.-]+"),
    ("scripts/leak_check.py", "*", r"1234567890(?:123)?"),
    ("scripts/leak_check.py", "*", r"1AbCdEfGhIjKlMnOpQrStUvWxYz0123456789ABCD"),
    ("scripts/leak_check.py", "*", r"sk-abcdefghijklmnopqrstuvwxyz0123"),
    ("scripts/leak_check.py", "*", r"abcdefghijklmnopqrstuvwx(?:yzab)?"),
    ("scripts/leak_check.py", "*", r"0123456789"),
    ("scripts/leak_check.py", "*", r"dBjftJeZ4CVPmB92K27uhbUJU1p1r"),
    ("scripts/leak_check.py", "*", r"Bearer abcdefghijklmnop0123"),
    ("scripts/leak_check.py", "*", r"1234567890:A+"),
    ("scripts/leak_check.py", "*", r"A{20,64}"),
    ("scripts/leak_check.py", "*", r"n8n-sync@users\.noreply\.github\.com"),
    ("scripts/scrub.py", "*", r".*(?:lawfirm|example)\.example.*"),
    ("scripts/scrub.py", "*", r".*hooks\.slack\.com.*"),
    ("scripts/scrub.py", "*", r"9000000001"),
    ("scripts/scrub.py", "*", r"(?i:.*(?:BEGIN|END)[A-Z ]*(?:PRIVATE KEY|CERTIFICATE).*)"),
)

for _path_glob, _name_glob, _value_re in ALLOWLIST:
    if _path_glob.startswith("exports/") or _path_glob in ("*", "**"):
        raise SystemExit(
            "leak_check.py: refusing to start — ALLOWLIST entry %r would suppress "
            "findings in captured n8n content. That is never permitted."
            % (_path_glob,))

COMPILED = [(name, re.compile(pat)) for name, pat in CHECKS]
_ALLOW = [(p, n, re.compile(v)) for p, n, v in ALLOWLIST]

# Blanked before any detector runs, unconditionally: shapes this repo publishes.
UUID = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b")
HEXDIGEST = re.compile(r"\b[0-9a-f]{40}\b|\b[0-9a-f]{64}\b")
BENIGN_TOKEN = re.compile(
    r"<REDACTED_[A-Z]+_\d+>"
    r"|\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b")
# Only in digest context. See the module docstring (D4).
DIGEST_CONTEXT = re.compile(r"(?i)(?:sha1|sha256|sha512|hash|digest|checksum)")
# A GitHub Action pinned to a commit SHA (`uses: owner/repo@<40 hex>`) is a
# digest too, and pinning is required here, so recognise the shape rather than
# allowlisting each SHA by value.
ACTION_PIN = re.compile(r"uses:\s*[\w.-]+/[\w./-]+@[0-9a-f]{40}\b")
MANIFEST_REL = os.path.join("exports", "manifest.json")

# An identifier-shaped lowercase run (`draft_active_determination`) is prose, not
# a Drive file id. A *contiguous* lowercase run is not exempt: it is exactly what
# a base32-ish token looks like.
IDENTIFIER_WORD = re.compile(r"[a-z]+(?:[_-][a-z]+)+")


def _relpath(path: str) -> str:
    try:
        rel = os.path.relpath(os.path.abspath(path), REPO)
    except ValueError:  # pragma: no cover - different drive on Windows
        return ""
    return "" if rel.startswith("..") else rel.replace(os.sep, "/")


def _allowlisted(rel: str, name: str, value: str) -> bool:
    if not rel:
        return False
    for path_glob, name_glob, value_re in _ALLOW:
        if (fnmatch.fnmatch(rel, path_glob)
                and fnmatch.fnmatch(name, name_glob)
                and value_re.fullmatch(value)):
            return True
    return False


def _enough_digits(value: str) -> bool:
    return sum(c.isdigit() for c in value) >= 10


def _benign(name: str, value: str, digest_ok: bool) -> bool:
    if PLACEHOLDER.fullmatch(value):
        return True
    if name == "split-digit-run" and not _enough_digits(value):
        return True   # an ISO date, a version triple: too few digits to be an id
    if name == "google-file-id":
        if UUID.fullmatch(value):
            return True
        if digest_ok and HEXDIGEST.fullmatch(value):
            return True
        if IDENTIFIER_WORD.fullmatch(value):
            return True
    return False


def scan_text(text: str, path: str):
    rel = _relpath(path)
    manifest = rel == MANIFEST_REL.replace(os.sep, "/")
    hits = []
    for lineno, line in enumerate(text.splitlines(), 1):
        digest_ok = (manifest or bool(DIGEST_CONTEXT.search(line))
                     or bool(ACTION_PIN.search(line)))
        stripped = BENIGN_TOKEN.sub(lambda m: "~" * len(m.group(0)), line)
        if digest_ok:
            stripped = HEXDIGEST.sub(lambda m: "~" * len(m.group(0)), stripped)
        for name, rx in COMPILED:
            for m in rx.finditer(stripped):
                val = m.group(0)
                if _benign(name, val, digest_ok):
                    continue
                if _allowlisted(rel, name, val) or _allowlisted(rel, name, line.strip()):
                    continue
                hits.append((path, lineno, name,
                             val[:18] + ("..." if len(val) > 18 else "")))
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
# One canary per detector, plus one per shape the gate used to miss. A canary is
# a synthetic value: all-zero runs, `example.invalid`, `lawfirm.example`.
CANARIES = {
    # original coverage
    "pem-block": "-----BEGIN RSA PRIVATE KEY-----\nMIIB\n-----END RSA PRIVATE KEY-----",
    "jwt": "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIwMDAwMDAwMDAwIn0.dBjftJeZ4CVPmB92K27uhbUJU1p1r",
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
    # shapes the gate missed before (D8)
    "url-encoded-email": "https://x.example/?to=clerk%40example.invalid",
    "pem-lowercase": "-----begin rsa private key-----\nMIIB\n-----end rsa private key-----",
    "pem-block-suffix": "-----BEGIN PGP PRIVATE KEY BLOCK-----\nxsBN\n-----END PGP PRIVATE KEY BLOCK-----",
    "digit-id-after-dot": "chat.9000000001",
    "hyphen-split-digits": "id 900-000-0001-22",
    "space-split-digits": "id 9000 0000 0122",
    "slack-webhook": "https://hooks.slack.com/services/T00000000/B00000000/abcdefghijklmnopqrstuvwx",
    "lowercase-case-marker": "reference evd-2026-0042 attached",
    "slash-case-marker": "matter 2026/0042 filed",
    "lowercase-alpha-fileid": "fileId: abcdefghijklmnopqrstuvwxyzab",
}

# Must NOT fire. These are the shapes the repo legitimately contains.
NEGATIVE = {
    "placeholder": "to <REDACTED_EMAIL_1> via <REDACTED_FILEID_2>",
    "node-id-uuid": "node id 01234567-89ab-cdef-0123-456789abcdef",
    "digest-in-context": 'sha256_canonical: "' + "a" * 64 + '"',
    "snake-case-identifier": "determination: unavailable_via_public_api",
    "iso-date": "captured on 2026-08-25 at 12:00Z",
    "version-triple": "python 3.11.9 and node 22.22.2",
}

# Must fire even though the text tries to talk its way out of being scanned:
# these are the D3 regression cases.
UNTRUSTED_MARKERS = (
    "leakcheck:allow-region-start",
    "leakcheck:allow",
    "# nosec / noqa / leak-check disabled",
)


def self_test() -> int:
    tmp = tempfile.mkdtemp(prefix="leakcheck-selftest-")
    failures, passed = [], []
    try:
        for name, canary in CANARIES.items():
            p = os.path.join(tmp, "%s.txt" % name)
            with open(p, "w", encoding="utf-8") as fh:
                fh.write("planted canary follows\n%s\ntrailing\n" % canary)
            found = {h[2] for h in scan([p])}
            if found:
                passed.append(name)
            else:
                failures.append("%s did NOT fire" % name)

        for name, text in NEGATIVE.items():
            p = os.path.join(tmp, "neg-%s.txt" % name)
            with open(p, "w", encoding="utf-8") as fh:
                fh.write(text + "\n")
            nhits = scan([p])
            if nhits:
                failures.append("negative control %s fired: %s"
                                % (name, [h[2:] for h in nhits]))
            else:
                passed.append("negative:" + name)

        # D3: content must never be able to switch the scanner off.
        for i, marker in enumerate(UNTRUSTED_MARKERS):
            p = os.path.join(tmp, "untrusted-%d.txt" % i)
            with open(p, "w", encoding="utf-8") as fh:
                fh.write("sticky note says %s\nclerk@example.invalid\n" % marker)
            if scan([p]):
                passed.append("untrusted-marker-ignored:%d" % i)
            else:
                failures.append("content marker %r silenced the scanner" % marker)

        # The allowlist must be inert for files outside the repo.
        p = os.path.join(tmp, "outside.yml")
        with open(p, "w", encoding="utf-8") as fh:
            fh.write('email: n8n-sync@users.noreply.github.com\n')
        if scan([p]):
            passed.append("allowlist-is-path-pinned")
        else:
            failures.append("an allowlist entry applied to a file outside the repo")
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
        print("leak-check matches SHAPES, not meaning: it cannot see a client name or a "
              "case summary in free prose. Read the diff.")
        return 0
    print("leak-check: %d hit(s) — refusing to proceed" % len(hits), file=sys.stderr)
    for path, lineno, name, sample in hits:
        print("  %s:%d  [%s]  %s" % (os.path.relpath(path, REPO), lineno, name, sample),
              file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
