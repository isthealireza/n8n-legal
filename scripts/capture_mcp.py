#!/usr/bin/env python3
"""Capture n8n workflow bodies **from an MCP session** into this repository.

Why this file exists
--------------------
`scripts/sync.py` is the intended capture path: it talks to the n8n public REST
API over HTTPS with an `X-N8N-API-KEY`. In the environment this repository was
first populated from, that path could not run at all — the egress proxy refuses
`CONNECT` to the instance host (HTTP 403) and no n8n API key exists. What *was*
available was the authenticated, read-only **n8n MCP server**.

So the bodies under `exports/` were read through MCP rather than through the
REST API, and this script is the tool that turned them into the on-disk format.
It exists so that capture is a **program with an input**, not a person pasting
JSON into files: given the same raw MCP responses it produces byte-identical
output, and the transformation from raw body to committed export is reviewable.

**Everything it writes is stamped `"source": "mcp-session"`** and carries the
capture date, so no reader can mistake an MCP capture for a REST API sync.
`sync.py` stamps its own, different string; the two never collide.

It shares code with `sync.py` on purpose
----------------------------------------
The scrubber (`scrub.scrub_obj`), the canonical serialisation
(`sync.canonical_json`), the on-disk serialisation (`sync.pretty_json`), the
digest (`sync.sha256_text`) and the published-body assembly
(`sync._body_from_active_version`) are **imported**, never restated. A second
copy of a canonicaliser is a second hash that silently disagrees with the first
the day one of them is edited. Importing `sync` opens no socket: that module's
entire network surface is `_get()`, which is reached only from `sync.run()`.

This script itself makes **no network call of any kind**. Its only inputs are
local files.

Input
-----
A raw directory (default `.raw/`, which `.gitignore` already excludes, because
raw bodies are unscrubbed). Per workflow key `<KEY>` from
`config/workflows.json`:

    .raw/<KEY>.details.json        REQUIRED. Verbatim `get_workflow_details`
                                   response. Either the whole response (with a
                                   top-level `workflow` object) or the workflow
                                   object itself.
    .raw/<KEY>.activeversion.json  Required ONLY when versionId != activeVersionId.
                                   Verbatim `get_workflow_version` response for
                                   the activeVersionId — the PUBLISHED graph.
    .raw/<KEY>.diff.json           OPTIONAL. Verbatim `get_workflow_versions_diff`
                                   response, published -> draft. Used to render
                                   the node-level "how they differ" section of
                                   the drift report. Absent is fine; the report
                                   then says the node-level detail was not
                                   captured rather than guessing at it.

Nothing is inferred from a missing file. If a workflow's draft and published
version ids differ and no `activeversion.json` is present, the script refuses
that workflow rather than writing the draft graph into `exports/active/` and
calling it published.

Output (identical in shape to what `sync.py` writes)
----------------------------------------------------
    exports/active/<KEY>.json      scrubbed published body + `_capture` block
    exports/draft/<KEY>.json       scrubbed draft body — ONLY where the two
                                   version ids genuinely differ
    exports/manifest.json          per-workflow version ids and SHA-256 digests
    docs/drift-report.md           drift vs the previous manifest, plus the
                                   observed published-vs-draft state

A draft file is removed when the key's two version ids agree, exactly as
`sync.py` does, so the *absence* of a draft file keeps its meaning: draft ==
published.

On the capture date in tracked files
------------------------------------
`sync.py` deliberately keeps the wall clock out of tracked output, because a
timestamp turns every scheduled run into a content change. That reasoning does
not apply here and the trade is different: this is a one-off, hand-fed capture
through a non-default interface, and *when* it was read is a load-bearing fact
about how much to trust it — a workflow's draft/published state is live and a
snapshot of it ages. The date is therefore written into the output, but it is
`--capture-date`, defaulting to today UTC and recorded in
`config/workflows.json`: pass the same date and a re-run is byte-identical.

Usage
-----
    python3 scripts/capture_mcp.py --capture-date 2026-08-25
    python3 scripts/capture_mcp.py --dry-run      # report what it would read/write
    python3 scripts/capture_mcp.py --self-test    # no n8n data needed

Exit codes:
    0  every configured workflow captured
    2  bad configuration or bad input
    5  PARTIAL — at least one configured workflow could not be captured
"""

from __future__ import annotations

