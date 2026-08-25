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

## `exports/` currently holds MCP-sourced data, not a REST API sync

Read this before anything else in this file.

**The n8n public REST API is unreachable from the environment this repository
was populated in.** The egress proxy refuses `CONNECT` to the instance host
(HTTP 403) and no n8n API key exists there, so `scripts/sync.py` cannot run —
not "has not been run", *cannot*. **The REST path in `sync.py` remains untested
against a live instance.**

The six workflows were captured a different way: through the authenticated,
**read-only n8n MCP server**, on **2026-08-25**, using only
`search_workflows`, `get_workflow_details`, `get_workflow_version` and
`get_workflow_versions_diff` — the four read-only tools the capture actually
needed. `scripts/capture_mcp.py` turned
those responses into the same on-disk format `sync.py` would have produced. It
shares this repository's scrubber and its canonicalisation and hashing with
`sync.py` by *importing* them, so the two paths cannot drift apart, and it
labels its own output unmistakably: every record it writes carries
`"source": "mcp-session"` and the capture date, in `exports/manifest.json`, in
each export's `_capture` block, in `config/workflows.json` and at the top of
`docs/drift-report.md`.

So: what is in `exports/` is real, first-hand and scrubbed. It did not come
through the interface this repository is built around, and nothing here claims
it did. See `docs/API_CAPABILITIES.md` for what that leaves untested.

Nothing in this repository is invented. Every version id and hash was read from
a tool response or computed from a captured body.

## Read this before you merge the first capture

`scripts/leak_check.py` matches **shapes, not meaning**. It can recognise the
form of an API key, an address, a Drive file id, a long numeric id, a matter
reference. It cannot recognise a client's name, an opposing party, a case
summary, or a paragraph of advice — none of those have a shape.

That matters here more than it would in most repositories, because n8n sticky
notes, `jsCode` comments and LLM prompt text are **free prose**, and free prose
is exactly where a real name or a real matter description ends up. A clean gate
run means "no recognisable secret *shape* was found". It never means "nothing
confidential is in this diff".

**A human must read the first capture's diff before merging it**, in full, with
that in mind. After the first review you know what the bodies look like and
later diffs are small; the first one is the one that matters — and the first one
is the commit that added `exports/`.

That review has extra weight here, because the first real capture is also the
first time the scrubber ever saw anything but synthetic fixtures, and it found
three things the fixtures could not (see **What real data taught the scrubber**
below).

Two further limits, stated plainly:

* A long identifier split across concatenated strings or across lines
  (`"1BxiMVs0XRA5" + "nFMdKvBdBZjgm…"`) is **not** reassembled and therefore not
  detected. Detecting it line-by-line without a flood of false positives is not
  practical; it is on the reviewer.
* The scrubber replaces values it recognises with placeholders. A value in a
  shape it does not know stays in the export verbatim.

## What real data taught the scrubber

`scripts/scrub.py` and `scripts/leak_check.py` were written and self-tested
against synthetic canaries. The first run over six real workflow bodies found
three defects that no synthetic fixture had exposed. All three are fixed in the
scrubber, none by allowlisting.

1. **Credential ids survived verbatim.** An n8n node carries
   `"credentials": {"<type>": {"id": …, "name": …}}`, and the ids on this
   instance are ~16 mixed-case alphanumeric characters — below the 28-character
   floor the Drive/Sheets file-id rule needs, and with no shape that can be
   matched without eating ordinary words. Four distinct live credential handles
   were sitting in the exports. They are now found **structurally** (walk to the
   `credentials` block) and removed by literal substitution across the whole
   document, prose included, as `<REDACTED_CREDID_n>`.
2. **An identifier written with its middle elided was invisible.** A sticky note
   read ``sheet `0Aa0a0…0000` `` — both ends of a live Google Sheets file id,
   six characters and four characters, far below every length floor. This is the
   same family as the split-across-string-literals case listed under *limits*
   below, except this one has a shape and so can be caught. New `ELIDEDID` rule,
   guarded so `wait...then`, `ACT-...-003`, `1...5` and JavaScript spread syntax
   are untouched. `leak_check.py` gained the matching detector, so the gate can
   now catch what the scrubber misses.
