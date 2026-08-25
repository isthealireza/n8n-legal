#!/usr/bin/env python3
"""One-way sync: n8n public REST API  ->  this repository.

**Direction is one-way and enforced structurally.** The only function in this
file that touches the network is `_get()`, and `_get()` asserts its method is
GET before it opens a connection. There is no write path to n8n here, not even
a disabled one. This script also never reads from GitHub.

Environment:
    N8N_BASE_URL   e.g. https://<your-instance>.app.n8n.cloud   (no trailing /api/v1)
    N8N_API_KEY    an n8n API key, sent as the X-N8N-API-KEY header

The API key is never printed: not in the summary, not in an error, not in a URL
(it travels only as a header), not under --debug.

Exit codes:
    0  success
    2  missing/invalid environment or config
    3  network / API failure
    4  wrote nothing because the API returned an unusable shape
"""

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from scrub import scrub_obj  # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG = os.path.join(REPO, "config", "workflows.json")
ACTIVE_DIR = os.path.join(REPO, "exports", "active")
DRAFT_DIR = os.path.join(REPO, "exports", "draft")
MANIFEST = os.path.join(REPO, "exports", "manifest.json")
DRIFT = os.path.join(REPO, "docs", "drift-report.md")

MANIFEST_SCHEMA_VERSION = 1
TIMEOUT = 30

# The only HTTP verb this program is permitted to use, anywhere, ever.
ALLOWED_METHOD = "GET"


class SyncError(Exception):
    def __init__(self, msg: str, code: int = 3):
        super().__init__(msg)
        self.code = code


# --------------------------------------------------------------------------
# network — this is the entire network surface of the program
# --------------------------------------------------------------------------
def _get(base_url: str, api_key: str, path: str, params: dict | None = None):
    """The ONLY network function. GET only, by assertion.

    `path` is appended to <base_url>/api/v1. The api key goes in a header and
    is never interpolated into the URL or into any message this function
    raises.
    """
    method = ALLOWED_METHOD
    assert method == "GET", "sync.py is read-only against n8n; only GET is permitted"

    url = base_url.rstrip("/") + "/api/v1" + path
    if params:
        url += "?" + urllib.parse.urlencode(params)

    req = urllib.request.Request(url, method=method)
    assert req.get_method() == "GET", "refusing a non-GET request to n8n"
    req.add_header("X-N8N-API-KEY", api_key)
    req.add_header("Accept", "application/json")
    req.add_header("User-Agent", "n8n-legal-sync/1 (read-only)")

    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            body = resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:  # no key in the message: url has none
        raise SyncError("GET %s -> HTTP %s %s" % (path, e.code, e.reason))
    except urllib.error.URLError as e:
        raise SyncError("GET %s -> network error: %s" % (path, e.reason))
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        raise SyncError("GET %s -> response was not JSON" % path)


