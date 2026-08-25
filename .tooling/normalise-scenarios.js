'use strict';
/**
 * normalise-scenarios.js -- one-shot, idempotent.
 *
 * Adds to every scenario file:
 *   target                    { workflow, unit_file } resolved against harness/units/index.json,
 *                             or null + target_unresolved_reason
 *   input.now                 the fixed clock every run injects
 *   input.items               $input for the unit
 *   input.nodeOutputs         { 'Node Name': [...] } for $('Node Name')
 *   harness.adapter           name of the projection in harness/adapters.js
 *
 * The ORIGINAL, QA-shaped input keys are left untouched beside the derived ones, so the
 * derivation stays reviewable: anyone can check nodeOutputs against the register it came
 * from without leaving the file.
 *
 * Run: node .tooling/normalise-scenarios.js
 */
const fs = require('fs');
const path = require('path');

const ROOT = path.join(__dirname, '..');
const DIR = path.join(ROOT, 'fixtures/scenarios');
const INDEX = JSON.parse(fs.readFileSync(path.join(ROOT, 'harness/units/index.json'), 'utf8'));
const O = require(path.join(ROOT, 'harness/oracles.js'));

const NOW = '2026-08-23T06:00:00.000Z';

function unitFile(workflow, nodeName) {
  const e = INDEX.find(u => u.workflow === workflow && u.nodeName === nodeName);
  if (!e) throw new Error('no unit for ' + workflow + ' / ' + nodeName);
  return { workflow, unit_file: 'harness/units/' + e.file };
}
const U = (w, n) => unitFile(w, n);

const files = fs.readdirSync(DIR).filter(f => f.endsWith('.json')).sort();
const S = Object.create(null);
for (const f of files) S[f.replace(/\.json$/, '')] = JSON.parse(fs.readFileSync(path.join(DIR, f), 'utf8'));

/* ---- case_id -> event index, for RUNTIME:ingressFingerprint(event of Cn) ---------- */
const eventByCase = Object.create(null);
for (const id of Object.keys(S)) {
  const j = S[id];
  const cid = j.input && j.input.case_id;
  const ev = j.input && j.input.event;
  if (!cid || !ev) continue;
  for (const tok of String(cid).split(/[\/]/)) eventByCase[tok.trim()] = ev;
}
// The round-trip suite names its first-delivery event EV_FIRST rather than a case id.
const EV_FIRST = (S['wf5-ingress-first-delivery-accept'] || {}).input
  ? S['wf5-ingress-first-delivery-accept'].input.event : null;
function resolveRuntime(v) {
  const s = String(v || '');
  if (/^<computed by ingressFingerprint\(EV_FIRST\)/.test(s)) {
    if (!EV_FIRST) throw new Error('EV_FIRST unavailable');
    return O.ingressFingerprint(EV_FIRST);
  }
  const m = /^RUNTIME:ingressFingerprint\(event of (.+)\)$/.exec(s);
  if (!m) return v;
  const ev = eventByCase[m[1].trim()];
  if (!ev) throw new Error('unknown case for runtime fingerprint: ' + v);
  return O.ingressFingerprint(ev);
}
const resolveComms = list => (list || []).map(c => {
  const o = Object.assign({}, c);
  if ('ingress_fingerprint' in o) o.ingress_fingerprint = resolveRuntime(o.ingress_fingerprint);
  return o;
});

/* ------------------------------------------------------------------ per-family rules */
const UNRESOLVED = (reason) => ({ target: null, reason });

