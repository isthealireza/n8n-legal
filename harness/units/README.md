# Extracted Code-Node Units

Every JavaScript Code node (`n8n-nodes-base.code`) in `exports/wf*.json` is mirrored here
as a standalone CommonJS module that runs in plain Node — no n8n, no network, no clock.

```
harness/
  n8n-shim.js            the fake n8n runtime (makeContext)
  units/
    index.json           {workflow, nodeName, nodeId, mode, file, bytes, sha256OfJsCode}
    wf1/ wf2/ … wf9/     one <slugified-node-name>.js per Code node
```

Regenerate with:

```bash
python3 /root/n8n-legal/.tooling/extract-units.py
```

The generator is the only thing allowed to write into `units/`. **Do not hand-edit a unit
file** — it will be overwritten, and hand-edits break the invariant below.

## The verbatim invariant

Inside each module the node's `parameters.jsCode` sits **byte-identical** between:

```js
// ---- BEGIN VERBATIM n8n jsCode ----
…
// ---- END VERBATIM n8n jsCode ----
```

Nothing is reformatted, re-indented, or rewritten. That means a diff between a unit file
and the workflow export stays meaningful in both directions: you can paste the marked
region straight back into n8n, and `sha256OfJsCode` in `index.json` lets you detect drift
between the repo and a live workflow.

## The shim contract

```js
const { makeContext } = require('../../n8n-shim');
const unit = require('./wf2/finalise-plan');

const out = await unit.run(makeContext({
  items:       [ { matter_id: 'M-1' } ],          // this node's input
  nodeOutputs: { 'Config': [ { tz: 'Europe/London' } ] },  // for $('Config')
  now:         '2026-08-25T09:00:00.000Z',        // REQUIRED
}));
```

`makeContext` returns the object passed to `run()`; it is also bound as `this` inside the
node code. What the node body sees:

| global | provided by | notes |
| --- | --- | --- |
| `$input.all()` | `items` | array of `{ json }` |
| `$input.first()` / `.last()` / `.item` | `items` | `{ json }`; throws on empty, like n8n |
| `$('Node Name').first()` / `.all()` | `nodeOutputs['Node Name']` | unknown node → error naming the node and the known ones |
| `$now` | `now` | frozen Luxon-ish `DateTime` |
| `$json` | first item's `.json`, or `json:` override | |
| `$items('Node Name')` | `nodeOutputs` | legacy alias for `$(…).all()` |
| `this.helpers.*` | `helpers:` | unstubbed helper → error telling you which one to stub |

**Item shape.** `items` and each `nodeOutputs` entry accept either raw payloads
(`{ matter_id: 'M-1' }`) or n8n's wire shape (`{ json: { matter_id: 'M-1' } }`). Both are
normalised to `{ json }`, so tests can stay terse.

**Determinism.** `now` has no default. The shim never reads the system clock; omitting
`now` throws. `$now` is UTC-only and supports `toISO()`, `toISODate()`, `toMillis()`,
`toJSDate()`, `toFormat()` (Luxon tokens: `yyyy LL dd HH mm ss SSS LLLL EEE a ZZ …`, with
`'quoted literals'`), `plus()`, `minus()`, `startOf()`, `endOf()`, `diff()`. The units in
this repo currently only call `.toISO()`; the rest is there so a new n8n edit does not
immediately fall off the harness.

**Async.** `run()` is always `async` — n8n Code nodes may use top-level `await` (e.g.
`wf3/hash-file.js`, `wf3/encode-image.js`). Always `await unit.run(…)`.

**Naming.** The wrapper's parameter is `__n8nCtx`, not `ctx`, because a lot of the node
code declares its own `const ctx`.

## Adding a unit test

> The canonical way to add a test in this repo is a **scenario** — a JSON file in
> `fixtures/scenarios/` run by `harness/run.js`. See `harness/README.md`, "How to add a
> scenario". What follows is the ad-hoc route: a throwaway `node --test` file for probing a
> unit while you work it out. `harness/tests/` does not exist and is not committed; create
> it locally if you want one, and convert anything worth keeping into a scenario.

1. Find the unit in `index.json` (search by `nodeName`).
2. Work out the node's real upstream dependencies — grep the unit for `$('…')`; every name
   that appears must be given a `nodeOutputs` entry or the shim throws.
3. Write the test next to your other tests, e.g. `harness/tests/finalise-plan.test.js`:

```js
const assert = require('node:assert/strict');
const { test } = require('node:test');
const { makeContext } = require('../n8n-shim');
const unit = require('../units/wf2/finalise-plan');

const NOW = '2026-08-25T09:00:00.000Z';

test('stamps created_at from $now, not the wall clock', async () => {
  const out = await unit.run(makeContext({
    items: [{ plan: { actions: [] } }],
    nodeOutputs: { 'Config': [{ tz: 'Europe/London' }] },
    now: NOW,
  }));
  assert.equal(out[0].json.created_at, NOW);
});
```

4. Run it: `node --test harness/tests/`.

Tips:

- Start from the shim's own error messages. They name the missing node or helper, so the
  fastest way to build a fixture is to run the unit with `items: [{}]` and follow the
  throws until it completes.
- Reusable payloads belong in `fixtures/`, not inline in every test.
- Binary nodes need `helpers`, e.g.
  `makeContext({ …, helpers: { getBinaryDataBuffer: async () => Buffer.from('pdf bytes') } })`.
- Nodes with `mode: "runOnceForEachItem"` (see `index.json`) read `$json` rather than
  `$input`; pass `json:` explicitly if you want it to differ from the first item.
- If a test starts failing after someone edits the workflow in n8n, re-run the extractor
  and compare `sha256OfJsCode` in `index.json` — that tells you the node body changed
  rather than the test.

## `sha256OfJsCode` — resolved 2026-08-25

There was a window in which six unit files carried a digest computed *before*
`.tooling/scrub.py` rewrote the real identifiers in `exports/wf*.json`:

```
wf1/validate-intent-json.js   wf2/build-plan-message.js   wf2/finalise-plan.js
wf4/distil-sources.js         wf4/integrity-guard.js      wf5/build-follow-up-draft-request.js
```

They were deliberately left alone rather than hand-patched, and the extractor was re-run at
the end of the reconstruction. Re-extraction changed **only** those six digests — the
verbatim region of every unit was already byte-identical to the scrubbed export, and a
following `.tooling/scrub.py` pass reported zero replacements, which is the proof that
re-extraction cannot re-introduce a scrubbed literal.

`sha256OfJsCode` is therefore now the digest of the **scrubbed** `jsCode`, for all 59 units.
It detects drift *within this repo*. It will not match a digest taken over the live node,
because the live node still carries the real spreadsheet id, chat id and credential
references. Compare live-vs-repo by diffing the scrubbed export against a freshly scrubbed
re-export, not by comparing digests to n8n.