# --------------------------------------------------------------------------
# hashing
# --------------------------------------------------------------------------
def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _canonical(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _pretty(obj) -> str:
    return json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


# --------------------------------------------------------------------------
# draft / active determination
# --------------------------------------------------------------------------
def classify(wf: dict) -> dict:
    """Decide what this instance's API actually told us about draft vs active.

    The public API's workflow object carries a top-level `versionId` (described
    upstream as the current version, used for optimistic locking) and may carry
    an `activeVersion` object holding the published version's own `versionId`,
    `nodes` and `connections`. Where `activeVersion` is present we can state the
    distinction. Where it is absent — an older instance, or an edition without
    workflow publishing — we must NOT invent one.
    """
    draft_vid = wf.get("versionId")
    av = wf.get("activeVersion")
    if isinstance(av, dict) and av.get("versionId"):
        return {
            "determination": "from_active_version_object",
            "draft_version_id": draft_vid,
            "active_version_id": av.get("versionId"),
            "diverged": bool(draft_vid) and av.get("versionId") != draft_vid,
        }
    return {
        "determination": "unavailable_via_public_api",
        "draft_version_id": draft_vid,
        "active_version_id": None,
        "diverged": None,
        "note": (
            "This instance's public API returned no populated `activeVersion` "
            "object, so published-vs-draft cannot be distinguished from what it "
            "gave us. The single body captured under exports/active/ is whatever "
            "GET /workflows/{id} returned; it is NOT asserted to be the published "
            "version. See docs/API_CAPABILITIES.md."
        ),
    }


def _body_from_active_version(wf: dict, av: dict) -> dict:
    """Published body = workflow envelope with the activeVersion graph swapped in."""
    body = {k: v for k, v in wf.items() if k not in ("activeVersion",)}
    for key in ("nodes", "connections", "nodeGroups"):
        if key in av and av[key] is not None:
            body[key] = av[key]
    body["versionId"] = av.get("versionId")
    return body


def _envelope(key: str, cfg: dict, kind: str, body: dict, cls: dict, captured_at: str,
              scrub_stats: dict) -> dict:
    return {
        "_capture": {
            "key": key,
            "workflow_id": cfg["id"],
            "workflow_name": cfg["name"],
            "kind": kind,  # "active" | "draft" | "unknown"
            "captured_at": captured_at,
            "source": "n8n public REST API GET /api/v1/workflows/{id} (read-only)",
            "draft_active_determination": cls["determination"],
            "draft_version_id": cls["draft_version_id"],
            "active_version_id": cls["active_version_id"],
            "scrubbed": True,
            "scrub_counts": scrub_stats,
        },
        "workflow": body,
    }


# --------------------------------------------------------------------------
# manifest / drift
# --------------------------------------------------------------------------
def _load_prev_manifest() -> dict:
    try:
        with open(MANIFEST, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        return {}


def write_drift(prev: dict, new: dict) -> list:
    prev_wf = (prev or {}).get("workflows", {})
    new_wf = new.get("workflows", {})
    lines, changes = [], []

    for key in sorted(set(prev_wf) | set(new_wf)):
        p, n = prev_wf.get(key), new_wf.get(key)
        if p is None:
            changes.append("%s: first capture" % key)
            continue
        if n is None:
            changes.append("%s: no longer configured / not captured this run" % key)
            continue
        for kind in ("active", "draft"):
            ph = (p.get(kind) or {}).get("sha256_canonical")
            nh = (n.get(kind) or {}).get("sha256_canonical")
            if ph == nh:
                continue
            if ph is None:
                changes.append("%s: %s body appeared" % (key, kind))
            elif nh is None:
                changes.append("%s: %s body disappeared (draft caught up to published?)" % (key, kind))
            else:
                changes.append("%s: %s body changed" % (key, kind))

    lines.append("# Drift report")
    lines.append("")
    lines.append("Generated by `scripts/sync.py` at %s." % new.get("captured_at"))
    lines.append("")
    lines.append("Previous sync: %s" % (prev.get("captured_at") or "_none — this is the first sync_"))
    lines.append("")
    lines.append("Draft/active determination this run: `%s`." % new.get("api_capability"))
    lines.append("")
    if changes:
        lines.append("## Changed since last sync")
        lines.append("")
        for c in changes:
            lines.append("- %s" % c)
    else:
        lines.append("## Changed since last sync")
        lines.append("")
        lines.append("- Nothing. Every captured body hashes identically to the previous sync.")
    lines.append("")
    lines.append("## Per-workflow state")
    lines.append("")
    lines.append("| key | name | active sha256 (canonical, first 12) | draft present | draft sha256 (first 12) |")
    lines.append("|---|---|---|---|---|")
    for key in sorted(new_wf):
        e = new_wf[key]
        a = (e.get("active") or {}).get("sha256_canonical")
        d = (e.get("draft") or {}).get("sha256_canonical")
        lines.append("| %s | %s | `%s` | %s | %s |" % (
            key, e.get("name", ""), (a or "-")[:12], "yes" if d else "no",
            "`%s`" % d[:12] if d else "-"))
    lines.append("")

    os.makedirs(os.path.dirname(DRIFT), exist_ok=True)
    with open(DRIFT, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
    return changes


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------
def load_config() -> dict:
    try:
        with open(CONFIG, "r", encoding="utf-8") as fh:
            cfg = json.load(fh)
    except OSError as e:
        raise SyncError("cannot read %s: %s" % (CONFIG, e), code=2)
    except json.JSONDecodeError as e:
        raise SyncError("%s is not valid JSON: %s" % (CONFIG, e), code=2)
    wfs = cfg.get("workflows")
    if not isinstance(wfs, dict) or not wfs:
        raise SyncError("config has no `workflows` object", code=2)
    for key, entry in wfs.items():
        if not isinstance(entry, dict) or not entry.get("id"):
            raise SyncError("config entry %s has no id" % key, code=2)
    return cfg


def read_env(required: bool):
    base = os.environ.get("N8N_BASE_URL", "").strip()
    key = os.environ.get("N8N_API_KEY", "").strip()
    missing = [n for n, v in (("N8N_BASE_URL", base), ("N8N_API_KEY", key)) if not v]
    if missing and required:
        raise SyncError(
            "missing required environment variable(s): %s. "
            "Set them and re-run; the key is read from the environment only and "
            "is never written to disk or logged." % ", ".join(missing),
            code=2,
        )
    return base, key, missing


def run(args) -> int:
    cfg = load_config()
    wfs = cfg["workflows"]
    base, key, missing = read_env(required=not args.dry_run)

    if args.dry_run:
        print("DRY RUN — no network call will be made.")
        print("config          : ok, %d workflows (%s)" % (len(wfs), ", ".join(sorted(wfs))))
        for name in ("N8N_BASE_URL", "N8N_API_KEY"):
            print("env %-13s: %s" % (name, "absent (a real run would exit 2)"
                                     if name in missing else "present (value not shown)"))
        if base:
            print("would GET       : %s/api/v1/workflows/<id>  [GET only]" % base.rstrip("/"))
        else:
            print("would GET       : <N8N_BASE_URL>/api/v1/workflows/<id>  [GET only]")
        print("would write     : exports/active/<KEY>.json, exports/manifest.json, docs/drift-report.md")
        print("write calls to n8n: none, by construction (single _get() helper, GET asserted)")
        return 0

    captured_at = _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    prev = _load_prev_manifest()
    manifest = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "captured_at": captured_at,
        "source": "n8n public REST API /api/v1 (GET only)",
        "api_capability": None,
        "workflows": {},
    }

    os.makedirs(ACTIVE_DIR, exist_ok=True)
    os.makedirs(DRAFT_DIR, exist_ok=True)

    capability = None
    written, skipped = 0, []

    for wf_key in sorted(wfs):
        entry = wfs[wf_key]
        wf = _get(base, key, "/workflows/%s" % urllib.parse.quote(entry["id"]),
                  {"excludePinnedData": "true"})
        if not isinstance(wf, dict) or "nodes" not in wf:
            skipped.append(wf_key)
            continue

        cls = classify(wf)
        capability = capability or cls["determination"]
        rec = {"name": entry.get("name"), "id": entry["id"],
               "determination": cls["determination"],
               "draft_version_id": cls["draft_version_id"],
               "active_version_id": cls["active_version_id"],
               "active": None, "draft": None}

        av = wf.get("activeVersion")
        if cls["determination"] == "from_active_version_object":
            active_body = _body_from_active_version(wf, av)
            bodies = [("active", active_body, ACTIVE_DIR)]
            if cls["diverged"]:
                draft_body = {k: v for k, v in wf.items() if k != "activeVersion"}
                bodies.append(("draft", draft_body, DRAFT_DIR))
            else:
                stale = os.path.join(DRAFT_DIR, "%s.json" % wf_key)
                if os.path.exists(stale):
                    os.remove(stale)
        else:
            # Honest fallback: we do not know which side of the line this is.
            bodies = [("unknown", {k: v for k, v in wf.items() if k != "activeVersion"},
                       ACTIVE_DIR)]

        for kind, body, outdir in bodies:
            scrubbed, stats = scrub_obj(body)
            env = _envelope(wf_key, entry, kind, scrubbed, cls, captured_at, stats)
            text = _pretty(env)
            path = os.path.join(outdir, "%s.json" % wf_key)
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(text)
            written += 1
            slot = "draft" if kind == "draft" else "active"
            rec[slot] = {
                "kind": kind,
                "path": os.path.relpath(path, REPO),
                "sha256_body": _sha(_pretty(scrubbed)),
                "sha256_canonical": _sha(_canonical(scrubbed)),
            }

        manifest["workflows"][wf_key] = rec

    manifest["api_capability"] = capability or "unavailable_via_public_api"

    if not manifest["workflows"]:
        print("ERROR: the API returned no usable workflow bodies; nothing written.",
              file=sys.stderr)
        return 4

    with open(MANIFEST, "w", encoding="utf-8") as fh:
        fh.write(_pretty(manifest))
    changes = write_drift(prev, manifest)

    print("n8n -> repo sync complete (read-only against n8n).")
    print("  captured_at        : %s" % captured_at)
    print("  workflows captured : %d of %d" % (len(manifest["workflows"]), len(wfs)))
    print("  files written      : %d" % written)
    print("  draft/active       : %s" % manifest["api_capability"])
    print("  drift              : %s" % ("%d change(s), see docs/drift-report.md" % len(changes)
                                         if changes else "none"))
    if skipped:
        print("  skipped (bad shape): %s" % ", ".join(skipped))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Read-only n8n -> repo sync. Never writes to n8n.")
    ap.add_argument("--dry-run", action="store_true",
                    help="validate config and environment handling; makes no network call")
    args = ap.parse_args(argv)
    try:
        return run(args)
    except SyncError as e:
        print("ERROR: %s" % e, file=sys.stderr)
        return e.code


if __name__ == "__main__":
    raise SystemExit(main())
