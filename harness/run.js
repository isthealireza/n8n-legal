#!/usr/bin/env node
'use strict';
/**
 * harness/run.js -- runs every `pure` scenario with a resolved target against the real
 * extracted n8n Code-node unit, offline and deterministically.
 *
 *   node harness/run.js
 *   node harness/run.js --filter delivery-key
 *   node harness/run.js --workflow wf4
 *   node harness/run.js --verbose
 *
 * Determinism. Two clocks exist and both are pinned:
 *   - $now, supplied to makeContext (the shim refuses to run without it), and
 *   - the JavaScript global Date, which several units read directly
 *     (`new Date()` in Build Daily Digest and Distil Sources, `Date.now()` in Finalise
 *     Plan's plan stamp). The runner replaces global Date with a frozen subclass for the
 *     duration of each unit call and restores it afterwards, so a unit can no more reach
 *     the wall clock than it can reach the network.
 *
 * Exit code 0 only when nothing failed.
 */
const fs = require('fs');
const path = require('path');
const { makeContext } = require('./n8n-shim');
const ADAPTERS = require('./adapters');
const O = require('./oracles');

const ROOT = path.join(__dirname, '..');
const DIR = path.join(ROOT, 'fixtures/scenarios');
const FIXED_NOW = '2026-08-23T06:00:00.000Z';

/* ------------------------------------------------------------------------- args */
const argv = process.argv.slice(2);
const opt = { filter: null, workflow: null, verbose: false };
for (let i = 0; i < argv.length; i++) {
  if (argv[i] === '--filter') opt.filter = argv[++i];
  else if (argv[i] === '--workflow') opt.workflow = argv[++i];
  else if (argv[i] === '--verbose' || argv[i] === '-v') opt.verbose = true;
  else if (argv[i] === '--help' || argv[i] === '-h') {
    console.log('usage: node harness/run.js [--filter <substring>] [--workflow wfN] [--verbose]');
    process.exit(0);
  } else { console.error('unknown argument: ' + argv[i]); process.exit(2); }
}

/* -------------------------------------------------------------------- scenarios */
const ALL = fs.readdirSync(DIR).filter(f => f.endsWith('.json')).sort()
  .map(f => JSON.parse(fs.readFileSync(path.join(DIR, f), 'utf8')));
const BY_ID = Object.create(null);
for (const s of ALL) BY_ID[s.id] = s;

/* ------------------------------------------------------------- frozen global Date */
// Installed once, for the whole process. Several units read the global clock directly:
//   new Date()   -- Build Daily Digest ("today", quiet-matter and overdue arithmetic),
//                   Distil Sources (retrieved_at stamp)
//   Date.now()   -- Finalise Plan (the base36 plan stamp)
// $now alone does not reach those. Replacing the global is the only way to make them
// deterministic without editing production code, which the harness must not do.
// It is installed process-wide rather than around each call because a unit's promise
// settles on a microtask, and a per-call freeze cannot survive that boundary.
const REAL_DATE = global.Date;
function freezeGlobalClock(iso) {
  const fixed = REAL_DATE.parse(iso);
  class Frozen extends REAL_DATE {
    constructor(...a) { if (a.length === 0) super(fixed); else super(...a); }
    static now() { return fixed; }
  }
  Frozen.parse = REAL_DATE.parse; Frozen.UTC = REAL_DATE.UTC;
  global.Date = Frozen;
}
freezeGlobalClock(FIXED_NOW);

/* --------------------------------------------------------------------- unit exec */
const unitCache = Object.create(null);
function loadUnit(rel) {
  const p = path.join(ROOT, rel);
  if (!unitCache[p]) unitCache[p] = require(p);
  return unitCache[p];
}
function unitSource(rel) { return fs.readFileSync(path.join(ROOT, rel), 'utf8'); }