import argparse
import datetime as _dt
import difflib
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from scrub import scrub_obj, scrub_text                      # noqa: E402
from sync import (                                           # noqa: E402
    ACTIVE_DIR,
    CONFIG,
    DRAFT_DIR,
    DRIFT,
    MANIFEST,
    REPO,
    SyncError,
    _body_from_active_version,
    canonical_json,
    load_config,
    pretty_json,
    sha256_text,
)

# Stamped into every record this script writes. `sync.py` writes a different
# string; a reader can always tell which path produced a file.
SOURCE = "mcp-session"
SOURCE_LONG = (
    "authenticated n8n MCP server, read-only tools only "
    "(get_workflow_details / get_workflow_version / get_workflow_versions_diff). "
    "NOT the public REST API — see docs/API_CAPABILITIES.md."
)
MANIFEST_SCHEMA_VERSION = 2
RAW_DIR_DEFAULT = os.path.join(REPO, ".raw")

# Keys the MCP surface decorates a workflow with that are not part of the
# workflow body. They describe the *caller's* session, not the workflow, and
# they would show up as spurious drift the first time a REST sync replaced this
# capture. `scopes`/`canExecute` in particular enumerate write permissions the
# calling token happens to hold, which has no place in a read-only mirror.
MCP_ONLY_KEYS = ("scopes", "canExecute", "availableInMCP", "nodeCount")


class CaptureError(Exception):
    def __init__(self, msg: str, code: int = 2):
        super().__init__(msg)
        self.code = code


# --------------------------------------------------------------------------
# raw input
# --------------------------------------------------------------------------
def _read_json(path: str):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except OSError as e:
        raise CaptureError("cannot read %s: %s" % (path, e))
    except json.JSONDecodeError as e:
        raise CaptureError("%s is not valid JSON: %s" % (path, e))


def unwrap_details(raw) -> dict:
    """Accept either the full `get_workflow_details` response or the workflow
    object inside it. Anything without a `nodes` array is refused: an export is
    a real capture or it does not exist."""
    wf = raw.get("workflow") if isinstance(raw, dict) and "workflow" in raw else raw
    if not isinstance(wf, dict):
        raise CaptureError("details payload is not an object")
    if not isinstance(wf.get("nodes"), list):
        raise CaptureError("details payload has no `nodes` array; refusing it")
    if not wf.get("versionId"):
        raise CaptureError("details payload has no `versionId`; refusing it")
    return wf


def unwrap_version(raw) -> dict:
    """Accept either the full `get_workflow_version` response or the version
    object inside it."""
    v = raw
    if isinstance(v, dict):
        for key in ("version", "workflowVersion", "data"):
            if isinstance(v.get(key), dict):
                v = v[key]
                break
    if not isinstance(v, dict) or not isinstance(v.get("nodes"), list):
        raise CaptureError("version payload has no `nodes` array; refusing it")
    return v


def strip_session_keys(body: dict) -> dict:
    return {k: v for k, v in body.items() if k not in MCP_ONLY_KEYS}


# --------------------------------------------------------------------------
# one workflow
# --------------------------------------------------------------------------
def classify_mcp(wf: dict) -> dict:
    """What MCP actually told us about draft vs published.

    `get_workflow_details` returns both ids at the top level — `versionId` (the
    draft / current version) and `activeVersionId` (the published one) — and an
    `activeVersion` object which, on this instance, is the convenience form
    `{"sameAsDraft": true}` when the two agree. Nothing here is inferred: if an
    id is absent it is reported absent.
    """
    draft_vid = wf.get("versionId")
    active_vid = wf.get("activeVersionId")
    av = wf.get("activeVersion")
    same_as_draft = av.get("sameAsDraft") if isinstance(av, dict) else None
    if not active_vid:
        return {
            "determination": "no_active_version_id_reported_by_mcp",
            "draft_version_id": draft_vid,
            "active_version_id": None,
            "diverged": None,
            "same_as_draft_flag": same_as_draft,
        }
    return {
        "determination": "from_mcp_active_version_id",
        "draft_version_id": draft_vid,
        "active_version_id": active_vid,
        "diverged": active_vid != draft_vid,
        "same_as_draft_flag": same_as_draft,
    }