function classify(id, j) {
  const inp = j.input || {};

  /* ---- WF5 Build Reply Context, reply-policy harness (BAKIml11QKedtH9d) ---------- */
  if (/^wf5-(reply|replypolicy)-/.test(id) && inp.register) {
    if (id === 'wf5-reply-nonaccept-outcomes-never-mutate') {
      return { target: U('wf5', 'Build Reply Context'), adapter: 'reply-policy-nonaccept' };
    }
    const ev = inp.event;
    return {
      target: U('wf5', 'Build Reply Context'),
      adapter: id === 'wf5-reply-resolver-is-deterministic' ? 'reply-determinism' : 'reply-policy',
      items: resolveComms(inp.register.comms),
      nodeOutputs: {
        'Match Reply to Matter': [{
          provider_message_id: ev.provider_message_id, thread_id: ev.thread_id,
          from_address: ev.from, subject: ev.subject, body_text: ev.body,
          received_at: ev.received_at,
        }],
        'Load Matters (Reply)': inp.register.matters || [],
        'Load Actions (Reply)': inp.register.actions || [],
        'Load Comms (Reply)': resolveComms(inp.register.comms),
      },
    };
  }

  /* ---- WF5 Build Reply Context, ingress round-trip harness (XevQwFviJHUobw0U) ---- */
  if (/^wf5-ingress-/.test(id) && inp.event && inp.communications_register) {
    const ev = inp.event;
    const comms = resolveComms(inp.communications_register);
    // The round-trip harness carries only Communications. Matters are implied by the rows:
    // resolveReply's onRegister() check needs them, and the harness's own register had
    // exactly the matters its comms name. Derived mechanically, not invented.
    const matters = Array.from(new Set(comms.map(c => String(c.matter_id)).filter(Boolean)))
      .map(m => ({ matter_id: m }));
    return {
      target: U('wf5', 'Build Reply Context'),
      adapter: 'reply-policy',
      items: comms,
      nodeOutputs: {
        'Match Reply to Matter': [{
          provider_message_id: ev.provider_message_id, thread_id: ev.thread_id,
          from_address: ev.from, subject: ev.subject, body_text: ev.body,
          received_at: ev.received_at,
        }],
        'Load Matters (Reply)': matters,
        'Load Actions (Reply)': [],
        'Load Comms (Reply)': comms,
      },
    };
  }

  /* ---- WF5 Build Daily Digest, conflict-notice sections ------------------------- */
  if (/^wf5-digest-/.test(id) && inp.register) {
    const r = inp.register;
    return {
      target: U('wf5', 'Build Daily Digest'),
      adapter: 'digest-notices',
      items: [{}],
      nodeOutputs: {
        'Load Matters (Digest)': r.matters || [],
        'Load Actions (Digest)': r.actions || [],
        'Load Approvals (Digest)': r.approvals || [],
        'Load Evidence (Digest)': r.evidence || [],
        'Load Events (Digest)': r.events || [],
        'Load Drafts (Digest)': r.drafts || [],
        'Load Conflict Notices (Digest)': r.notices || [],
      },
    };
  }

  /* ---- WF5 Build Daily Digest, isTestMatter predicate table --------------------- */
  if (id === 'wf5-digest-is-test-matter-predicate') {
    const matters = inp.cases.map(c => c.matter).filter(Boolean);
    return {
      target: U('wf5', 'Build Daily Digest'),
      adapter: 'digest-testmatter',
      items: [{}],
      nodeOutputs: {
        'Load Matters (Digest)': matters,
        'Load Actions (Digest)': [], 'Load Approvals (Digest)': [],
        'Load Evidence (Digest)': [], 'Load Events (Digest)': [],
        'Load Drafts (Digest)': [], 'Load Conflict Notices (Digest)': [],
      },
    };
  }

  /* ---- WF4 Distil Sources, alignment / excerpt suite ---------------------------- */
  if ((/^wf4-alignment-/.test(id) || /^wf4-excerpt-/.test(id)) && inp.registry_items) {
    return {
      target: U('wf4', 'Distil Sources'),
      adapter: 'distil',
      items: inp.response_items,
      nodeOutputs: {
        'Collect Evidence Text': [inp.ctx],
        'Source Registry': inp.registry_items,
      },
    };
  }

  /* ---- WF4 Distil Sources, verification-grading suite (pre-alignment fixtures) --- */
  if (/^wf4-verify-/.test(id) && inp.ctx && inp.items) {
    // These fixtures predate the Source Registry. The registry is reconstructed from
    // ctx.urls with an EMPTY want list, which is exactly the pre-alignment semantics:
    // with want_declared === 0 the alignment, contents-list and stored-excerpt rules are
    // all inert and verify() alone grades the page, as it did before the fix.
    const registry = (inp.ctx.urls || []).map(u => ({ json: { url: u, want: [], cite: '' } }));
    const items = inp.items.map((it, i) => Object.assign({}, it, { pairedItem: { item: i } }));
    return {
      target: U('wf4', 'Distil Sources'),
      adapter: 'distil-grading',
      items, nodeOutputs: { 'Collect Evidence Text': [inp.ctx], 'Source Registry': registry },
    };
  }

  /* ---- WF4 Approval Gate, delivery-key derivation ------------------------------- */
  if (/^wf4-delivery-key-/.test(id) && inp.approval && inp.action && inp.draft) {
    return { target: U('wf4', 'Approval Gate'), adapter: 'delivery-key' };
  }
  if (id === 'wf4-delivery-key-retry-after-uncertain-result') {
    return { target: U('wf4', 'Approval Gate'), adapter: 'delivery-key-retry' };
  }
  if (id === 'wf4-delivery-key-derivation-reads-no-clock') {
    return { target: U('wf4', 'Approval Gate'), adapter: 'delivery-key-no-clock' };
  }

  /* ---- WF4 Integrity Guard ------------------------------------------------------ */
  if (/^wf4-guard-/.test(id) && inp.config && inp.actions) {
    return {
      target: U('wf4', 'Integrity Guard'), adapter: 'integrity-guard',
      items: [inp.passthrough || {}],
      nodeOutputs: {
        'Config': [inp.config], 'Load Actions': inp.actions, 'Load Approvals': inp.approvals || [],
      },
    };
  }

  /* ---- WF4 Verify Selected Row (two-stage: guard -> [fault] -> verify) ---------- */
  if (/^wf4-verify-/.test(id) && inp.config && inp.actions) {
    return {
      target: U('wf4', 'Verify Selected Row'), adapter: 'verify-selected-row',
      nodeOutputs: {
        'Config': [inp.config], 'Load Actions': inp.actions, 'Load Approvals': inp.approvals || [],
      },
    };
  }

  /* ---- WF2 Finalise Plan -------------------------------------------------------- */
  const FINALISE = new Set([
    'wf2-b1-required-fact-present-classifies', 'wf2-b1-miskeyed-required-fact-is-loud',
    'wf2-b1-planner-contradiction-recorded-value-wins',
    'wf2-b1-proceed-records-unobtainable-not-verified',
    'wf2-b1-action-ids-immutable-plan-stamped', 'wf2-b1-question-hygiene-dedup',
  ]);
  if (FINALISE.has(id)) {
    const pb = inp.playbook_id || 'motor_vehicle_damage_v1';
    const plan = {
      plan_valid: inp.plan_valid !== undefined ? inp.plan_valid : true,
      matter_id: inp.matter_id || 'MAT-QA-000001',
      playbook_id: pb,
      facts_json: inp.facts_json !== undefined ? inp.facts_json : '{}',
      missing_facts_json: inp.missing_facts_json !== undefined ? inp.missing_facts_json : '[]',
      risk_flags_json: inp.risk_flags_json !== undefined ? inp.risk_flags_json : '[]',
      questions: inp.questions || [],
      actions: inp.actions || [],
      owner_summary: '',
    };
    return {
      target: U('wf2', 'Finalise Plan'), adapter: 'finalise-plan',
      items: [plan],
      nodeOutputs: {
        'Resolve Matter': [{ force_proceed: !!inp.force_proceed }],
        // The B1 harness supplied the playbook's fact vocabulary directly rather than
        // loading the 20KB Playbook Library, so the library is reconstructed from it.
        'Playbook Library': [{ playbooks: { [pb]: {
          required_facts: inp.required_facts || [], optional_facts: inp.optional_facts || [],
        } } }],
      },
    };
  }

  /* ---------------------------------------------------------------- unresolved ---- */
  const R = {
    'wf2-b1-malformed-planner-output-rejected': "The oracle is the Plan Valid? IF node plus a Capture Failure branch, not a Code node. Validate Plan JSON does emit plan_valid and failure_reason, but the scenario's expect also pins branch_taken and writes:0, which are graph properties. Binding it to Validate Plan JSON would test a strict subset while claiming the whole.",
    'wf2-legacy-positional-action-ids-collide': "Asserts the PRE-fix positional id scheme of the QA clone T6jGZRxNd9pVOfHi. The deployed Validate Plan JSON no longer mints ids that way (Finalise Plan stamps them), so there is no unit that exhibits this behaviour. Kept as a regression record.",
    'wf2-b1-marker-gate-before-any-write': 'QA-harness-only nodes (Read QA Marker / Assert QA Marker). No production unit.',
    'wf2-b1-preflight-qa-id-not-production': 'QA-harness-only node (QA Preflight). No production unit.',
    'wf2-b1-write-gate-reasserts-target': 'QA-harness-only nodes (Assert QA Before Upsert / Append). No production unit.',
    'wf4-supersede-stale-pending-approval-read-before-mutate': 'One-shot audit workflow Z0phpkSNeLngQpl1. Its decision logic was never extracted into a WF4 Code node.',
    'wf5-guarded-replay-first-delivery-new-inbound': 'QA-only Decide node from c6YPmuWf3cevjZ3r. It is the idempotency-key-shaped ANCESTOR of Build Reply Context and compares downstream products (summary, classification), which the deployed resolver deliberately does not. Binding it to build-reply-context.js would assert the superseded rule against the corrected code.',
    'wf5-guarded-replay-same-key-different-content': 'As above (QA-only ancestor logic).',
    'wf5-guarded-replay-same-key-identical-content': 'As above (QA-only ancestor logic).',
    'wf5-inbound-idempotency-key-stable-across-replay': 'The two keys are n8n Set-node expressions on Log Inbound / Append Next Action, not a Code node. Nothing in harness/units/ evaluates them.',
    'wf4-regex-host-filter-replaces-url-constructor': "The production half of the expect (prod_urls_count === 0) is only true in an environment with no global URL constructor. On Node.js it is false and the scenario's own note says the verdict flips. The filter also lives inline in Build Draft Context behind five other node reads, not as an addressable function.",
  };
  if (R[id]) return UNRESOLVED(R[id]);
  if (/^wf5-testonly-/.test(id)) {
    return UNRESOLVED("Half of the expect is resolveTestFlag(ingress), a WF5 ingress predicate that does not exist: grep finds no resolveTestFlag in any of .raw/wf{1,2,3,4,5,9}.json or in any of the 59 extracted units. Binding to Build Daily Digest would silently drop that half. The isTestMatter half is covered by wf5-digest-is-test-matter-predicate. See harness/FINDINGS.md.");
  }
  if (/^(conflictnotices|matters-|qa-harness|qa-autopilot|sheet-schema|legal-register|wf2-b1-qa-writes)/.test(id)) {
    return UNRESOLVED('Administrative / QA-infrastructure workflow. No WF1-WF5/WF9 Code node implements it.');
  }
  return UNRESOLVED('No unit in harness/units/index.json implements the behaviour this scenario names.');
}

/* -------------------------------------------------------------------------- write */
let bound = 0, unbound = 0, skipped = 0;
for (const id of Object.keys(S)) {
  const j = S[id];
  if (j.kind !== 'pure') {
    // Non-pure scenarios still get a target where one is obvious, but no context.
    j.target = j.target === undefined ? null : j.target;
    if (j.target === null && !j.target_unresolved_reason) {
      j.target_unresolved_reason = 'kind is "' + j.kind + '": not executed by harness/run.js.';
    }
    skipped++;
  } else {
    const c = classify(id, j);
    if (c.target === null || !c.target) {
      j.target = null;
      j.target_unresolved_reason = c.reason;
      delete j.harness;
      unbound++;
    } else {
      j.target = c.target;
      delete j.target_unresolved_reason;
      j.harness = { adapter: c.adapter };
      j.input.now = NOW;
      if (c.items !== undefined) j.input.items = c.items;
      if (c.nodeOutputs !== undefined) j.input.nodeOutputs = c.nodeOutputs;
      bound++;
    }
  }
  fs.writeFileSync(path.join(DIR, id + '.json'), JSON.stringify(j, null, 2) + '\n');
}
console.log('pure bound:', bound, ' pure unresolved:', unbound, ' non-pure:', skipped);