/**
 * Run one unit synchronously against a context built from a canonical input block:
 *   { now, items, nodeOutputs, json, helpers }
 * Units are declared `async` but every extracted unit is synchronous in body, so the
 * returned promise is already settled; the runner unwraps it without an event-loop turn
 * so the frozen clock cannot leak across scenarios.
 */
async function runUnit(rel, input) {
  const now = (input && input.now) || FIXED_NOW;
  if (now !== FIXED_NOW) freezeGlobalClock(now);
  const ctx = makeContext({
    items: input.items === undefined ? [{}] : input.items,
    nodeOutputs: input.nodeOutputs || {},
    now,
    json: input.json,
    helpers: input.helpers,
  });
  try {
    return await loadUnit(rel).run(ctx);
  } finally {
    if (now !== FIXED_NOW) freezeGlobalClock(FIXED_NOW);
  }
}

/* --------------------------------------------- shared helpers offered to adapters */
function fingerprintOfCase(caseId) {
  for (const s of ALL) {
    const cid = s.input && s.input.case_id;
    if (!cid || !s.input.event) continue;
    if (String(cid).split('/').map(x => x.trim()).includes(String(caseId).trim())) {
      return O.ingressFingerprint(s.input.event);
    }
  }
  return '(no scenario carries case ' + caseId + ')';
}

/**
 * Approval Gate STUB for the Verify Selected Row suite, matching the QA harness: the real
 * gate is out of scope there, and the stub emits only the four fields Verify consumes.
 * Recipient and channel come from the register row unless the scenario injects a fault.
 */
async function runVerify(scn, guardOut) {
  const inp = scn.input;
  const fault = inp.injected_fault || {};
  // `injected_fault` perturbs what the GATE emits, between Approval Gate and Verify.
  // `register_row_*` records what the register row says and is deliberately NOT changed:
  // the whole point of each case is that the gate and the row now disagree.
  const guardAction = guardOut.selected_action_id
    || (inp.approvals || []).filter(a => a.approval_id === (inp.config || {}).approval_id)
      .map(a => a.action_id)[0] || '';
  const actionId = fault.action_id !== undefined ? fault.action_id : guardAction;
  const row = (inp.actions || []).filter(a => a.action_id === guardAction).pop() || {};
  const gateStub = {
    gate: 'SEND',
    action_id: actionId,
    recipient: String(fault.recipient !== undefined ? fault.recipient : row.recipient),
    channel: String(fault.channel !== undefined ? fault.channel : row.channel),
  };
  // load_actions_at_verify lets a scenario simulate the register changing between
  // the Integrity Guard read (snapshot 1) and the Verify Selected Row read (snapshot 2).
  // When present, the verify step sees this array instead of inp.actions, proving
  // FINGERPRINT_CHANGED fires on a status or field change that occurred in the TOCTOU window.
  const actions = fault.load_actions_at_verify !== undefined
    ? fault.load_actions_at_verify
    : inp.actions;
  let guard = guardOut;
  if (fault.selected_rows_fingerprint) {
    guard = JSON.parse(JSON.stringify(guardOut));
    Object.keys(guard.selected_rows || {}).forEach(k => {
      guard.selected_rows[k].fingerprint = fault.selected_rows_fingerprint;
    });
  }
  return (await runUnit('harness/units/wf4/verify-selected-row.js', {
    now: inp.now, items: [gateStub],
    nodeOutputs: { 'Integrity Guard': [guard], 'Load Actions': actions },
  }))[0].json;
}

const ctxApi = {
  runUnit, unitSource, fingerprintOfCase, runVerify,
  byId: id => BY_ID[id],
  siblings: adapter => ALL.filter(s => s.kind === 'pure' && s.target && s.harness
    && s.harness.adapter === adapter),
};

/* ------------------------------------------------------------------------- select */
function selected(s) {
  if (opt.filter && s.id.indexOf(opt.filter) === -1) return false;
  if (opt.workflow && s.workflow !== opt.workflow) return false;
  return true;
}