def _envelope(key: str, cfg: dict, kind: str, body: dict, cls: dict,
              scrub_stats: dict, capture_date: str, published_from: str) -> dict:
    """The committed capture envelope. Same shape as `sync.py`'s, with the
    provenance fields telling the truth about where the bytes came from."""
    return {
        "_capture": {
            "key": key,
            "workflow_id": cfg["id"],
            "workflow_name": cfg["name"],
            "kind": kind,  # "active" | "draft"
            "source": SOURCE,
            "source_detail": SOURCE_LONG,
            "captured_on": capture_date,
            "captured_by": "scripts/capture_mcp.py",
            "not_captured_by": (
                "scripts/sync.py — the n8n public REST API was unreachable from "
                "the capture environment (proxy refused CONNECT) and no API key "
                "was available. The REST path remains untested against a live "
                "instance."
            ),
            "published_body_from": published_from,
            "draft_active_determination": cls["determination"],
            "draft_version_id": cls["draft_version_id"],
            "active_version_id": cls["active_version_id"],
            "draft_diverged_from_published": cls["diverged"],
            "mcp_only_keys_dropped": list(MCP_ONLY_KEYS),
            "scrubbed": True,
            "scrub_counts": scrub_stats,
        },
        "workflow": body,
    }


def capture_one(key: str, entry: dict, raw_dir: str, capture_date: str) -> dict:
    """Read one workflow's raw MCP payloads and write its export file(s).

    Returns the manifest record. Raises CaptureError with the reason if the
    inputs do not support an honest capture.
    """
    details_path = os.path.join(raw_dir, "%s.details.json" % key)
    if not os.path.exists(details_path):
        raise CaptureError("no raw MCP capture at %s" % os.path.relpath(details_path, REPO))
    wf = unwrap_details(_read_json(details_path))

    if wf.get("id") and entry.get("id") and wf["id"] != entry["id"]:
        raise CaptureError(
            "raw capture is for workflow id %r but config/workflows.json says %s is %r"
            % (wf["id"], key, entry["id"]))

    cls = classify_mcp(wf)
    if cls["determination"] != "from_mcp_active_version_id":
        raise CaptureError(
            "MCP reported no activeVersionId for this workflow, so published "
            "cannot be distinguished from draft; refusing to write a body that "
            "would have to claim one or the other")

    # The draft is the top-level graph, minus MCP session decoration.
    draft_body = strip_session_keys(
        {k: v for k, v in wf.items() if k != "activeVersion"})

    if cls["diverged"]:
        av_path = os.path.join(raw_dir, "%s.activeversion.json" % key)
        if not os.path.exists(av_path):
            raise CaptureError(
                "draft version %s is ahead of published version %s, but there is "
                "no %s holding the published graph. Fetch it with "
                "get_workflow_version(activeVersionId) — the draft graph must "
                "never be written to exports/active/."
                % (cls["draft_version_id"], cls["active_version_id"],
                   os.path.relpath(av_path, REPO)))
        av = unwrap_version(_read_json(av_path))
        av_vid = av.get("versionId")
        if av_vid and av_vid != cls["active_version_id"]:
            raise CaptureError(
                "%s holds version %r, but the published version is %r"
                % (os.path.relpath(av_path, REPO), av_vid, cls["active_version_id"]))
        # Reuse sync.py's assembly so both paths build a published body the
        # same way: workflow envelope, published graph swapped in.
        active_body = strip_session_keys(_body_from_active_version(wf, av))
        active_body["versionId"] = cls["active_version_id"]
        published_from = ("get_workflow_version(activeVersionId=%s): the published "
                          "graph, swapped into the workflow envelope"
                          % cls["active_version_id"])
        bodies = [("active", active_body, ACTIVE_DIR),
                  ("draft", draft_body, DRAFT_DIR)]
    else:
        active_body = dict(draft_body)
        published_from = ("get_workflow_details: versionId == activeVersionId, so "
                          "the single graph returned IS the published one")
        bodies = [("active", active_body, ACTIVE_DIR)]
        stale = os.path.join(DRAFT_DIR, "%s.json" % key)
        if os.path.exists(stale):
            os.remove(stale)

    rec = {
        "_bodies": {"active": active_body, "draft": draft_body} if cls["diverged"] else None,
        "name": entry.get("name"),
        "id": entry["id"],
        "source": SOURCE,
        "captured_on": capture_date,
        "determination": cls["determination"],
        "draft_version_id": cls["draft_version_id"],
        "active_version_id": cls["active_version_id"],
        "diverged": cls["diverged"],
        "active": None,
        "draft": None,
    }

    for kind, body, outdir in bodies:
        scrubbed, stats = scrub_obj(body)
        env = _envelope(key, entry, kind, scrubbed, cls, stats, capture_date,
                        published_from)
        os.makedirs(outdir, exist_ok=True)
        path = os.path.join(outdir, "%s.json" % key)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(pretty_json(env))
        rec["draft" if kind == "draft" else "active"] = {
            "kind": kind,
            "path": os.path.relpath(path, REPO).replace(os.sep, "/"),
            "sha256_body": sha256_text(pretty_json(scrubbed)),
            "sha256_canonical": sha256_text(canonical_json(scrubbed)),
        }
    return rec


