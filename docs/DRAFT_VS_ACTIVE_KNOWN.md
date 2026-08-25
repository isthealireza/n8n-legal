# Draft vs published: what was observed

**Source: the authenticated n8n MCP server, read on 2026-08-25 with
`get_workflow_details`, `get_workflow_version` and `get_workflow_versions_diff`
— all read-only.** This is no longer a prior awaiting confirmation: the six
bodies in `exports/` were captured through that same session, and every version
id below is in `exports/manifest.json` and `config/workflows.json`.

What has **not** happened is a capture through the public REST API. The API was
unreachable from the capture environment — the egress proxy refused `CONNECT` to
the instance host and no API key existed — so `scripts/sync.py` has still never
run against a live instance. The table below is first-hand through MCP and
untested through REST. See `docs/API_CAPABILITIES.md`.

Version ids appear here now, where an earlier draft of this file deliberately
withheld them. The reason they were withheld was to avoid creating a second,
unverifiable source of truth alongside an export that did not yet exist. The
export exists, so the ids are observations rather than claims, and they are
copied from the same manifest the drift report is generated from.

## The mechanism worth understanding first

A **UI autosave silently creates a draft ahead of the published version.**
Nobody presses publish, nobody is prompted, and production keeps running the
older code. Open a live workflow in the n8n editor, nudge a field, walk away:
the workflow's current version has moved, the active version has not, and any
tool that reads the workflow's default body is now reading something that has
never executed.

A second, subtler effect: the n8n editor **prunes parameters whose value equals
the node default** when it saves. A node written with a default spelled out
explicitly loses that key on the first UI autosave. Nothing behavioural changed;
a diff shows a removed parameter anyway.

Both are visible in WF1 below, which is the clearest example of each.

## Observed state, 2026-08-25

`sameAsDraft` is a convenience boolean MCP returns on `activeVersion`; it agreed
with the version-id comparison on all six.

| key | workflow | published (active) version id | draft version id | draft ahead? |
|---|---|---|---|---|
| WF1 | 1 - Telegram Intake and Command Router | `b1c425bf-5830-4e3c-a6f7-bcf2c02ef593` | `9cc644ec-595d-4084-b64d-cfbe265b0712` | **yes** |
| WF2 | 2 - Matter Classification and Planning | `61e6ffee-6708-453e-ab64-8a93dfcbaa9d` | `61e6ffee-6708-453e-ab64-8a93dfcbaa9d` | no |
| WF3 | 3 - Evidence Intake and Storage | `644bbdb3-6e78-42c1-a250-3cf9ba05fadc` | `644bbdb3-6e78-42c1-a250-3cf9ba05fadc` | no |
| WF4 | 4 - Research Drafting Approval and Dispatch | `8f6b3704-7a7d-47e2-be9f-d40e7311855e` | `8f6b3704-7a7d-47e2-be9f-d40e7311855e` | no |
| WF5 | 5 - Inbound Replies and Daily Supervisor | `983da561-5c19-42db-a2b4-1e2e7ac67e0f` | `811b746c-869c-4fc3-94dc-123f60cb7067` | **yes** |
| WF9 | 9 - Error Handler | `a5b10619-31e4-4246-8988-90a08bd45ab1` | `a5b10619-31e4-4246-8988-90a08bd45ab1` | no |

`exports/draft/` holds `WF1.json` and `WF5.json` and nothing else. **The absence
of a draft file is the statement that draft == published.**

### WF1 — draft ahead: two fields, and two canvas positions

`get_workflow_versions_diff` (published `b1c425bf` → draft `9cc644ec`) reports
no node added, none removed, no connection changed, and exactly two field
changes:

1. **`DeepSeek - Router`, `parameters.options.maxTokens`: `64000` → `32768`.**
2. **`Ack Button`, `parameters.operation`: the key was removed.** Its value in
   the published body is `"answerQuery"`, which is the default operation for
   that node's `callback` resource — the editor's default-pruning behaviour
   described above, not an authored edit.

A direct comparison of the two captured bodies finds one thing the diff endpoint
does not report: **two nodes moved on the canvas.** `Ack Button` from
`[20, 420]` to `[32, 432]`, and `Is Callback?` from `[-200, 420]` to
`[-208, 432]`. A twelve- and an eight-pixel nudge is the fingerprint of a mouse,
and it is consistent with an accidental autosave. It is recorded because it is a
real difference between the two stored bodies, not because it matters — it does
not change behaviour.

So: no structural change, and no behavioural change beyond the token ceiling.

### WF5 — draft ahead on one Code node

`get_workflow_versions_diff` (published `983da561` → draft `811b746c`) reports
no node added, none removed, no connection changed, and **exactly one modified
node: the Code node `Build Daily Digest`**, on `parameters.jsCode`. That body
went from 23,691 characters over 433 lines to 20,956 characters over 412 lines
(104 lines removed, 83 added). A direct comparison of the two captured bodies
agrees: that one node, and nothing else.

Reading the two bodies side by side, the change is not only a trim. Much of the
removed volume is explanatory comment, but the draft also **rewrites the
message-budget logic**: the published version appends a bare
`[N further section(s) omitted…]` notice *after* it has finished measuring
against the 3600-character ceiling, so a truncated message always overshoots by
the length of that notice; the draft names each dropped section with its
priority and row count, and includes that block *inside* the measurement. The
draft also carries `sections_kept_titles`, `sections_omitted_detail`,
`budget_ceiling` and `budget_holds` in its diagnostics. Both bodies are in
`exports/`; this paragraph is a reading of them, and the bytes are the
authority.

### WF9 — converged

WF9's draft and published version ids are identical (`a5b10619`). An earlier
note in this repository recorded WF9 as having had a draft ahead of published
earlier the same day, with a publish landing mid-session. That transition was
not observed by this capture — only its result was. What this capture states is
the endpoint: as at 2026-08-25, the two sides agree.

## This table is a snapshot and it ages

A workflow's draft/published state is live. Everything above describes
2026-08-25. Re-run the capture (or a REST sync, once one is possible) before
relying on it.

## What a first authenticated REST sync should confirm

- That the public REST API exposes a populated `activeVersion` on this instance
  at all. If it does not, none of the above is reproducible through that
  interface, and the exports will say so.
- That the version ids above still hold, or that they have moved because
  somebody published or edited in the interim.
- That the top-level workflow body is the draft and `activeVersion` is the
  published body. MCP is unambiguous about this — it returns `activeVersionId`
  as a distinct top-level field — but `docs/API_CAPABILITIES.md` records it as
  an inference on the REST side, and it remains an inference there.
- That a REST capture of an unchanged workflow reproduces the SHA-256 digests in
  `exports/manifest.json`. It should: `capture_mcp.py` hashes with the very
  functions `sync.py` hashes with. If it does not, the difference is in the
  envelope the two paths build around the body, and that is worth knowing about
  precisely.