/* --------------------------------------------------------------------------- run */
const results = { passed: [], failed: [], skipped: [] };
const skipReason = { unresolved_target: [], not_pure: [], needs_hash_regen: [], no_adapter: [] };

async function main() {
for (const s of ALL) {
  if (!selected(s)) continue;
  if (s.kind !== 'pure') { results.skipped.push(s.id); skipReason.not_pure.push(s.id + '  [' + s.kind + ']'); continue; }
  if (!s.target) {
    results.skipped.push(s.id);
    skipReason.unresolved_target.push(s.id + '  -- ' + (s.target_unresolved_reason || '(no reason recorded)'));
    continue;
  }
  const adapter = ADAPTERS[s.harness && s.harness.adapter];
  if (!adapter) {
    results.skipped.push(s.id);
    skipReason.no_adapter.push(s.id + '  -- no adapter named "' + (s.harness || {}).adapter + '"');
    continue;
  }

  let res, thrown = null;
  try { res = await adapter.run(s, ctxApi); } catch (e) { thrown = e; }

  if (thrown) {
    results.failed.push({ id: s.id, unit: s.target.unit_file, checks: [],
      error: thrown.message + '\n' + String(thrown.stack || '').split('\n').slice(1, 4).join('\n') });
    continue;
  }

  // Anti-weakening rule: every top-level `expect` key must be consumed, as a check or
  // as an explicitly declared informational key.
  // An adapter that iterates Object.keys(expect) in a switch with a failing `default`
  // declares `consumed` explicitly; otherwise fall back to matching check names.
  const consumedKeys = new Set((res.consumed || []).concat(res.informational || []));
  for (const c of res.checks) {
    for (const k of Object.keys(s.expect)) {
      if (c.key === k || c.key.indexOf(k) === 0) consumedKeys.add(k);
    }
  }
  const unconsumed = Object.keys(s.expect).filter(k => !consumedKeys.has(k));
  const checks = res.checks.concat(unconsumed.map(k => ({
    key: 'UNCONSUMED expect key "' + k + '"', expected: s.expect[k],
    actual: '(the adapter produced no check for it)', ok: false })));

  const bad = checks.filter(c => !c.ok);
  if (bad.length) results.failed.push({ id: s.id, unit: s.target.unit_file, checks: bad, detail: res.detail });
  else results.passed.push({ id: s.id, unit: s.target.unit_file, checks });
}
} // end main()

/* ------------------------------------------------------------------- invariants.md */
function writeInvariants() {
  const inv = ALL.filter(s => s.kind === 'invariant');
  const lines = [
    '# Live-register invariants',
    '',
    '_Generated by `node harness/run.js`. Do not edit by hand._',
    '',
    'These ' + inv.length + ' scenarios are properties of the **live Google Sheets register**, not of',
    'any unit. They have no `input`: there is nothing to feed a function, because the subject',
    'is the register itself as it stands right now. `harness/run.js` counts them as skipped and',
    'lists them here with the query that would check each one.',
    '',
    'Every query below is read-only (`values:batchGet` or `values.get`). None of them writes.',
    '',
  ];
  for (const s of inv) {
    lines.push('## `' + s.id + '`');
    lines.push('');
    lines.push('- **Workflow**: ' + s.workflow + '  |  **Unit under protection**: ' + s.unit);
    if (s.source_qa_workflow) {
      const q = s.source_qa_workflow;
      lines.push('- **Source QA workflow**: ' + (typeof q === 'string' ? q : (q.name + ' (`' + q.id + '`)')));
    }
    lines.push('');
    lines.push('**Property.** ' + s.description);
    lines.push('');
    lines.push('**Why it exists.** ' + s.why_it_exists);
    lines.push('');
    lines.push('**Query that would check it.**');
    lines.push('');
    lines.push('```');
    lines.push(invariantQuery(s));
    lines.push('```');
    lines.push('');
    lines.push('**Assertions.**');
    lines.push('');
    for (const a of (s.assertions || [])) lines.push('- ' + a);
    lines.push('');
    lines.push('---');
    lines.push('');
  }
  fs.writeFileSync(path.join(__dirname, 'invariants.md'), lines.join('\n'));
  return inv.length;
}