# --------------------------------------------------------------------------
# node-level difference rendering (from get_workflow_versions_diff)
# --------------------------------------------------------------------------
def _short(value, limit: int = 80) -> str:
    """One line, scrubbed, bounded. Values from a diff are workflow content and
    go through the same scrubber as everything else before being written."""
    if isinstance(value, (dict, list)):
        text = canonical_json(value)
    else:
        text = "" if value is None else str(value)
    text, _ = scrub_text(text)
    text = " ".join(text.split())
    return (text[:limit] + "…") if len(text) > limit else text


# Above this, a truncated snippet of a value says nothing useful. A node's
# `jsCode` is thousands of characters; "// Deterministic. No model runs here…"
# is not a description of what changed. Long text is summarised by shape
# instead — sizes and line counts — which is derived from the two bodies and
# invents nothing. The bodies themselves are in exports/, which is where a
# reader who needs the actual delta should go.
LONG_VALUE = 200


class _Gone:
    """A key that exists on one side only. Distinct from a value of None."""

    def __repr__(self):  # pragma: no cover - debug aid
        return "<absent>"


_GONE = _Gone()


def _describe_change(before, after) -> str:
    if before is _GONE:
        return "key added, now %s" % (_short(after) or "(empty)")
    if after is _GONE:
        return "key removed (was %s)" % (_short(before) or "(empty)")
    if (isinstance(before, str) and isinstance(after, str)
            and max(len(before), len(after)) > LONG_VALUE):
        a, b = before.splitlines(), after.splitlines()
        removed = added = 0
        for line in difflib.unified_diff(a, b, n=0, lineterm=""):
            if line.startswith("-") and not line.startswith("---"):
                removed += 1
            elif line.startswith("+") and not line.startswith("+++"):
                added += 1
        return ("long text rewritten: %d -> %d characters, %d -> %d lines "
                "(%d line(s) removed, %d added). The two bodies are in "
                "`exports/active/` and `exports/draft/`."
                % (len(before), len(after), len(a), len(b), removed, added))
    return "%s  ->  %s" % (_short(before) or "(absent)", _short(after) or "(absent)")


def _diff_entries(diff) -> list:
    """Flatten a `get_workflow_versions_diff` response into report lines.

    Written against the shape the n8n MCP server actually returned on
    2026-08-25: `nodesAdded` / `nodesRemoved` / `nodesModified` /
    `connectionsAdded` / `connectionsRemoved`, where a modified node carries a
    `changes` tree mirroring the node's own structure down to the changed leaf.
    A leaf is `{"__old": x, "__new": y}` for a replaced value, or the parent
    holds `"<key>__deleted"` / `"<key>__added"` for a key that went or arrived.

    Unrecognised leaves are reported as "changed" with the path, never guessed
    at. Every value printed goes through the scrubber first.
    """
    if not isinstance(diff, dict):
        return []
    lines = []

    def name_of(item):
        if isinstance(item, dict):
            for k in ("name", "nodeName", "id", "nodeId"):
                if isinstance(item.get(k), str):
                    return item[k]
        return str(item)

    for item in diff.get("nodesAdded") or []:
        lines.append("node added: `%s`" % name_of(item))
    for item in diff.get("nodesRemoved") or []:
        lines.append("node removed: `%s`" % name_of(item))

    def walk(node, path, out):
        """Depth-first over a `changes` subtree, emitting (path, before, after)."""
        if not isinstance(node, dict):
            out.append((path, None, node))
            return
        if "__old" in node or "__new" in node:
            out.append((path, node.get("__old"), node.get("__new")))
            return
        for key, value in node.items():
            if key.endswith("__deleted"):
                out.append((path + [key[: -len("__deleted")]], value, _GONE))
            elif key.endswith("__added"):
                out.append((path + [key[: -len("__added")]], _GONE, value))
            else:
                walk(value, path + [key], out)

    for item in diff.get("nodesModified") or []:
        nm = name_of(item)
        leaves = []
        walk(item.get("changes") or {}, [], leaves)
        if not leaves:
            lines.append("node modified: `%s` (the diff carried no field-level "
                         "detail)" % nm)
        for path, before, after in leaves:
            lines.append("node `%s`, `%s`: %s"
                         % (nm, ".".join(path) or "(node)",
                            _describe_change(before, after)))

    for verb in ("Added", "Removed"):
        for item in diff.get("connections" + verb) or []:
            lines.append("connection %s: %s" % (verb.lower(), _short(item, 120)))
    return lines


