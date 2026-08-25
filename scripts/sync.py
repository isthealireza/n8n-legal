#!/usr/bin/env python3
"""One-way sync: n8n public REST API  ->  this repository.

**Direction is one-way and enforced structurally.** The only function in this
file that touches the network is `_get()`. It raises — it does not `assert` —
if its method is anything but GET, so the guarantee survives `python3 -O`,
which strips assertions. There is no write path to n8n here, not even a
disabled one, and CI re-checks that with `scripts/no_mutating_verbs.sh`. This
script also never reads from GitHub.

Environment:
    N8N_BASE_URL   e.g. https://<your-instance>.app.n8n.cloud   (no trailing /api/v1)
    N8N_API_KEY    an n8n API key, sent as the X-N8N-API-KEY header

How the API key is protected
----------------------------
The key is never printed: not in the summary, not in an error, not in a URL
(it travels only as a header). Beyond that, three rules keep it from travelling
anywhere it was not meant to go:

1. **`N8N_BASE_URL` must be `https://`.** The single exception is a loopback
   host — `http://localhost` or `http://127.0.0.1` — where there is no network
   segment to sniff. Any other `http://` URL is refused before a socket is
   opened. A plaintext base URL means the key crosses the wire in the clear.
2. **Redirects are refused outright.** `urlopen`'s default opener replays every
   request header, including `X-N8N-API-KEY`, at whatever host a `Location:`
   names — over plaintext if the redirect says so. A single `302` from a
   misconfigured proxy, or from anyone who can answer for the configured host,
   is enough to hand the live key to a third party and have the reply accepted
   as a genuine workflow body. This module installs an opener whose redirect
   handler raises instead.
3. **The responding host is checked** against the configured host, so even a
   handler bug cannot let a response from somewhere else be trusted.

Response bodies are read with a hard size cap (see MAX_RESPONSE_BYTES).

Exit codes:
    0  success
    2  missing/invalid environment or config
    3  network / API failure (nothing usable captured)
    4  wrote nothing because the API returned an unusable shape
    5  PARTIAL capture — some workflows captured, at least one failed
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

# Where this script and its config live: the *trusted* copy. In CI that is a
# staging directory taken from the default-branch checkout, never the
# sync-branch worktree — see the ordering note in .github/workflows/n8n-sync.yml.
SOURCE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# Where captured output is written. In CI this is the sync-branch worktree, so
# trusted code writes into an untrusted tree rather than being run from one.
# Locally the two are the same directory and nothing changes.
REPO = os.environ.get("N8N_SYNC_OUTPUT_ROOT", "").strip() or SOURCE_ROOT
CONFIG = os.path.join(SOURCE_ROOT, "config", "workflows.json")
ACTIVE_DIR = os.path.join(REPO, "exports", "active")
DRAFT_DIR = os.path.join(REPO, "exports", "draft")
MANIFEST = os.path.join(REPO, "exports", "manifest.json")
# Timestamps live here and NOWHERE else. This file is gitignored: writing the
# wall clock into a tracked file made every scheduled run a content change, so
# the job committed and force-pushed ~96x/day and kept a pull request open
# claiming things had changed when nothing had. Tracked output is derived from
# the captured content alone.
LASTRUN = os.path.join(REPO, "exports", "last-run.json")
DRIFT = os.path.join(REPO, "docs", "drift-report.md")

MANIFEST_SCHEMA_VERSION = 2
TIMEOUT = 30
# A workflow body is a few hundred KB at the outside. Anything past this is a
# broken or hostile endpoint, and reading it would be an easy way to exhaust
# the runner's memory.
MAX_RESPONSE_BYTES = 8 * 1024 * 1024

# The only HTTP verb this program is permitted to use, anywhere, ever.
ALLOWED_METHOD = "GET"

# Plain http is tolerable only where the traffic never leaves the machine.
LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "::1"}


class SyncError(Exception):
    def __init__(self, msg: str, code: int = 3):
        super().__init__(msg)
        self.code = code


# --------------------------------------------------------------------------
# network — this is the entire network surface of the program
# --------------------------------------------------------------------------
class _RefuseRedirects(urllib.request.HTTPRedirectHandler):
    """Refuse every redirect, loudly.

    urllib replays the original request's headers on a redirect, so following
    one would forward X-N8N-API-KEY to whatever host the Location names. The
    n8n public API has no legitimate reason to redirect a GET of a workflow, so
    a redirect is either a misconfiguration or an attack, and both deserve a
    hard failure rather than a silent hand-off of the key.
    """

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        target = urllib.parse.urlsplit(newurl)
        where = "%s://%s" % (target.scheme or "?", target.netloc or "?")
        raise SyncError(
            "refusing to follow an HTTP %s redirect to %s. Following it would "
            "replay the X-N8N-API-KEY header at that host. Point N8N_BASE_URL "
            "at the instance's real URL instead." % (code, where)
        )

    # Belt and braces: the code-specific hooks all route through the above, but
    # pin them anyway so a stdlib change cannot reintroduce following.
    http_error_301 = http_error_302 = http_error_303 = http_error_307 = \
        http_error_308 = urllib.request.HTTPRedirectHandler.http_error_302


_OPENER = urllib.request.build_opener(_RefuseRedirects())


def check_base_url(base_url: str) -> tuple:
    """Validate N8N_BASE_URL and return (scheme, host, port). Raises on refusal."""
    parts = urllib.parse.urlsplit(base_url)
    host = (parts.hostname or "").lower()
    if not host:
        raise SyncError("N8N_BASE_URL has no host: expected https://<instance>", code=2)
    if parts.scheme == "https":
        return parts.scheme, host, parts.port
    if parts.scheme == "http" and host in LOOPBACK_HOSTS:
        return parts.scheme, host, parts.port
    raise SyncError(
        "N8N_BASE_URL must use https:// — the API key is sent as a request "
        "header and a plaintext URL puts it on the wire in the clear. Plain "
        "http:// is accepted only for a loopback host (http://localhost or "
        "http://127.0.0.1), where there is no network to intercept. Got "
        "scheme %r for host %r." % (parts.scheme, host),
        code=2,
    )


def _get(base_url: str, api_key: str, path: str, params: dict | None = None):
    """The ONLY network function. GET only, enforced by a raise.

    `path` is appended to <base_url>/api/v1. The api key goes in a header and
    is never interpolated into the URL or into any message this function
    raises.
    """
    method = ALLOWED_METHOD
    if method != "GET":
        # NOT an assert: `python3 -O` deletes asserts, and this guarantee is
        # the whole premise of the repository.
        raise SyncError(
            "sync.py is read-only against n8n; only GET is permitted, refusing %r"
            % (method,), code=2)

    scheme, host, port = check_base_url(base_url)

    url = base_url.rstrip("/") + "/api/v1" + path
    if params:
        url += "?" + urllib.parse.urlencode(params)

    req = urllib.request.Request(url, method=method)
    if req.get_method() != "GET":
        raise SyncError("refusing a non-GET request to n8n", code=2)
    req.add_header("X-N8N-API-KEY", api_key)
    req.add_header("Accept", "application/json")
    req.add_header("User-Agent", "n8n-legal-sync/1 (read-only)")

    try:
        with _OPENER.open(req, timeout=TIMEOUT) as resp:
            final = urllib.parse.urlsplit(resp.geturl())
            if (final.hostname or "").lower() != host:
                raise SyncError(
                    "%s %s -> response came from host %r, not the configured %r; "
                    "refusing to treat it as an n8n reply"
                    % (method, path, final.hostname, host))
            raw = resp.read(MAX_RESPONSE_BYTES + 1)
            if len(raw) > MAX_RESPONSE_BYTES:
                raise SyncError(
                    "%s %s -> response exceeds the %d byte size cap; refusing to "
                    "read further" % (method, path, MAX_RESPONSE_BYTES))
            body = raw.decode("utf-8")
    except urllib.error.HTTPError as e:  # no key in the message: url has none
        raise SyncError("%s %s -> HTTP %s %s" % (method, path, e.code, e.reason))
    except urllib.error.URLError as e:
        raise SyncError("%s %s -> network error: %s" % (method, path, e.reason))
    except UnicodeDecodeError:
        raise SyncError("%s %s -> response was not valid UTF-8" % (method, path))
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        raise SyncError("%s %s -> response was not JSON" % (method, path))


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


def _envelope(key: str, cfg: dict, kind: str, body: dict, cls: dict,
              scrub_stats: dict) -> dict:
    """The committed capture envelope. Deliberately carries NO timestamp: see
    the note on LASTRUN. Everything here is derived from the captured content,
    so an unchanged workflow produces a byte-identical file."""
    return {
        "_capture": {
            "key": key,
            "workflow_id": cfg["id"],
            "workflow_name": cfg["name"],
            "kind": kind,  # "active" | "draft" | "unknown"
            "source": "n8n public REST API GET /api/v1/workflows/{id} (read-only)",
            "capture_time": "see exports/last-run.json (untracked, so an unchanged "
                            "capture does not produce a commit)",
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


def write_drift(prev: dict, new: dict, failed: dict, configured: set) -> list:
    """Render docs/drift-report.md. Content-derived only — no timestamps, so a
    run that captured identical bodies rewrites the file byte-for-byte."""
    prev_wf = (prev or {}).get("workflows", {})
    new_wf = new.get("workflows", {})
    lines, changes = [], []

    for key in sorted(set(prev_wf) | set(new_wf) | set(configured) | set(failed)):
        if key in failed:
            # A fetch that failed is NOT a removal. Say which it is.
            had = "previous hashes retained" if key in prev_wf else "never captured"
            changes.append("%s: CAPTURE FAILED this run — %s (%s)"
                           % (key, failed[key], had))
            continue
        p, n = prev_wf.get(key), new_wf.get(key)
        if p is None and n is not None:
            changes.append("%s: first capture" % key)
            continue
        if n is None:
            if key in configured:
                changes.append("%s: configured but not captured this run" % key)
            else:
                changes.append("%s: no longer configured (removed from "
                               "config/workflows.json)" % key)
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
    lines.append("Written by `scripts/sync.py`. Everything below is derived from the")
    lines.append("captured content, never from the clock — a run that sees no change")
    lines.append("rewrites this file identically and produces no commit. Run times are")
    lines.append("in `exports/last-run.json`, which is untracked.")
    lines.append("")
    if failed:
        lines.append("## Incomplete capture")
        lines.append("")
        lines.append("This run did **not** capture every configured workflow. A failure")
        lines.append("here is a transient fetch problem, not evidence that a workflow was")
        lines.append("removed; the previously captured bodies and hashes are left in place.")
        lines.append("")
        for key in sorted(failed):
            lines.append("- **%s**: %s" % (key, failed[key]))
        lines.append("")
    lines.append("## Changed since last sync")
    lines.append("")
    if changes:
        for c in changes:
            lines.append("- %s" % c)
    else:
        lines.append("- Nothing. Every captured body hashes identically to the previous sync.")
    lines.append("")
    lines.append("## Per-workflow state")
    lines.append("")
    lines.append("| key | name | capture | active sha256 (canonical, first 12) | draft present | draft sha256 (first 12) |")
    lines.append("|---|---|---|---|---|---|")
    for key in sorted(set(new_wf) | set(failed)):
        e = new_wf.get(key, {})
        a = (e.get("active") or {}).get("sha256_canonical")
        d = (e.get("draft") or {}).get("sha256_canonical")
        lines.append("| %s | %s | %s | `%s` | %s | %s |" % (
            key, e.get("name", ""),
            "FAILED this run" if key in failed else "ok",
            (a or "-")[:12], "yes" if d else "no",
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
    if base and required:
        check_base_url(base)
    return base, key, missing


def _write_last_run(payload: dict) -> None:
    """Untracked sidecar: the clock lives here so it cannot cause a commit."""
    try:
        os.makedirs(os.path.dirname(LASTRUN), exist_ok=True)
        with open(LASTRUN, "w", encoding="utf-8") as fh:
            fh.write(_pretty(payload))
    except OSError:
        pass


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
            try:
                check_base_url(base)
                print("base url        : accepted (https, or loopback http)")
            except SyncError as e:
                print("base url        : REFUSED — %s" % e)
            print("would GET       : %s/api/v1/workflows/<id>  [GET only]" % base.rstrip("/"))
        else:
            print("would GET       : <N8N_BASE_URL>/api/v1/workflows/<id>  [GET only]")
        print("would write     : exports/active/<KEY>.json, exports/manifest.json,")
        print("                  docs/drift-report.md, exports/last-run.json (untracked)")
        print("redirects       : refused; the API key never follows a Location header")
        print("response cap    : %d bytes" % MAX_RESPONSE_BYTES)
        print("write calls to n8n: none, by construction (single _get() helper, GET raised on)")
        return 0

    captured_at = _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    prev = _load_prev_manifest()
    prev_wf = (prev or {}).get("workflows", {})
    manifest = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "source": "n8n public REST API /api/v1 (GET only)",
        "timestamps": "not stored here on purpose — see exports/last-run.json",
        "api_capability": None,
        "workflows": {},
    }

    os.makedirs(ACTIVE_DIR, exist_ok=True)
    os.makedirs(DRAFT_DIR, exist_ok=True)

    capability = None
    written = 0
    failed: dict = {}

    for wf_key in sorted(wfs):
        entry = wfs[wf_key]
        try:
            wf = _get(base, key, "/workflows/%s" % urllib.parse.quote(entry["id"]),
                      {"excludePinnedData": "true"})
        except SyncError as e:
            if e.code == 2:
                raise
            failed[wf_key] = "fetch failed: %s" % e
            wf = None
        if wf is not None and (not isinstance(wf, dict) or "nodes" not in wf):
            failed[wf_key] = ("the API returned an unexpected shape (no `nodes` key). "
                              "Treated as a transient failure, NOT as a removal.")
            wf = None
        if wf is None:
            # Carry the previous record forward untouched, so a transient
            # failure neither destroys a good capture nor churns the manifest.
            if wf_key in prev_wf:
                manifest["workflows"][wf_key] = prev_wf[wf_key]
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
            env = _envelope(wf_key, entry, kind, scrubbed, cls, stats)
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

    manifest["api_capability"] = (
        capability
        or (prev.get("api_capability") if failed else None)
        or "unavailable_via_public_api")

    captured_now = len(wfs) - len(failed)
    if captured_now == 0:
        _write_last_run({"captured_at": captured_at, "status": "failed",
                         "failed": failed})
        print("ERROR: the API returned no usable workflow bodies; nothing written.",
              file=sys.stderr)
        for k, why in sorted(failed.items()):
            print("  %s: %s" % (k, why), file=sys.stderr)
        return 4

    with open(MANIFEST, "w", encoding="utf-8") as fh:
        fh.write(_pretty(manifest))
    changes = write_drift(prev, manifest, failed, set(wfs))

    _write_last_run({
        "captured_at": captured_at,
        "status": "partial" if failed else "ok",
        "workflows_configured": len(wfs),
        "workflows_captured": captured_now,
        "failed": failed,
        "changes": changes,
        "note": "Untracked on purpose: a timestamp in a tracked file makes every "
                "scheduled run look like a change.",
    })

    print("n8n -> repo sync complete (read-only against n8n).")
    print("  captured_at        : %s  (exports/last-run.json, untracked)" % captured_at)
    print("  workflows captured : %d of %d" % (captured_now, len(wfs)))
    print("  files written      : %d" % written)
    print("  draft/active       : %s" % manifest["api_capability"])
    print("  drift              : %s" % ("%d change(s), see docs/drift-report.md" % len(changes)
                                         if changes else "none"))
    if failed:
        print("PARTIAL CAPTURE — %d of %d workflow(s) could not be captured this run."
              % (len(failed), len(wfs)), file=sys.stderr)
        for k, why in sorted(failed.items()):
            print("  %s: %s" % (k, why), file=sys.stderr)
        print("  Previous hashes for those keys were retained; this is a transient "
              "failure, not a removal.", file=sys.stderr)
        return 5
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
