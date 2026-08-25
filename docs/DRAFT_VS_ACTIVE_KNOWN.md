# Draft vs published: what is already known

**Source: direct observation via the authenticated n8n MCP server on
2026-08-25.** Every statement below is an MCP observation and is *pending
confirmation by the first authenticated sync* through the public REST API. None
of it has been verified through the path this repo will actually use.

No version-id strings appear in this file. The observations were made against
specific version identifiers, but those values belong in the export the first
sync produces, not in prose written ahead of it. Describing the state is enough
to know what to expect; restating identifiers here would create a second,
unverifiable source of truth.

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

Both matter for reading this repo's exports: a draft that is "ahead" is not
necessarily a draft that *does* anything different.

## Observed state, 2026-08-25

| key | workflow | draft vs published |
|---|---|---|
| WF1 | 1 - Telegram Intake and Command Router | **draft ahead of published** |
| WF2 | 2 - Matter Classification and Planning | draft == published |
| WF3 | 3 - Evidence Intake and Storage | draft == published |
| WF4 | 4 - Research Drafting Approval and Dispatch | draft == published |
| WF5 | 5 - Inbound Replies and Daily Supervisor | **draft ahead of published** |
| WF9 | 9 - Error Handler | draft == published (a publish landed mid-session) |

### WF1 — draft ahead, via a UI autosave

The divergence was created by an editor autosave, not by an intentional change
set. It amounts to **two parameter changes and nothing else**:

1. a **reduction in `maxTokens` on the DeepSeek node**, and
2. a **Telegram node dropping a parameter whose value equalled the node
   default** — the editor's default-pruning behaviour described above, not an
   authored edit.

Neither is a structural change. No node was added, removed, or rewired.

### WF5 — draft ahead on one Code node

The draft differs from the published version on a **single Code node,
`Build Daily Digest`**. The rest of the workflow is identical across the two
sides.

### WF9 — the divergence closed itself

WF9 had a draft ahead of published earlier in the session; **a publish landed
mid-session** and the two sides converged. It is recorded here because the
transition is the useful fact: a workflow's draft/published state is live, and
a snapshot of it ages. This table describes 2026-08-25, not today.

## What the first authenticated sync should confirm

- That the public REST API exposes a populated `activeVersion` on this instance
  at all (see `docs/API_CAPABILITIES.md` — if it does not, none of the above can
  be reproduced through the public API and the exports will say so).
- That WF1 and WF5 still show a draft ahead of published, or that they no longer
  do because someone published in the interim.
- That WF2, WF3, WF4 and WF9 still show draft == published, i.e. **no file
  appears for them under `exports/draft/`**.
- That the top-level workflow body is indeed the draft and `activeVersion` is
  indeed the published body — the one inference in `API_CAPABILITIES.md` that
  the spec does not spell out in prose.

If the first sync contradicts anything above, the sync wins. It is the
first-hand reading through the interface this repo actually depends on; this
file is a prior.