def body_node_differences(published: dict, draft: dict) -> list:
    """Compare the two captured bodies directly, without the diff tool.

    This is not a second opinion for its own sake. On WF1 the MCP diff endpoint
    reported two changed fields and did **not** report that two nodes had moved
    on the canvas, which is a real difference between the two stored bodies even
    though it changes no behaviour. A report that only ever repeats what one
    endpoint says cannot notice what that endpoint leaves out.

    Compares by node NAME (n8n's own connection map is keyed by name) and lists
    the top-level node keys whose canonical form differs. Values are not printed
    here — `_diff_entries` already prints them where the diff tool supplied them.
    """
    def by_name(nodes):
        return {n.get("name", n.get("id", "?")): n for n in (nodes or [])
                if isinstance(n, dict)}

    pub, dra = by_name(published.get("nodes")), by_name(draft.get("nodes"))
    lines = []
    for nm in sorted(set(dra) - set(pub)):
        lines.append("node only in the draft: `%s`" % nm)
    for nm in sorted(set(pub) - set(dra)):
        lines.append("node only in the published body: `%s`" % nm)
    for nm in sorted(set(pub) & set(dra)):
        keys = sorted(k for k in set(pub[nm]) | set(dra[nm])
                      if canonical_json(pub[nm].get(k)) != canonical_json(dra[nm].get(k)))
        if keys:
            lines.append("node `%s`: differs on %s"
                         % (nm, ", ".join("`%s`" % k for k in keys)))
    if canonical_json(published.get("connections")) != canonical_json(draft.get("connections")):
        lines.append("the connection map differs")
    else:
        lines.append("the connection map is identical — no node was rewired")
    return lines


