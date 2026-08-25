# n8n-legal

A one-way mirror of six n8n workflows into git.

**Sync direction is n8n → GitHub, and only that.** GitHub never updates n8n.
Nothing in this repository issues a write to the n8n API: `scripts/sync.py`
has a single network helper, that helper asserts its method is `GET`, and there
is no other network call anywhere in the tree. Merging a pull request here
changes files in this repository and has no effect on any running workflow.

This repo is **pre-purchase scaffolding**. It contains no exports yet —
`exports/active/` and `exports/draft/` are empty and fill on the first
authenticated sync. No workflow body, version id, or hash in this repo has been
invented; every such field is `null` until a real capture populates it.

## Running a sync locally

```
N8N_BASE_URL=https://your-instance.example  N8N_API_KEY=… python3 scripts/sync.py
```

Both are read from the environment and nowhere else. The key travels as an
`X-N8N-API-KEY` header and is never printed, never put in a URL, never written
to disk.

Dry run — validates the config and the environment handling, makes no network
call:

```
python3 scripts/sync.py --dry-run
```

Before committing anything a sync produced, run the gate:

```
python3 scripts/leak_check.py            # exit 1 on any secret or PII hit
python3 scripts/leak_check.py --self-test
```

Stdlib only. No install step, locally or in CI.

## Layout

```
config/workflows.json          the six workflow ids and keys; all versions null
exports/active/                published bodies, one <KEY>.json each (empty until first sync)
exports/draft/                 drafts, only where a draft is genuinely ahead (empty until first sync)
exports/manifest.json          per-workflow hashes + capture timestamp (written by sync)
scripts/sync.py                the read-only sync
scripts/scrub.py               pattern-only scrubber; holds no real values
scripts/leak_check.py          standalone secret/PII gate, with --self-test
docs/API_CAPABILITIES.md       what the public API can actually tell us about draft vs active
docs/DRAFT_VS_ACTIVE_KNOWN.md  state observed via MCP on 2026-08-25, pending confirmation
docs/POST_PURCHASE.md          the six setup steps
docs/drift-report.md           written by sync: what changed since the previous run
.github/workflows/n8n-sync.yml scheduled sync → branch `n8n-sync` → PR into `main`
```

## What is committed

Scrubbed exports only. Every captured body passes through `scripts/scrub.py`,
which works on **patterns** — it contains no map of real values, so it cannot
leak by being read. Spreadsheet and Drive file ids, addresses, long chat ids,
API-key shapes, bearer tokens and PEM blocks become stable placeholders like
`<REDACTED_FILEID_1>`. The scrub is deterministic, so the SHA-256 in the
manifest is stable and drift detection means something.

`scripts/leak_check.py` is the gate. CI runs it *before* committing and fails
the job on a hit.

Next step: `docs/POST_PURCHASE.md`.