function invariantQuery(s) {
  const q = (s.expect && (s.expect.query || s.expect.check_query)) || null;
  if (q) return typeof q === 'string' ? q : JSON.stringify(q, null, 2);
  const tabs = {
    'wf4-delivery-key-is-16-char-format': ['Communications!A1:Z2000'],
    'wf4-no-unresolved-outbound-pending-or-uncertain': ['Communications!A1:Z2000'],
    'wf4-pending-approval-not-stranded-on-legacy-key': ['Communications!A1:Z2000', 'Approvals!A1:Z2000'],
    'wf4-pending-approval-references-latest-draft': ['Approvals!A1:Z2000', 'Drafts!A1:Z3000'],
    'wf4-one-pending-approval-per-action': ['Approvals!A1:Z2000'],
    'wf4-sources-no-duplicate-source-id': ['Sources!A1:Z3000'],
    'wf5-actions-no-duplicate-action-id': ['Actions!A1:Z3000'],
    'wf5-actions-no-conflicting-status-on-one-action-id': ['Actions!A1:Z3000'],
    'wf5-communications-schema-18-columns-with-ingress-fingerprint': ['Communications!A1:Z1'],
  }[s.id] || ['<tab>!A1:Z3000'];
  return 'GET https://sheets.googleapis.com/v4/spreadsheets/{SPREADSHEET_ID}/values:batchGet\n'
    + tabs.map(r => '    ?ranges=' + encodeURIComponent(r)).join('\n')
    + '\n    &valueRenderOption=UNFORMATTED_VALUE\n\n'
    + 'then, over the returned rows:\n'
    + (s.assertions || []).map(a => '  - ' + a).join('\n');
}

/* ------------------------------------------------------------------------ report */
function report(invCount) {
const pad = (s, n) => String(s).padEnd(n);
if (opt.verbose) {
  for (const p of results.passed) {
    console.log('PASS  ' + pad(p.id, 58) + p.unit);
    for (const c of p.checks) console.log('        . ' + c.key + ' = ' + JSON.stringify(c.actual));
  }
}
for (const f of results.failed) {
  console.log('FAIL  ' + pad(f.id, 58) + f.unit);
  if (f.error) console.log('        ! threw: ' + f.error.replace(/\n/g, '\n          '));
  for (const c of f.checks) {
    console.log('        x ' + c.key);
    console.log('            expected: ' + JSON.stringify(c.expected));
    console.log('            actual:   ' + JSON.stringify(c.actual));
  }
  if (opt.verbose && f.detail) console.log('        detail: ' + JSON.stringify(f.detail));
}

console.log('');
console.log('================ harness summary ================');
console.log('passed   ' + results.passed.length);
console.log('failed   ' + results.failed.length);
console.log('skipped  ' + results.skipped.length);
console.log('');
const groups = [
  ['unresolved target', skipReason.unresolved_target],
  ['no adapter', skipReason.no_adapter],
  ['kind != pure', skipReason.not_pure],
  ['needs_hash_regen (expectation not regenerable offline)', skipReason.needs_hash_regen],
];
for (const [label, list] of groups) {
  if (!list.length) continue;
  console.log('  skipped -- ' + label + ': ' + list.length);
  if (opt.verbose) for (const l of list) console.log('      ' + l);
}
if (!opt.verbose && results.skipped.length) console.log('  (--verbose lists every skip with its reason)');
if (invCount !== null) console.log('');
if (invCount !== null) console.log('  ' + invCount + ' invariant scenarios written to harness/invariants.md');
console.log('=================================================');

process.exit(results.failed.length ? 1 : 0);
}

main().then(() => report((!opt.filter && !opt.workflow) ? writeInvariants() : null),
  e => { console.error(e); process.exit(2); });