# --------------------------------------------------------------------------
# manifest / drift report
# --------------------------------------------------------------------------
def _load_prev_manifest() -> dict:
    try:
        with open(MANIFEST, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        return {}


def write_drift(prev: dict, new: dict, failed: dict, configured: set,
                diffs: dict, bodies: dict, capture_date: str) -> list:
    prev_wf = (prev or {}).get("workflows", {})
    new_wf = new.get("workflows", {})
    changes = []

    for key in sorted(set(prev_wf) | set(new_wf) | set(configured) | set(failed)):
        if key in failed:
            had = "previous record retained" if key in prev_wf else "never captured"
            changes.append("%s: CAPTURE FAILED this run — %s (%s)"
                           % (key, failed[key], had))
            continue
        p, n = prev_wf.get(key), new_wf.get(key)
        if p is None and n is not None:
            changes.append("%s: first capture" % key)
            continue
        if n is None:
            changes.append("%s: configured but not captured this run" % key
                           if key in configured else
                           "%s: no longer configured" % key)
            continue
        for kind in ("active", "draft"):
            ph = (p.get(kind) or {}).get("sha256_canonical")
            nh = (n.get(kind) or {}).get("sha256_canonical")
            if ph == nh:
                continue
            if ph is None:
                changes.append("%s: %s body appeared" % (key, kind))
            elif nh is None:
                changes.append("%s: %s body disappeared (draft caught up to "
                               "published)" % (key, kind))
            else:
                changes.append("%s: %s body changed" % (key, kind))

    L = []
    L.append("# Drift report")
    L.append("")
    L.append("**Generated by `scripts/capture_mcp.py` — NOT by `scripts/sync.py`.**")
    L.append("")
    L.append("Every body summarised below was read through the authenticated,")
    L.append("read-only **n8n MCP server** on **%s**, because the n8n public REST"
             % capture_date)
    L.append("API was unreachable from the capture environment (the egress proxy")
    L.append("refused `CONNECT` to the instance host and no API key existed). The")
    L.append("REST path in `scripts/sync.py` has still never run against a live")
    L.append("instance. See `docs/API_CAPABILITIES.md`.")
    L.append("")
    L.append("A workflow's draft/published state is live and this is a snapshot of")
    L.append("one day. Read the date, not the tense.")
    L.append("")
    if failed:
        L.append("## Incomplete capture")
        L.append("")
        for key in sorted(failed):
            L.append("- **%s**: %s" % (key, failed[key]))
        L.append("")
    L.append("## Published vs draft, as observed")
    L.append("")
    L.append("| key | name | published (active) version id | draft version id | differ? | draft file |")
    L.append("|---|---|---|---|---|---|")
    for key in sorted(set(new_wf) | set(failed)):
        e = new_wf.get(key, {})
        if key in failed:
            L.append("| %s | | — | — | CAPTURE FAILED | — |" % key)
            continue
        L.append("| %s | %s | `%s` | `%s` | %s | %s |" % (
            key, e.get("name", ""), e.get("active_version_id") or "—",
            e.get("draft_version_id") or "—",
            "**yes**" if e.get("diverged") else "no",
            "`exports/draft/%s.json`" % key if e.get("draft") else "none (draft == published)"))
    L.append("")
    L.append("## How the diverged workflows differ")
    L.append("")
    diverged = [k for k in sorted(new_wf) if new_wf[k].get("diverged")]
    if not diverged:
        L.append("- No configured workflow had a draft ahead of its published version.")
    for key in diverged:
        L.append("### %s — %s" % (key, new_wf[key].get("name", "")))
        L.append("")
        L.append("Published `%s` -> draft `%s`, per `get_workflow_versions_diff`:"
                 % (new_wf[key].get("active_version_id"),
                    new_wf[key].get("draft_version_id")))
        L.append("")
        entries = diffs.get(key) or []
        if entries:
            for line in entries:
                L.append("- %s" % line)
        else:
            L.append("- Node-level detail was not captured for this workflow. The")
            L.append("  two version ids differ; what differs between them is not")
            L.append("  stated here, because it was not observed.")
        L.append("")
        pair = bodies.get(key)
        if pair:
            L.append("Independent comparison of the two bodies in `exports/`, node by")
            L.append("node — this is computed here, not taken from the diff endpoint,")
            L.append("and it can therefore show differences that endpoint does not")
            L.append("report:")
            L.append("")
            for line in body_node_differences(pair["active"], pair["draft"]):
                L.append("- %s" % line)
            L.append("")
    L.append("## Changed since the previous manifest")
    L.append("")
    if changes:
        for c in changes:
            L.append("- %s" % c)
    else:
        L.append("- Nothing. Every captured body hashes identically to the previous record.")
    L.append("")
    L.append("## Digests")
    L.append("")
    L.append("SHA-256 over the canonical form (`sync.canonical_json`) of the")
    L.append("**scrubbed** body — the same function `sync.py` hashes with, so a")
    L.append("later REST sync of an unchanged workflow produces the same digest")
    L.append("for the same bytes.")
    L.append("")
    L.append("| key | source | active sha256 (first 12) | draft sha256 (first 12) |")
    L.append("|---|---|---|---|")
    for key in sorted(set(new_wf) | set(failed)):
        e = new_wf.get(key, {})
        a = (e.get("active") or {}).get("sha256_canonical")
        d = (e.get("draft") or {}).get("sha256_canonical")
        L.append("| %s | %s | `%s` | %s |" % (
            key, "CAPTURE FAILED" if key in failed else e.get("source", SOURCE),
            (a or "-")[:12], "`%s`" % d[:12] if d else "—"))
    L.append("")

    os.makedirs(os.path.dirname(DRIFT), exist_ok=True)
    with open(DRIFT, "w", encoding="utf-8") as fh:
        fh.write("\n".join(L))
    return changes


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------
def run(args) -> int:
    cfg = load_config()
    wfs = cfg["workflows"]
    raw_dir = os.path.abspath(args.raw_dir)
    capture_date = args.capture_date

    if args.dry_run:
        print("DRY RUN — reads nothing, writes nothing, makes no network call.")
        print("raw dir      : %s" % raw_dir)
        print("capture date : %s" % capture_date)
        print("source stamp : %s" % SOURCE)
        for key in sorted(wfs):
            have = os.path.exists(os.path.join(raw_dir, "%s.details.json" % key))
            av = os.path.exists(os.path.join(raw_dir, "%s.activeversion.json" % key))
            df = os.path.exists(os.path.join(raw_dir, "%s.diff.json" % key))
            print("  %-4s details=%-5s activeversion=%-5s diff=%s"
                  % (key, have, av, df))
        print("would write  : exports/active/<KEY>.json, exports/draft/<KEY>.json,")
        print("               exports/manifest.json, docs/drift-report.md")
        return 0

    prev = _load_prev_manifest()
    prev_wf = (prev or {}).get("workflows", {})
    os.makedirs(ACTIVE_DIR, exist_ok=True)
    os.makedirs(DRAFT_DIR, exist_ok=True)

    manifest = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "source": SOURCE,
        "source_detail": SOURCE_LONG,
        "captured_on": capture_date,
        "captured_by": "scripts/capture_mcp.py",
        "api_capability": "not_exercised_rest_api_unreachable_from_capture_environment",
        "hashing": ("sha256 over sync.canonical_json() of the scrubbed body — the "
                    "same function scripts/sync.py uses"),
        "workflows": {},
    }

    failed, diffs, bodies = {}, {}, {}
    for key in sorted(wfs):
        try:
            rec = capture_one(key, wfs[key], raw_dir, capture_date)
            # The unscrubbed pair is used only to render the comparison below and
            # is never written to the manifest.
            pair = rec.pop("_bodies", None)
            if pair:
                bodies[key] = pair
            manifest["workflows"][key] = rec
        except CaptureError as e:
            failed[key] = str(e)
            if key in prev_wf:
                manifest["workflows"][key] = prev_wf[key]
            continue
        dpath = os.path.join(raw_dir, "%s.diff.json" % key)
        if manifest["workflows"][key].get("diverged") and os.path.exists(dpath):
            diffs[key] = _diff_entries(_read_json(dpath))

    with open(MANIFEST, "w", encoding="utf-8") as fh:
        fh.write(pretty_json(manifest))
    changes = write_drift(prev, manifest, failed, set(wfs), diffs, bodies,
                          capture_date)

    print("MCP capture complete (read-only; no network call from this script).")
    print("  captured_on        : %s" % capture_date)
    print("  source             : %s" % SOURCE)
    print("  workflows captured : %d of %d" % (len(wfs) - len(failed), len(wfs)))
    print("  drift              : %s" % (("%d change(s)" % len(changes))
                                         if changes else "none"))
    for key in sorted(manifest["workflows"]):
        rec = manifest["workflows"][key]
        if key in failed:
            continue
        print("  %-4s published=%s draft=%s %s"
              % (key, (rec.get("active_version_id") or "?")[:8],
                 (rec.get("draft_version_id") or "?")[:8],
                 "DIVERGED" if rec.get("diverged") else "same"))
    if failed:
        print("PARTIAL — %d of %d workflow(s) not captured:" % (len(failed), len(wfs)),
              file=sys.stderr)
        for k, why in sorted(failed.items()):
            print("  %s: %s" % (k, why), file=sys.stderr)
        return 5
    return 0