3. **Every ISO timestamp was being redacted as a chat id.** `2026-08-18` is
   three hyphen-separated digit groups, which satisfied the split-digit-run
   rule. That is not a leak — it is the opposite, a false positive that deleted
   harmless information and made an export look redacted where nothing needed
   redacting. `leak_check.py` had guarded the identical regex with a ">= 10
   digits" test from the start and `scrub.py` had not, so the gate and the
   scrubber disagreed about the same pattern. They now share the rule.

Two things real data did **not** change, and one to keep in view:

* Node-id and `webhookId` UUIDs are preserved deliberately, as before. A
  `webhookId` is part of a production webhook path; it is kept because mangling
  node ids turns every future diff into noise, and that trade is unchanged.
* An n8n `if` node's condition ids are long digit runs and are redacted as chat
  ids. Harmless over-redaction, left alone.
* Free prose is still free prose. The gate matches shapes; it cannot see a
  client's name in a sticky note.

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

## Capturing through MCP instead

When the REST API cannot be reached — which is the situation this repository is
in — `scripts/capture_mcp.py` produces the same outputs from raw MCP responses
saved as local files. It makes no network call at all; it reads `.raw/` and
writes `exports/` and `docs/drift-report.md`.

```
python3 scripts/capture_mcp.py --dry-run                  # what it would read/write
python3 scripts/capture_mcp.py --capture-date 2026-08-25  # the capture
python3 scripts/capture_mcp.py --self-test
```

Per workflow key it wants `.raw/<KEY>.details.json` (a `get_workflow_details`
response), plus `.raw/<KEY>.activeversion.json` (a `get_workflow_version`
response for the `activeVersionId`) **only** where the draft and published
version ids differ, and optionally `.raw/<KEY>.diff.json`. If the two ids differ
and the published graph is missing, it refuses that workflow rather than filing
the draft graph under `exports/active/` and calling it published.

`.raw/` is gitignored, because raw bodies are unscrubbed. `leak_check.py` skips
it for that reason — and only while `.gitignore` still excludes it, and it
prints the skip rather than performing it silently.

Before committing anything a capture produced, run the gates:

```
python3 scripts/leak_check.py            # exit 1 on any secret or PII hit
python3 scripts/leak_check.py --self-test
python3 scripts/scrub.py --self-test
python3 scripts/capture_mcp.py --self-test
python3 scripts/sync.py --dry-run
bash    scripts/no_mutating_verbs.sh
```

Stdlib only. No install step, locally or in CI.

## Layout

```
config/workflows.json          the six workflow ids and keys, with the version ids and
                               hashes observed via MCP on 2026-08-25
exports/active/                published bodies, one <KEY>.json each — MCP-sourced
exports/draft/                 drafts, only where a draft is genuinely ahead: WF1, WF5
exports/manifest.json          per-workflow version ids and hashes (carries no wall clock)
exports/last-run.json          sync run time and status — GITIGNORED, see below
.raw/                          unscrubbed MCP responses fed to capture_mcp.py — GITIGNORED
scripts/sync.py                the read-only REST sync (never yet run against an instance)
scripts/capture_mcp.py         the MCP capture path; no network call; stamps "mcp-session"
scripts/scrub.py               pattern-only scrubber, plus one structural rule for
                               credential ids; holds no real values
scripts/leak_check.py          standalone secret/PII gate, with --self-test
scripts/no_mutating_verbs.sh   CI guard: no mutating verb beside an n8n path
docs/API_CAPABILITIES.md       what the public API can tell us about draft vs active, and
                               why none of it has been exercised yet
docs/DRAFT_VS_ACTIVE_KNOWN.md  the draft-vs-published state observed via MCP on 2026-08-25
docs/POST_PURCHASE.md          the six setup steps
docs/drift-report.md           generated: published vs draft, how they differ, and drift
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

Scrubbed exports only, and at present they are MCP-sourced. Every captured body passes through `scripts/scrub.py`,
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
