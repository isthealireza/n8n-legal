"""Pattern-only scrubber for n8n workflow exports.

Design constraints (non-negotiable for this repo):

* **Patterns only.** This module contains no map of real values, no real
  spreadsheet id, no real address, no real chat id. It cannot leak by being
  read, because it knows nothing.
* **Ordered alternation.** All categories are compiled into one alternation and
  applied in a single pass, so an earlier, more specific category always wins
  over a later, broader one. A UUID branch sits deliberately *ahead* of the
  broad Drive/Sheets file-id branch and maps to itself, because n8n node ids are
  UUIDs and must survive scrubbing intact or every diff becomes noise.
* **Deterministic *and* order-independent.** See below.

Why placeholders are numbered over the *sorted distinct values*
---------------------------------------------------------------
An earlier version numbered placeholders by **first appearance** in the
document. That is deterministic, but it ties the label to a value's *position*
rather than to the value, and that has two consequences, both wrong:

* **It hides a real change.** If two real values swap places between captures
  — the recipient of one node's mail becomes the recipient of another's — the
  first-seen value is still ``_1`` and the second still ``_2``. The scrubbed
  bytes are identical, the SHA-256 is identical, and drift detection reports
  "nothing changed" about a change that really happened.
* **It fabricates a change.** Reordering keys in a node's parameters, which the
  n8n editor does routinely and which means nothing, reshuffles the numbering
  and rewrites every affected placeholder. The hash moves and the drift report
  claims a body changed when it did not.

So the label has to be derived from the *content* of the set of values, not
from where they appeared. Two options were considered:

1. **A short HMAC/SHA prefix of the real value under a fixed, non-secret salt.**
   Rejected. The salt has to be committed for the scrub to be reproducible, and
   the values this scrubber handles are mostly low entropy — an address, a
   phone-shaped id, a matter number. A committed salt plus a low-entropy domain
   is a rainbow table: anyone reading the repo can enumerate candidates and
   confirm a match. That makes the placeholder reversible, which defeats the
   point of scrubbing.
2. **Ordinals over the sorted distinct values (chosen).** Within a document,
   every distinct value of a category is collected in a first pass, sorted, and
   numbered. The label therefore depends only on the *set* of values, never on
   insertion order. A swap changes which position holds which label, so the
   hash moves. A reorder changes nothing, so the hash holds. The placeholder
   leaks only one bit of ordering information about the underlying set (roughly:
   this value sorts before that one), and nothing that can be inverted to a
   value.

   The honest cost of the choice: adding a *new* value can shift the ordinals of
   the values that sort after it, so one genuine addition can produce more diff
   lines than strictly necessary. That is bounded, visible in review, and always
   errs toward showing a change rather than concealing one — the opposite of the
   failure mode being fixed. It is the right side to err on.

The numbering is per-document, so a value never gains a stable cross-document
identity either, which is also deliberate.

Placeholders look like ``<REDACTED_EMAIL_1>``. `leak_check.py` allowlists that
shape.

Two rules that are not pure shape-matching, and why
---------------------------------------------------
Both were added after this scrubber was first run over **real** captured n8n
bodies rather than over the synthetic fixtures in the self-test. Each fixes a
defect real data exposed and synthetic data could not.

* **Credential ids are collected structurally (`CREDID`).** An n8n node carries
  ``"credentials": {"<type>": {"id": "...", "name": "..."}}``, and that id is
  a live handle to a stored credential on the instance. The ids observed are
  ~16 mixed-case alphanumeric characters — comfortably *below* the 28-character
  floor the Drive/Sheets ``FILEID`` branch needs, and there is no safe shape
  rule that catches a bare 16-character alphanumeric run without also eating
  ordinary identifiers, hashes and words out of every sticky note in the
  document. So the ids are found by **structure** (walk to the ``credentials``
  block, take each entry's ``id``) and then removed by **literal** substitution
  everywhere in the document, prose included. The module still contains no real
  value: it learns the literals from the document it is handed, per document,
  and forgets them.

  The consequence for `scrub_text`, which is handed a bare string and has no
  structure to walk: it cannot do this. That is stated on the function.

* **An elided identifier is redacted (`ELIDEDID`).** A sticky note in a real
  workflow reads ``sheet `0Aa0a0...0000` ``. Six characters of prefix and four
  of suffix are below every length floor in the table, so no shape rule saw it,
  and yet it discloses both ends of a live Google Sheets file id. It is the
  same family as the split-across-string-literals case the README calls out as
  undetected — except this one has a distinctive shape and so can be caught. A
  guard keeps it off ordinary prose: the fragment before the ellipsis must be at
  least five characters and carry both a letter and a digit.

* **A hyphen/space-split digit run needs ten digits, like `leak_check.py`.**
  The ``CHATID`` split branch matched ``2026-08-18`` — three groups, and the
  lookarounds are satisfied — so every ISO date in every capture came out as
  ``<REDACTED_CHATID_1>T07:10:55.430Z``. That is not a leak, it is the opposite:
  a false positive that deletes real, harmless information and makes an export
  look redacted where nothing needed redacting. `leak_check.py` had guarded the
  identical pattern with ``_enough_digits`` (>= 10 digits) from the start and
  this module had not, so the gate and the scrubber disagreed about the same
  regex. They now share the rule.

Self-test:  ``python3 scripts/scrub.py --self-test``
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from typing import Dict, Iterable, List, Tuple

# --- pattern table -----------------------------------------------------------
# This table describes shapes; it contains no secrets. leak_check.py holds an
# explicit path+pattern allowlist for the literals below (see ALLOWLIST there).

_IDENTITY = "__IDENTITY__"

# Order matters. First match wins.
PATTERNS: Tuple[Tuple[str, str], ...] = (
    # PEM private/certificate blocks, whole block including body. Case-insensitive,
    # and tolerant of the "... KEY BLOCK-----" spelling PGP uses.
    ("PEM", r"(?i:-----BEGIN [A-Z ]*(?:PRIVATE KEY|CERTIFICATE)(?: BLOCK)?-----[\s\S]*?-----END [A-Z ]*(?:PRIVATE KEY|CERTIFICATE)(?: BLOCK)?-----)"),
    # JSON Web Tokens.
    ("JWT", r"eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}"),
    # Authorization / bearer header values (the value, not the word).
    ("BEARER", r"(?i:\b(?:bearer|authorization\s*[:=]\s*bearer)\s+)[A-Za-z0-9._~+/=-]{12,}"),
    # Incoming-webhook URLs carry their own authorisation in the path.
    ("WEBHOOK", r"https://hooks\.slack\.com/(?:services|workflows)/[A-Za-z0-9/_+-]{8,}"),
    ("WEBHOOK", r"https://discord(?:app)?\.com/api/webhooks/[0-9]+/[A-Za-z0-9._-]{8,}"),
    # Vendor API-key shapes.
    ("APIKEY", r"\bsk-(?:proj-|ant-|live-|test-)?[A-Za-z0-9_-]{16,}"),
    ("APIKEY", r"\bAIza[0-9A-Za-z_-]{30,}"),
    ("APIKEY", r"\bghp_[A-Za-z0-9]{30,}"),
    ("APIKEY", r"\bgithub_pat_[A-Za-z0-9_]{20,}"),
    ("APIKEY", r"\bxox[abposr]-[A-Za-z0-9-]{10,}"),
    ("APIKEY", r"\bn8n_api_[A-Za-z0-9_-]{16,}"),
    # Telegram bot token: <numeric bot id>:<35-ish char secret>.
    ("BOTTOKEN", r"\b\d{8,12}:[A-Za-z0-9_-]{30,}"),
    # Email addresses, including the %40 form that survives URL encoding.
    ("EMAIL", r"\b[A-Za-z0-9._%+-]+(?:@|%40)[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
    # Client / matter markers, in any case and with either separator.
    ("CASEREF", r"(?i:\b(?:MAT|ACT|APR|DRF|EVD|COM)[-/][A-Za-z0-9][A-Za-z0-9_/-]{3,})"),
    ("CASEREF", r"\b(?:19|20)\d{2}/\d{3,6}\b"),
    # An identifier written with its middle elided: `0Aa0a0...0000`. Found in a
    # real sticky note. Six characters of prefix and four of suffix are far below
    # every length floor here, so nothing else in this table sees it — and it is
    # a partial disclosure of a live Drive file id all the same. Guarded (see
    # `_looks_elided_id`) so ordinary prose ellipses are untouched.
    ("ELIDEDID", r"\b[A-Za-z0-9_-]{4,}(?:\.\.\.|…)[A-Za-z0-9_-]{3,}\b"),
    # UUIDs are n8n node ids. Preserve them, and shadow the broad file-id branch.
    (_IDENTITY, r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"),
    # Google Sheets / Drive file ids: long opaque base64url-ish run.
    ("FILEID", r"\b[A-Za-z0-9_-]{28,64}\b"),
    # Long digit runs: Telegram chat ids, phone-ish identifiers. Also the
    # hyphen- or space-separated spellings of the same thing.
    ("CHATID", r"(?<![\d])-?\d{9,}(?![\d])"),
    ("CHATID", r"(?<![\d.-])\d{3,}(?:[ -]\d{2,}){2,}(?![\d.-])"),
)

def _enough_digits(value: str) -> bool:
    """>= 10 digits. The same test `leak_check.py` applies to the same pattern:
    an ISO date or a version triple is three groups of digits and is not an id."""
    return sum(c.isdigit() for c in value) >= 10


# Per-branch guards, keyed by the branch's own regex source so that reordering
# PATTERNS cannot silently detach a guard from the pattern it belongs to. A
# branch whose guard returns False is treated as if it had not matched.
def _looks_elided_id(value: str) -> bool:
    """True for `0Aa0a0...0000`, false for prose and for code.

    The left-hand fragment must look like an opaque identifier — at least five
    characters carrying BOTH a letter and a digit — which is what separates a
    truncated Drive id from `wait...then`, `TEST...ONLY`, or a numeric range
    like `1...5`. The cost of the guard is that an all-alphabetic elided token
    is not caught; the cost of dropping it would be redacting ordinary prose,
    and this repo's exports are mostly prose.
    """
    left = re.split(r"\.\.\.|…", value, 1)[0]
    return (len(left) >= 5
            and any(c.isdigit() for c in left)
            and any(c.isalpha() for c in left))


_GUARDS = {
    r"(?<![\d.-])\d{3,}(?:[ -]\d{2,}){2,}(?![\d.-])": _enough_digits,
    r"\b[A-Za-z0-9_-]{4,}(?:\.\.\.|…)[A-Za-z0-9_-]{3,}\b": _looks_elided_id,
}

_COMBINED = re.compile(
    "|".join("(?P<G%d>%s)" % (i, pat) for i, (_, pat) in enumerate(PATTERNS))
)
_LABELS = [label for label, _ in PATTERNS]
_BRANCH_GUARDS = [_GUARDS.get(pat) for _, pat in PATTERNS]


def _matched(m: "re.Match[str]") -> Tuple[str, str]:
    """(label, raw) for whichever alternation branch fired.

    A branch with a guard that rejects the value reports `_IDENTITY`, i.e. the
    text is left exactly as it was.
    """
    for i, label in enumerate(_LABELS):
        raw = m.group("G%d" % i)
        if raw is not None:
            guard = _BRANCH_GUARDS[i]
            if guard is not None and not guard(raw):
                return _IDENTITY, raw
            return label, raw
    return _IDENTITY, m.group(0)  # pragma: no cover - defensive


def _collect(texts: Iterable[str]) -> Dict[str, Dict[str, str]]:
    """Pass one: gather the distinct values per category and assign ordinals
    over the *sorted* values, so the label never depends on insertion order."""
    found: Dict[str, set] = {}
    for text in texts:
        for m in _COMBINED.finditer(text):
            label, raw = _matched(m)
            if label != _IDENTITY:
                found.setdefault(label, set()).add(raw)
    return {
        label: {raw: "<REDACTED_%s_%d>" % (label, n)
                for n, raw in enumerate(sorted(values), 1)}
        for label, values in found.items()
    }


def _apply(text: str, table: Dict[str, Dict[str, str]]) -> str:
    def repl(m: "re.Match[str]") -> str:
        label, raw = _matched(m)
        if label == _IDENTITY:
            return raw
        return table[label][raw]
    return _COMBINED.sub(repl, text)


def scrub_text(text: str) -> Tuple[str, Dict[str, int]]:
    """Return (scrubbed_text, {category: count_of_distinct_values}).

    Shape rules only. A bare string carries no structure, so the ``CREDID``
    rule — which finds credential ids by walking to a node's ``credentials``
    block — cannot apply here. Use `scrub_obj` for anything that is a workflow
    body; this is for fragments (a diff value, a log line).
    """
    table = _collect([text])
    return _apply(text, table), {k: len(v) for k, v in sorted(table.items())}


# --- structural rule: credential ids -----------------------------------------
# See the module docstring. This is the one thing here that is not a shape: an
# n8n credential id is a ~16-character alphanumeric run with no distinguishing
# form, so it is located by where it sits rather than by what it looks like.
CREDID_LABEL = "CREDID"


def _credential_ids(node, out: set) -> None:
    """Collect every ``credentials.<type>.id`` string in the document.

    Also picks up a bare ``credentialId``/``credential_id`` value, which some
    node parameter shapes use instead of the nested block.
    """
    if isinstance(node, dict):
        creds = node.get("credentials")
        if isinstance(creds, dict):
            for entry in creds.values():
                if isinstance(entry, dict) and isinstance(entry.get("id"), str) \
                        and entry["id"].strip():
                    out.add(entry["id"])
        for key, value in node.items():
            if key in ("credentialId", "credential_id") and isinstance(value, str) \
                    and value.strip():
                out.add(value)
            _credential_ids(value, out)
    elif isinstance(node, list):
        for value in node:
            _credential_ids(value, out)


def _literal_table(values) -> Dict[str, str]:
    """Ordinals over the sorted distinct values, exactly as `_collect` does."""
    return {raw: "<REDACTED_%s_%d>" % (CREDID_LABEL, n)
            for n, raw in enumerate(sorted(values), 1)}


def _literal_re(table: Dict[str, str]):
    if not table:
        return None
    # Longest first, so one id that is a prefix of another cannot shadow it.
    return re.compile("|".join(re.escape(v) for v in
                               sorted(table, key=len, reverse=True)))


def _apply_literals(text: str, rx, table: Dict[str, str]) -> str:
    if rx is None:
        return text
    return rx.sub(lambda m: table[m.group(0)], text)


def _strings(node) -> Iterable[str]:
    """Every string the scrubber will look at, for the collection pass."""
    if isinstance(node, dict):
        for k, v in node.items():
            yield str(k)
            yield from _strings(v)
    elif isinstance(node, list):
        for v in node:
            yield from _strings(v)
    elif isinstance(node, str):
        yield node
    elif isinstance(node, bool):
        return
    elif isinstance(node, int):
        yield str(node)


def scrub_obj(obj):
    """Scrub a JSON-serialisable object *structurally*.

    Deliberately NOT done by scrubbing the serialised text: a bare JSON number
    such as a chat id would be replaced by an unquoted placeholder and the
    result would no longer parse. Instead the object is walked, strings and
    dictionary keys are scrubbed as text, and integers whose decimal form
    matches a scrubbed shape become placeholder *strings* (a type change, which
    is correct — the value is no longer a number, it is a redaction marker).

    Two passes: collect every distinct value first so the ordinals are decided
    over the whole document's sorted value set, then substitute. See the module
    docstring for why the label must not depend on document order.

    Returns (scrubbed_obj, {category: distinct_values_seen}).
    """
    # Structural pass first: learn this document's credential ids, then remove
    # them by literal substitution BEFORE the shape rules run, so an id that
    # also happens to satisfy a broader shape cannot be labelled twice.
    cred_values: set = set()
    _credential_ids(obj, cred_values)
    creds = _literal_table(cred_values)
    cred_rx = _literal_re(creds)

    def pre(text: str) -> str:
        return _apply_literals(text, cred_rx, creds)

    table = _collect(pre(s) for s in _strings(obj))

    def sub(text: str) -> str:
        return _apply(pre(text), table)

    def walk(node):
        if isinstance(node, dict):
            return {sub(str(k)): walk(v) for k, v in node.items()}
        if isinstance(node, list):
            return [walk(v) for v in node]
        if isinstance(node, str):
            return sub(node)
        if isinstance(node, bool):
            return node
        if isinstance(node, int):
            as_text = str(node)
            scrubbed = sub(as_text)
            return node if scrubbed == as_text else scrubbed
        return node

    counts = {k: len(v) for k, v in sorted(table.items())}
    if creds:
        counts[CREDID_LABEL] = len(creds)
    return walk(obj), dict(sorted(counts.items()))


# --- self test ---------------------------------------------------------------
def _canon_hash(obj) -> str:
    out, _ = scrub_obj(obj)
    return hashlib.sha256(
        json.dumps(out, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def self_test() -> int:
    A, B = "alice@lawfirm.example", "bob@lawfirm.example"
    failures: List[str] = []
    passed: List[str] = []

    # 1. Swapping two real values MUST change the hash (a real change is visible).
    h1 = _canon_hash({"nodes": [{"to": A}, {"to": B}]})
    h2 = _canon_hash({"nodes": [{"to": B}, {"to": A}]})
    (passed if h1 != h2 else failures).append(
        "swap-changes-hash" if h1 != h2 else
        "swap-changes-hash: swapping two values left the hash identical")

    # 2. Reordering keys MUST NOT change the hash (no fabricated drift).
    r1 = _canon_hash({"alpha": A, "beta": B})
    r2 = _canon_hash({"beta": B, "alpha": A})
    (passed if r1 == r2 else failures).append(
        "reorder-keeps-hash" if r1 == r2 else
        "reorder-keeps-hash: a pure key reorder moved the hash")

    # 3. Stable across repeated runs in the same process and across documents
    #    with the same value set in a different order.
    r3 = _canon_hash({"beta": B, "alpha": A})
    (passed if r2 == r3 else failures).append(
        "stable-across-runs" if r2 == r3 else "stable-across-runs: not deterministic")

    # 4. Ordinals follow sorted order, not first appearance.
    out, _ = scrub_obj({"first": B, "second": A})
    ok = out["first"] == "<REDACTED_EMAIL_2>" and out["second"] == "<REDACTED_EMAIL_1>"
    (passed if ok else failures).append(
        "ordinals-are-sorted" if ok else
        "ordinals-are-sorted: got %r" % out)

    # 5. Node-id UUIDs survive intact.
    uid = "01234567-89ab-cdef-0123-456789abcdef"
    out, _ = scrub_obj({"id": uid})
    (passed if out["id"] == uid else failures).append(
        "uuid-preserved" if out["id"] == uid else "uuid-preserved: node id was mangled")

    # 6. An integer chat id becomes a placeholder string.
    out, _ = scrub_obj({"chatId": 9000000001})
    ok = isinstance(out["chatId"], str) and out["chatId"].startswith("<REDACTED_CHATID_")
    (passed if ok else failures).append(
        "int-chatid-redacted" if ok else "int-chatid-redacted: got %r" % out["chatId"])

    # 7. An ISO date is NOT a chat id. This fired on real data: every
    #    createdAt/updatedAt came back as <REDACTED_CHATID_n>T07:10:55.430Z.
    out, _ = scrub_obj({"createdAt": "2026-08-18T07:10:55.430Z"})
    ok = out["createdAt"] == "2026-08-18T07:10:55.430Z"
    (passed if ok else failures).append(
        "iso-date-survives" if ok else "iso-date-survives: got %r" % out["createdAt"])

    # 8. ...but a genuinely split long id still goes. Same rule as leak_check.
    out, _ = scrub_obj({"x": "id 900-000-0001-22"})
    ok = "<REDACTED_CHATID_" in out["x"]
    (passed if ok else failures).append(
        "split-long-id-still-redacted" if ok else
        "split-long-id-still-redacted: got %r" % out["x"])

    # 8b. An elided identifier. A real sticky note carried exactly this shape:
    #     a Sheets file id with its middle replaced by an ellipsis. The value
    #     here is synthetic, like every other value in this file.
    out, _ = scrub_obj({"note": "sheet `0Aa0a0...0000` is hardcoded"})
    ok = "0Aa0a0" not in out["note"] and "<REDACTED_ELIDEDID_1>" in out["note"]
    (passed if ok else failures).append(
        "elided-id-redacted" if ok else "elided-id-redacted: got %r" % out["note"])

    # 8c. ...but prose and code ellipses are not identifiers.
    keep = {"a": "ACT-...-003", "b": "wait...then", "c": "1...5",
            "d": "const x = [...items];"}
    out, _ = scrub_obj(keep)
    ok = all(out[k] == v for k, v in keep.items())
    (passed if ok else failures).append(
        "prose-ellipsis-survives" if ok else "prose-ellipsis-survives: got %r" % out)

    # 9. A credential id is structural, not shape-matched: too short for the
    #    file-id branch, and it survived verbatim until this rule existed.
    doc = {"nodes": [
        {"name": "A", "credentials": {"googleSheetsOAuth2Api":
                                      {"id": "AbCdEfGhIjKlMnOp", "name": "acct"}}},
        {"name": "B", "notes": "see credential AbCdEfGhIjKlMnOp"}]}
    out, counts = scrub_obj(doc)
    text = json.dumps(out)
    ok = ("AbCdEfGhIjKlMnOp" not in text
          and "<REDACTED_CREDID_1>" in text
          and counts.get("CREDID") == 1)
    (passed if ok else failures).append(
        "credential-id-redacted" if ok else
        "credential-id-redacted: got %s" % text)

    # 10. Credential-id ordinals are sorted too, and the same id in prose gets
    #     the same label as the one in the credentials block.
    out, _ = scrub_obj({"nodes": [
        {"credentials": {"t": {"id": "zzzzzzzzzzzzzzzz"}}},
        {"credentials": {"t": {"id": "aaaaaaaaaaaaaaaa"}}}]})
    ok = (out["nodes"][0]["credentials"]["t"]["id"] == "<REDACTED_CREDID_2>"
          and out["nodes"][1]["credentials"]["t"]["id"] == "<REDACTED_CREDID_1>")
    (passed if ok else failures).append(
        "credid-ordinals-are-sorted" if ok else
        "credid-ordinals-are-sorted: got %r" % out)

    for name in passed:
        print("  ok    %s" % name)
    for f in failures:
        print("  FAIL  %s" % f)
    print("scrub self-test: %d passed, %d failed" % (len(passed), len(failures)))
    return 1 if failures else 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Pattern-only scrubber (self-test entry point).")
    ap.add_argument("--self-test", action="store_true",
                    help="assert placeholder labels are content-derived and stable")
    args = ap.parse_args(argv)
    if args.self_test:
        return self_test()
    ap.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