# --------------------------------------------------------------------------
# self test — needs no n8n data
# --------------------------------------------------------------------------
def self_test() -> int:
    passed, failures = [], []

    wf = {"id": "X", "name": "n", "versionId": "v-draft",
          "activeVersionId": "v-draft", "nodes": [], "connections": {},
          "scopes": ["workflow:update"], "canExecute": True,
          "activeVersion": {"sameAsDraft": True}}
    cls = classify_mcp(wf)
    ok = cls["diverged"] is False and cls["active_version_id"] == "v-draft"
    (passed if ok else failures).append(
        "same-version-is-not-diverged" if ok else
        "same-version-is-not-diverged: %r" % cls)

    wf2 = dict(wf, activeVersionId="v-pub", activeVersion={"sameAsDraft": False})
    ok = classify_mcp(wf2)["diverged"] is True
    (passed if ok else failures).append(
        "different-version-is-diverged" if ok else "different-version-is-diverged")

    ok = classify_mcp({"versionId": "v"})["determination"] == \
        "no_active_version_id_reported_by_mcp"
    (passed if ok else failures).append(
        "missing-active-id-is-refused" if ok else "missing-active-id-is-refused")

    stripped = strip_session_keys(wf)
    ok = "scopes" not in stripped and "canExecute" not in stripped and "nodes" in stripped
    (passed if ok else failures).append(
        "session-keys-dropped" if ok else "session-keys-dropped: %r" % sorted(stripped))

    # The digest must be the one sync.py would compute. Not a re-implementation.
    import sync as _sync
    ok = (sha256_text(canonical_json({"b": 1, "a": 2}))
          == _sync._sha(_sync._canonical({"a": 2, "b": 1})))
    (passed if ok else failures).append(
        "hash-shared-with-sync" if ok else "hash-shared-with-sync: diverged")

    # A diff entry must never carry an unscrubbed address through to the report.
    lines = _diff_entries({"nodesModified": [
        {"name": "N", "changes": {"parameters": {"sendTo": {
            "__old": "a@lawfirm.example", "__new": "b@lawfirm.example"}}}}]})
    ok = (len(lines) == 1 and "@" not in lines[0]
          and "parameters.sendTo" in lines[0])
    (passed if ok else failures).append(
        "diff-values-are-scrubbed" if ok else "diff-values-are-scrubbed: %r" % lines)

    # The `__deleted` / `__added` spelling must be read as a key coming or going,
    # not walked into as if it were a nested field.
    lines = _diff_entries({"nodesModified": [
        {"name": "Ack", "changes": {"parameters": {"operation__deleted": "answerQuery"}}}]})
    ok = (len(lines) == 1 and "parameters.operation" in lines[0]
          and "key removed" in lines[0] and "answerQuery" in lines[0])
    (passed if ok else failures).append(
        "deleted-key-is-read-as-removal" if ok else
        "deleted-key-is-read-as-removal: %r" % lines)

    # An independent body comparison must see what the diff endpoint omits.
    pub = {"nodes": [{"name": "A", "position": [0, 0], "parameters": {"x": 1}}],
           "connections": {}}
    dra = {"nodes": [{"name": "A", "position": [8, 8], "parameters": {"x": 1}}],
           "connections": {}}
    lines = body_node_differences(pub, dra)
    ok = any("differs on `position`" in l for l in lines) and \
        any("connection map is identical" in l for l in lines)
    (passed if ok else failures).append(
        "body-comparison-sees-position" if ok else
        "body-comparison-sees-position: %r" % lines)

    ok = unwrap_details({"workflow": {"nodes": [], "versionId": "v"}})["versionId"] == "v"
    (passed if ok else failures).append(
        "details-unwrapped" if ok else "details-unwrapped")

    try:
        unwrap_details({"workflow": {"versionId": "v"}})
        failures.append("nodeless-payload-refused: it was accepted")
    except CaptureError:
        passed.append("nodeless-payload-refused")

    for n in passed:
        print("  ok    %s" % n)
    for f in failures:
        print("  FAIL  %s" % f)
    print("capture_mcp self-test: %d passed, %d failed" % (len(passed), len(failures)))
    return 1 if failures else 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Capture n8n workflows from raw MCP responses into exports/. "
                    "Makes no network call.")
    ap.add_argument("--raw-dir", default=RAW_DIR_DEFAULT,
                    help="directory holding <KEY>.details.json etc (default .raw/, gitignored)")
    ap.add_argument("--capture-date",
                    default=_dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%d"),
                    help="the date the MCP session read these bodies (UTC, YYYY-MM-DD)")
    ap.add_argument("--dry-run", action="store_true",
                    help="report which raw inputs are present; write nothing")
    ap.add_argument("--self-test", action="store_true",
                    help="check the classification, stripping, hashing and diff rendering")
    args = ap.parse_args(argv)
    if args.self_test:
        return self_test()
    try:
        return run(args)
    except (CaptureError, SyncError) as e:
        print("ERROR: %s" % e, file=sys.stderr)
        return getattr(e, "code", 2)


if __name__ == "__main__":
    raise SystemExit(main())
