"""Pattern-only scrubber for n8n workflow exports.

Design constraints (non-negotiable for this repo):

* **Patterns only.** This module contains no map of real values, no real
  spreadsheet id, no real address, no real chat id. It cannot leak by being
  read, because it knows nothing.
* **Deterministic.** The same input always produces the same output, so the
  SHA-256 of a scrubbed export is stable across runs and drift detection means
  something. Placeholders are numbered by *first appearance* within a single
  document, which keeps them stable without hashing the secret (a hash of a
  low-entropy secret such as an address is itself enumerable).
* **Ordered alternation.** All categories are compiled into one alternation and
  applied in a single pass, so an earlier, more specific category always wins
  over a later, broader one. A UUID branch sits deliberately *ahead* of the
  broad Drive/Sheets file-id branch and maps to itself, because n8n node ids are
  UUIDs and must survive scrubbing intact or every diff becomes noise.

Placeholders look like ``<REDACTED_EMAIL_1>``. `leak_check.py` allowlists that
shape.
"""

from __future__ import annotations

import re
from typing import Dict, Tuple

# --- pattern table -----------------------------------------------------------
# leakcheck:allow-region-start  (this table describes shapes, it contains no secrets)

_IDENTITY = "__IDENTITY__"

# Order matters. First match wins.
PATTERNS: Tuple[Tuple[str, str], ...] = (
    # PEM private/certificate blocks, whole block including body.
    ("PEM", r"-----BEGIN [A-Z ]*(?:PRIVATE KEY|CERTIFICATE)-----[\s\S]*?-----END [A-Z ]*(?:PRIVATE KEY|CERTIFICATE)-----"),
    # JSON Web Tokens.
    ("JWT", r"eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}"),
    # Authorization / bearer header values (the value, not the word).
    ("BEARER", r"(?i:\b(?:bearer|authorization\s*[:=]\s*bearer)\s+)[A-Za-z0-9._~+/=-]{12,}"),
    # Vendor API-key shapes.
    ("APIKEY", r"\bsk-(?:proj-|ant-|live-|test-)?[A-Za-z0-9_-]{16,}"),
    ("APIKEY", r"\bAIza[0-9A-Za-z_-]{30,}"),
    ("APIKEY", r"\bghp_[A-Za-z0-9]{30,}"),
    ("APIKEY", r"\bgithub_pat_[A-Za-z0-9_]{20,}"),
    ("APIKEY", r"\bxox[abposr]-[A-Za-z0-9-]{10,}"),
    ("APIKEY", r"\bn8n_api_[A-Za-z0-9_-]{16,}"),
    # Telegram bot token: <numeric bot id>:<35-ish char secret>.
    ("BOTTOKEN", r"\b\d{8,12}:[A-Za-z0-9_-]{30,}"),
    # Email addresses.
    ("EMAIL", r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
    # UUIDs are n8n node ids. Preserve them, and shadow the broad file-id branch.
    (_IDENTITY, r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"),
    # Google Sheets / Drive file ids: long opaque base64url-ish run.
    ("FILEID", r"\b[A-Za-z0-9_-]{28,64}\b"),
    # Long digit runs: Telegram chat ids, phone-ish identifiers.
    ("CHATID", r"(?<![\d.])-?\d{9,}(?![\d.])"),
)
# leakcheck:allow-region-end

_COMBINED = re.compile(
    "|".join("(?P<G%d>%s)" % (i, pat) for i, (_, pat) in enumerate(PATTERNS))
)
_LABELS = [label for label, _ in PATTERNS]


def scrub_text(text: str) -> Tuple[str, Dict[str, int]]:
    """Return (scrubbed_text, {category: count_of_distinct_values})."""
    seen: Dict[str, Dict[str, str]] = {}

    def repl(m: "re.Match[str]") -> str:
        for i, label in enumerate(_LABELS):
            raw = m.group("G%d" % i)
            if raw is None:
                continue
            if label == _IDENTITY:
                return raw
            bucket = seen.setdefault(label, {})
            if raw not in bucket:
                bucket[raw] = "<REDACTED_%s_%d>" % (label, len(bucket) + 1)
            return bucket[raw]
        return m.group(0)  # pragma: no cover - defensive

    out = _COMBINED.sub(repl, text)
    return out, {k: len(v) for k, v in sorted(seen.items())}


def scrub_obj(obj):
    """Scrub a JSON-serialisable object *structurally*.

    Deliberately NOT done by scrubbing the serialised text: a bare JSON number
    such as a chat id would be replaced by an unquoted placeholder and the
    result would no longer parse. Instead the object is walked, strings and
    dictionary keys are scrubbed as text, and integers whose decimal form
    matches a scrubbed shape become placeholder *strings* (a type change, which
    is correct — the value is no longer a number, it is a redaction marker).

    Returns (scrubbed_obj, {category: distinct_values_seen}).
    """
    seen: Dict[str, Dict[str, str]] = {}

    def placeholder(label: str, raw: str) -> str:
        bucket = seen.setdefault(label, {})
        if raw not in bucket:
            bucket[raw] = "<REDACTED_%s_%d>" % (label, len(bucket) + 1)
        return bucket[raw]

    def text(value: str) -> str:
        def repl(m: "re.Match[str]") -> str:
            for i, label in enumerate(_LABELS):
                raw = m.group("G%d" % i)
                if raw is None:
                    continue
                return raw if label == _IDENTITY else placeholder(label, raw)
            return m.group(0)  # pragma: no cover - defensive

        return _COMBINED.sub(repl, value)

    def walk(node):
        if isinstance(node, dict):
            return {text(str(k)): walk(v) for k, v in node.items()}
        if isinstance(node, list):
            return [walk(v) for v in node]
        if isinstance(node, str):
            return text(node)
        if isinstance(node, bool):
            return node
        if isinstance(node, int):
            as_text = str(node)
            scrubbed = text(as_text)
            return node if scrubbed == as_text else scrubbed
        return node

    out = walk(obj)
    return out, {k: len(v) for k, v in sorted(seen.items())}
