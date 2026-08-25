# n8n-legal

A one-way mirror of six n8n workflows into git.

**Sync direction is n8n → GitHub, and only that.** GitHub never updates n8n.
Nothing in this repository issues a write to the n8n API: `scripts/sync.py`
has a single network helper, that helper **raises** — it does not `assert`, so
`python3 -O` cannot strip the check — unless its method is `GET`, and there is
no other network call anywhere in the tree. `scripts/no_mutating_verbs.sh` greps
the whole tree for a mutating verb beside an n8n path and runs in CI on every
sync, so the guarantee is enforced by the pipeline rather than by a comment.
Merging a pull request here changes files in this repository and has no effect
on any running workflow.

This repo is **pre-purchase scaffolding**. It contains no exports yet —
`exports/active/` and `exports/draft/` are empty and fill on the first
authenticated sync. No workflow body, version id, or hash in this repo has been
invented; every such field is `null` until a real capture populates it.

## Read this before you merge the first sync

`scripts/leak_check.py` matches **shapes, not meaning**. It can recognise the
form of an API key, an address, a Drive file id, a long numeric id, a matter
reference. It cannot recognise a client's name, an opposing party, a case
summary, or a paragraph of advice — none of those have a shape.

That matters here more than it would in most repositories, because n8n sticky
notes, `jsCode` comments and LLM prompt text are **free prose**, and free prose
is exactly where a real name or a real matter description ends up. A clean gate
run means "no recognisable secret *shape* was found". It never means "nothing
confidential is in this diff".

**A human must read the first sync's diff before merging it**, in full, with
that in mind. After the first review you know what the bodies look like and
later diffs are small; the first one is the one that matters.

Two further limits, stated plainly:

* A long identifier split across concatenated strings or across lines
  (`"1BxiMVs0XRA5" + "nFMdKvBdBZjgm…"`) is **not** reassembled and therefore not
  detected. Detecting it line-by-line without a flood of false positives is not
  practical; it is on the reviewer.
* The scrubber replaces values it recognises with placeholders. A value in a
  shape it does not know stays in the export verbatim.

## Running a sync locally

```
N8N_BASE_URL=https://your-instance.example  N8N_API_KEY=… python3 scripts/sync.py
```

Both are read from the environment and nowhere else. The key travels as an
`X-N8N-API-KEY` header, is never printed, never put in a URL, never written to
disk.

Three rules keep it from travelling anywhere it was not meant to go:

1. **`N8N_BASE_URL` must be `https://`.** The only exception is a loopback host
   (`http://localhost`, `http://127.0.0.1`), where the traffic never leaves the
   machine. Any other `http://` URL is refused before a socket is opened.
2. **Redirects are refused outright.** `urlopen`'s default opener replays every
   request header — including `X-N8N-API-KEY` — at whatever host a `Location:`
   header names, over plaintext if it says so. One `302` was enough to hand the
   live key to a third party and have the reply accepted as a genuine workflow
   body. `sync.py` installs an opener whose redirect handler raises instead.
3. **The responding host is checked** against the configured host before the
   body is read, and the body is read under a hard size cap.

Dry run — validates the config and the environment handling, makes no network
call:

```
python3 scripts/sync.py --dry-run
```

Before committing anything a sync produced, run the gates:

```
python3 scripts/leak_check.py            # exit 1 on any secret or PII hit
python3 scripts/leak_check.py --self-test
python3 scripts/scrub.py --self-test
bash    scripts/no_mutating_verbs.sh
```

Stdlib only. No install step, locally or in CI.

## Layout

```
config/workflows.json          the six workflow ids and keys; all versions null
exports/active/                published bodies, one <KEY>.json each (empty until first sync)
exports/draft/                 drafts, only where a draft is genuinely ahead (empty until first sync)
exports/manifest.json          per-workflow hashes (written by sync; carries no timestamp)
exports/last-run.json          run time and status — GITIGNORED, see below
scripts/sync.py                the read-only sync
scripts/scrub.py               pattern-only scrubber; holds no real values
scripts/leak_check.py          standalone secret/PII gate, with --self-test
scripts/no_mutating_verbs.sh   CI guard: no mutating verb beside an n8n path
docs/API_CAPABILITIES.md       what the public API can actually tell us about draft vs active
docs/DRAFT_VS_ACTIVE_KNOWN.md  state observed via MCP on 2026-08-25, pending confirmation
docs/POST_PURCHASE.md          the six setup steps
docs/drift-report.md           written by sync: what changed since the previous run
.github/workflows/n8n-sync.yml scheduled sync → branch `n8n-sync` → PR into `main`
```

**Why the run time is not committed.** Every tracked file a sync writes is
derived from the captured content alone. Stamping the wall clock into
`manifest.json` or the drift report made every scheduled run a content change,
so the Action committed and force-pushed roughly 96 times a day and kept a pull
request open claiming things had changed when nothing had. Timestamps now live
in `exports/last-run.json`, which is gitignored, and the Action's "commit only
if something changed" step is finally true.

## What is committed

Scrubbed exports only. Every captured body passes through `scripts/scrub.py`,
which works on **patterns** — it contains no map of real values, so it cannot
leak by being read. Spreadsheet and Drive file ids, addresses, long chat ids,
API-key shapes, bearer tokens, webhook URLs and PEM blocks become stable
placeholders like `<REDACTED_FILEID_1>`.

Placeholder numbers are ordinals over the **sorted distinct values** in the
document, not the order they were first seen in. That is what makes the scrub
both stable and meaningful: swapping two real values changes the hash (a real
change stays visible), and reordering keys does not (no fabricated drift). The
reasoning, and the option rejected, is argued in the `scripts/scrub.py`
docstring.

`scripts/leak_check.py` is the gate. CI runs it *before* committing and fails
the job on a hit. Nothing in the *content* of a scanned file can switch it off:
allow-markers found in text are ignored entirely, because most of what it scans
is free prose fetched from n8n. The only suppression mechanism is an explicit
(path, detector, value) allowlist held in the script itself, and it may never
name anything under `exports/`.

Next step: `docs/POST_PURCHASE.md`.
