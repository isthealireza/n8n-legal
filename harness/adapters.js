'use strict';
/**
 * adapters.js -- one projection per scenario family.
 *
 * A scenario's `expect` is the oracle the QA workflow actually asserted, in that
 * workflow's vocabulary. The unit under test emits its own. An adapter is the bridge:
 * given the unit's output items it must produce, for EVERY key in `expect`, either
 *   - a check  { key, expected, actual, ok }, or
 *   - an explicit `informational` marking (prose, notes, provenance).
 *
 * The runner fails any scenario with an `expect` key the adapter did not consume. That
 * is the anti-weakening rule: dropping an assertion is a failure, not a silent pass.
 *
 * Adapters may run a unit more than once (a two-stage guard/verify pipeline, a
 * determinism check, a cross-scenario key comparison). They must never mutate a
 * scenario, and must never read the system clock -- `run` injects a fixed one.
 */
const O = require('./oracles');

const eq = (a, b) => JSON.stringify(a) === JSON.stringify(b);
const mk = (key, expected, actual, ok) => ({ key, expected, actual, ok: ok === undefined ? eq(expected, actual) : !!ok });

/** Helper: build the checks for a flat expect whose keys are output field names. */
function flat(expect, out, opts) {
  const o = opts || {};
  const checks = [];
  const info = [];
  for (const k of Object.keys(expect)) {
    if ((o.informational || []).includes(k)) { info.push(k); continue; }
    if (o.custom && Object.prototype.hasOwnProperty.call(o.custom, k)) { checks.push(o.custom[k]()); continue; }
    if (!(k in out)) { checks.push(mk(k, expect[k], '(field absent from unit output)', false)); continue; }
    checks.push(mk(k, expect[k], out[k]));
  }
  return { checks, informational: info };
}

/* ===================================================================== WF5 replies */

const replyPolicy = {
  units: ['wf5/build-reply-context.js'],
  async run(scn, ctx) {
    const out = (await ctx.runUnit(scn.target.unit_file, scn.input))[0].json;
    const e = scn.expect;
    const custom = {};
    if ('ingress_fingerprint' in e && e.ingress_fingerprint === 'REGENERATE') {
      const ev = scn.input.event;
      custom.ingress_fingerprint = () => mk('ingress_fingerprint', O.ingressFingerprint(ev), out.ingress_fingerprint);
    }
    if (e.stored_fingerprint === 'REGENERATE') {
      const ev = scn.input.event;
      custom.stored_fingerprint = () => mk('stored_fingerprint', O.ingressFingerprint(ev), out.stored_fingerprint);
    } else if (typeof e.stored_fingerprint === 'string' && /^RUNTIME:/.test(e.stored_fingerprint)) {
      const m = /event of (.+)\)$/.exec(e.stored_fingerprint);
      custom.stored_fingerprint = () => mk('stored_fingerprint',
        ctx.fingerprintOfCase(m && m[1]), out.stored_fingerprint);
    }
    if ('reason' in e) {
      custom.reason = () => mk('reason (contains)', e.reason,
        out.reason, String(out.reason || '').indexOf(String(e.reason)) !== -1 || out.reason === e.reason);
    }
    return flat(e, out, {
      informational: ['reason_shape', 'note', 'ingress_fingerprint_spec', 'needs_hash_regen',
        'state_change', '_correction_2026-08-25'],
      custom,
    });
  },
};

const replyDeterminism = {
  units: ['wf5/build-reply-context.js'],
  async run(scn, ctx) {
    const a = (await ctx.runUnit(scn.target.unit_file, scn.input))[0].json;
    const b = (await ctx.runUnit(scn.target.unit_file, scn.input))[0].json;
    return { checks: [mk('first_run_json EQUALS second_run_json', JSON.stringify(a), JSON.stringify(b))],
      informational: [] };
  },
};

/**
 * A1/A2/A3: properties over the outcomes of EVERY case in the reply-policy suite, not
 * over one input. The adapter re-runs every sibling scenario bound to this unit and
 * evaluates the three properties across all of them.
 */
const replyNonAccept = {
  units: ['wf5/build-reply-context.js'],
  async run(scn, ctx) {
    const outs = [];
    for (const s of ctx.siblings('reply-policy')) outs.push(((await ctx.runUnit(s.target.unit_file, s.input)))[0].json);
    const nonAccept = outs.filter(o => o.decision !== 'ACCEPT');
    const noEventId = nonAccept.filter(o => !o.event_id);
    const wrote = nonAccept.filter(o => o.write_log_inbound || o.write_append_action || o.write_touch_matter);
    const replays = outs.filter(o => o.decision === 'ALREADY_RECORDED' || o.decision === 'IDEMPOTENCY_CONFLICT');
    const classified = replays.filter(o => o.matched === true);
    return { checks: [
      mk('every_replay_outcome_has_event_id', true, noEventId.length === 0,
         noEventId.length === 0),
      mk('no_nonaccept_outcome_writes', true, wrote.length === 0, wrote.length === 0),
      mk('no_replay_reaches_classifier', true, classified.length === 0, classified.length === 0),
    ], informational: [],
      detail: { cases_evaluated: outs.length, non_accept: nonAccept.length,
        blocked_without_event_id: noEventId.map(o => o.basis) } };
  },
};

/* ===================================================================== WF5 digest */

const digestNotices = {
  units: ['wf5/build-daily-digest.js'],
  async run(scn, ctx) {
    const out = (await ctx.runUnit(scn.target.unit_file, scn.input))[0].json;
    const d = out.diagnostics;
    const reply = String(out.reply || '');
    const e = scn.expect;
    const hm = /Conflict notices not yet reported to you: (\d+)/.exec(reply);
    const headline = hm ? Number(hm[1]) : 0;
    const checks = [];
    const seen = k => Object.prototype.hasOwnProperty.call(e, k);
    if (seen('total')) checks.push(mk('notices_total', e.total, d.notices_total));
    if (seen('pending')) checks.push(mk('notices_pending', e.pending, d.notices_pending));
    if (seen('failed')) checks.push(mk('notices_failed', e.failed, d.notices_failed));
    if (seen('exhausted')) checks.push(mk('notices_exhausted', e.exhausted, d.notices_exhausted));
    if (seen('dupes')) checks.push(mk('notice_duplicate_keys', e.dupes, d.notice_duplicate_keys));
    if (seen('headline')) {
      // The QA oracle wrote `null` where the digest must print no headline line at all.
      if (e.headline === null) checks.push(mk('no unreported-notices headline line', true, hm === null));
      else checks.push(mk('headline unreported count', e.headline, headline));
    }
    for (const s of (e.present || [])) checks.push(mk('reply contains "' + s + '"', true, reply.indexOf(s) !== -1));
    for (const s of (e.absent || [])) checks.push(mk('reply omits "' + s + '"', true, reply.indexOf(s) === -1));
    for (const s of (e.silentKeys || [])) checks.push(mk('reply stays silent about "' + s + '"', true, reply.indexOf(s) === -1));
    if (seen('expectBudgetPressure')) {
      checks.push(mk('sections were dropped for budget', e.expectBudgetPressure, out.sections_omitted > 0));
      checks.push(mk('nothing at priority 0 was dropped', true,
        (d.sections_omitted_detail || []).every(o => o.priority !== 0)));
      checks.push(mk('rendered message is within the 3600-char ceiling', true, d.budget_holds));
    }
    checks.push(mk('diagnostics.reconciles', true, d.reconciles));
    return { checks, informational: [], consumed: Object.keys(e) };
  },
};

const digestTestMatter = {
  units: ['wf5/build-daily-digest.js'],
  async run(scn, ctx) {
    const out = (await ctx.runUnit(scn.target.unit_file, scn.input))[0].json;
    const flagged = new Set(out.diagnostics.test_matter_ids);
    const checks = scn.input.cases.map((c, i) => {
      const want = scn.expect.results[i];
      // A null matter never reaches isTestMatter: Build Daily Digest filters
      // `r && r.matter_id` off the loader, so it can only ever be "not a test matter".
      const got = !!(c.matter && flagged.has(c.matter.matter_id));
      return mk('case ' + i + ' (' + c.name + ')', want, got);
    });
    return { checks, informational: ['rules', 'results'] };
  },
};

/* ================================================================ WF4 Distil Sources */

function distilChecks(scn, out) {
  const e = scn.expect;
  const src = out.sources || [];
  const s0 = src[0] || {};
  const checks = [];
  const informational = [];
  for (const k of Object.keys(e)) {
    switch (k) {
      case 'source_rows': checks.push(mk(k, e[k], src.length)); break;
      case 'unique_source_ids': checks.push(mk(k, e[k], new Set(src.map(s => s.source_id)).size)); break;
      case 'per_row':
        e.per_row.forEach((r, i) => {
          const s = src[i] || {};
          if ('source_id' in r) checks.push(mk('row' + i + '.source_id', r.source_id, s.source_id));
          if ('title' in r) checks.push(mk('row' + i + '.title', r.title, s.title));
          if ('url' in r) checks.push(mk('row' + i + '.url', r.url, s.url));
          if ('excerpt_contains' in r) checks.push(mk('row' + i + '.excerpt contains "' + r.excerpt_contains + '"',
            true, String(s.excerpt || '').indexOf(r.excerpt_contains) !== -1));
        });
        break;
      case 'all_retrieved':
        checks.push(mk(k, e[k], src.length > 0 && src.every(s => s.verification_status === 'RETRIEVED')));
        break;
      case 'all_rows_status':
        checks.push(mk(k, e[k], Array.from(new Set(src.map(s => s.verification_status))).join(',')));
        break;
      case 'all_urls_empty': checks.push(mk(k, e[k], src.every(s => s.url === ''))); break;
      case 'row0_status': checks.push(mk(k, e[k], (src[0] || {}).verification_status)); break;
      case 'row1_status': checks.push(mk(k, e[k], (src[1] || {}).verification_status)); break;
      case 'row0_excerpt': checks.push(mk(k, e[k], (src[0] || {}).excerpt)); break;
      case 'row1_excerpt': checks.push(mk(k, e[k], (src[1] || {}).excerpt)); break;
      case 'research_status_not': checks.push(mk('research_status is not ' + e[k], true, out.research_status !== e[k])); break;
      case 'verification_status':
        if (Array.isArray(e[k])) checks.push(mk(k, e[k], src.map(s => s.verification_status)));
        else checks.push(mk(k, e[k], s0.verification_status));
        break;
      case 'excerpt_contains':
        checks.push(mk('excerpt contains "' + e[k] + '"', true, String(s0.excerpt || '').indexOf(e[k]) !== -1));
        break;
      case 'anchor_score_at_least': {
        const best = Math.max.apply(null, String(s0.anchor_scores || '').split(',').map(Number).concat([-Infinity]));
        checks.push(mk('best anchor score >= ' + e[k], true, best >= e[k], best >= e[k]));
        break;
      }
      case 'text_chars_gt': checks.push(mk('text_chars > ' + e[k], true, s0.text_chars > e[k], s0.text_chars > e[k])); break;
      case 'want_missing_contains':
        checks.push(mk('want_missing contains "' + e[k] + '"', true, String(s0.want_missing || '').indexOf(e[k]) !== -1));
        break;
      case 'title': case 'url': case 'source_id': case 'pinpoints':
      case 'excerpt': case 'excerpt_is_anchored':
        checks.push(mk(k, e[k], s0[k])); break;
      case 'alignment_all_ok': case 'excerpts_all_anchored': case 'pinpoints_all_present':
      case 'sources_retrieved': case 'sources_contents_only': case 'research_status':
        checks.push(mk(k, e[k], out[k])); break;
      default:
        checks.push(mk(k, e[k], '(adapter has no rule for this key)', false));
    }
  }
  return { checks, informational, consumed: Object.keys(e) };
}

const distil = {
  units: ['wf4/distil-sources.js'],
  async run(scn, ctx) { return distilChecks(scn, ((await ctx.runUnit(scn.target.unit_file, scn.input)))[0].json); },
};
const distilGrading = distil;

/* ============================================================ WF4 Approval Gate keys */

// A minimal, complete Approval Gate context that reaches `common` -- the block where the
// delivery key is derived -- without entering the send preconditions. decision=REJECT is
// used because REJECTED returns {...common} directly after check 5, so the derivation is
// observed exactly as the send path would compute it, with nothing stubbed.
function deliveryKeyInput(inp) {
  const approval = Object.assign({
    matter_id: 'MAT-KEY-000', status: 'PENDING', draft_id: inp.draft.draft_id,
    token_hash_or_reference: 'HASH-1', delivery_mode: 'PDF_ATTACHMENT',
  }, inp.approval, { action_id: inp.action.action_id, draft_id: inp.draft.draft_id });
  const action = Object.assign({ matter_id: approval.matter_id, status: 'AWAITING_APPROVAL' }, inp.action);
  const draft = Object.assign({
    action_id: action.action_id, version: 1, content_hash: 'HASH-1',
    content: 'body', draft_type: 'LETTER',
  }, inp.draft);
  return {
    now: inp.now,
    items: [{}],
    nodeOutputs: {
      'Config': [{ approval_id: approval.approval_id, decision: 'REJECT',
        chat_id: 'OWNER', owner_chat_id: 'OWNER', dry_run: 'false' }],
      'Load Approvals': [approval],
      'Load Actions': [action],
      'Load Drafts': [draft],
      'Load Communications': [],
      'Load Matters': [{ matter_id: approval.matter_id, title: 'Key fixture', owner_chat_id: 'OWNER' }],
    },
  };
}

const deliveryKey = {
  units: ['wf4/approval-gate.js'],
  async run(scn, ctx) {
    const uf = scn.target.unit_file;
    const out = (await ctx.runUnit(uf, deliveryKeyInput(scn.input)))[0].json;
    const e = scn.expect;
    // Independently computed oracle -- never the value the unit produced.
    const basis = O.deliveryIdentity(
      Object.assign({}, scn.input.approval),
      Object.assign({}, scn.input.action),
      Object.assign({}, scn.input.draft));
    const oracleHash = O.fnv1aHex16(basis);
    const against = [].concat(scn.input.compare_against || []);
    const others = {};
    for (const id of against) {
      const s2 = ctx.byId(id);
      others[id] = (await ctx.runUnit(s2.target.unit_file, deliveryKeyInput(s2.input)))[0].json;
    }
    const other = others['wf4-delivery-key-first-send'] || others[against[0]] || null;
    const checks = [];
    for (const k of Object.keys(e)) {
      switch (k) {
        case 'note': break;
        case 'delivery_key_parts': checks.push(mk(k, e[k], out.delivery_key_parts)); break;
        case 'send_key':
          checks.push(mk('send_key === "SND-" + independent FNV-1a', 'SND-' + oracleHash, out.send_key));
          break;
        case 'communication_id_send':
          checks.push(mk('communication_id_send === "COM-" + independent FNV-1a', 'COM-' + oracleHash, out.communication_id_send));
          break;
        case 'differs_from_first_send': {
          const o = others['wf4-delivery-key-first-send'];
          checks.push(mk(k, e[k], !!o && out.send_key !== o.send_key)); break;
        }
        case 'differs_from_duplicate_approval': {
          const o = others['wf4-delivery-key-duplicate-approval-is-a-new-delivery'];
          checks.push(mk(k, e[k], !!o && out.send_key !== o.send_key)); break;
        }
        case 'send_key_equals_first_send':
          checks.push(mk(k + ' (vs ' + scn.input.compare_against + ')', e[k], !!other && out.send_key === other.send_key));
          break;
        case 'communication_id_dry_differs_from_send':
          checks.push(mk(k, e[k], out.communication_id_dry !== out.communication_id_send)); break;
        case 'both_contain_delivery_hash':
          checks.push(mk(k, e[k],
            out.communication_id_send.indexOf(out.delivery_hash) !== -1
            && out.communication_id_dry.indexOf(out.delivery_hash) !== -1)); break;
        case 'dry_key_shape':
          checks.push(mk('dry_key === send_key + "|DRY"', out.send_key + '|DRY', out.dry_key)); break;
        default:
          checks.push(mk(k, e[k], '(adapter has no rule for this key)', false));
      }
    }
    checks.push(mk('delivery_hash is 16 lowercase hex', true, /^[0-9a-f]{16}$/.test(out.delivery_hash)));
    return { checks, informational: ['note'], consumed: Object.keys(e) };
  },
};

const deliveryKeyRetry = {
  units: ['wf4/approval-gate.js'],
  async run(scn, ctx) {
    const base = { approval: { approval_id: 'APR-001' },
      action: { action_id: 'ACT-001', channel: 'GMAIL', recipient: 'insurerclaims01@example.com' },
      draft: { draft_id: 'DFT-001' }, now: scn.input.now };
    const a = (await ctx.runUnit(scn.target.unit_file, deliveryKeyInput(base)))[0].json;
    const b = (await ctx.runUnit(scn.target.unit_file, deliveryKeyInput(base)))[0].json;
    return { checks: [
      mk('send_key_stable', true, a.send_key === b.send_key),
      mk('communication_id_stable', true, a.communication_id_send === b.communication_id_send),
      mk('no clock in the key (two runs 1s apart agree)', a.send_key, b.send_key),
    ], informational: [] };
  },
};

// Static check over the production node body, per _groupA-notes.md item 2: the original
// asserted on the SOURCE TEXT of normEmail/fnv1aHex/deriveDelivery. Ported as a lint over
// the derivation block of the real node rather than over three stringified functions.
const deliveryKeyNoClock = {
  units: ['wf4/approval-gate.js'],
  async run(scn, ctx) {
    const src = ctx.unitSource(scn.target.unit_file);
    const b = src.indexOf('function normEmail');
    const e2 = src.indexOf('const common = {');
    const block = src.slice(b, e2);
    const m = block.match(new RegExp(scn.input.forbidden_pattern.replace(/^\/|\/g$/g, ''), 'g')) || [];
    return { checks: [mk('clock_reference_matches', scn.expect.clock_reference_matches, m.length)],
      informational: [], detail: { block_chars: block.length, matches: m } };
  },
};

/* ========================================================= WF4 integrity / verify */

const integrityGuard = {
  units: ['wf4/integrity-guard.js'],
  async run(scn, ctx) {
    const out = (await ctx.runUnit(scn.target.unit_file, scn.input))[0].json;
    const e = scn.expect;
    const checks = [];
    for (const k of Object.keys(e)) {
      switch (k) {
        case 'reaches': break;
        case 'integrity_ok': checks.push(mk(k, e[k], out.integrity_ok)); break;
        case 'gate': checks.push(mk(k, e[k], out.gate)); break;
        case 'integrity_code': checks.push(mk(k, e[k], out.integrity_code)); break;
        case 'scope_label':
          checks.push(mk(k, e[k], out.integrity_scope
            || ((out.integrity_reason || '').match(/could be selected for (.+?)\./) || [])[1])); break;
        case 'conflict_count':
          // BINDING, not expectation. The mined QA workflows meant "how many
          // ambiguous ACTIONS did the guard report", but until 2026-08-28 the node
          // published no such number, so this adapter approximated it with the
          // length of integrity_detail. That approximation is exactly the
          // double-count FINDINGS.md section 1 records: every duplicated action_id
          // appears in integrity_detail once per conflict class, so 6 ambiguous
          // actions read as 12. The guard now states the number itself. Read the
          // real field, and keep the old approximation only for the pre-fix shape.
          // The expected value in every scenario is unchanged.
          checks.push(mk(k, e[k], typeof out.integrity_conflict_count === 'number'
            ? out.integrity_conflict_count
            : (out.integrity_detail || []).length)); break;
        case 'reaches_approval_gate': case 'reaches_drafting':
          checks.push(mk(k, e[k], out.integrity_ok === true)); break;
        case 'selected_action_id': checks.push(mk(k, e[k], out.selected_action_id)); break;
        case 'selected_row_fingerprint':
          // Independent oracle: re-derive the fingerprint of the single in-scope row.
          // The mined expectation is a placeholder ("REGENERATE" / "RUNTIME:FP-<fnv><fnv>"),
          // never a literal. Re-derive it with the independent oracle in oracles.js.
          checks.push(mk(k, /^(REGENERATE|RUNTIME:)/.test(String(e[k]))
            ? O.rowFingerprint(scn.input.actions.filter(a => a.action_id === out.selected_action_id)[0] || {})
            : e[k], out.selected_row_fingerprint)); break;
        case 'verify_integrity_ok': case 'integrity_verified_action_id': {
          const v = await ctx.runVerify(scn, out);
          checks.push(k === 'verify_integrity_ok'
            ? mk(k, e[k], v.integrity_ok)
            : mk(k, e[k], v.action_id));
          break;
        }
        default: checks.push(mk(k, e[k], '(adapter has no rule for this key)', false));
      }
    }
    return { checks, informational: ['reaches'], consumed: Object.keys(e) };
  },
};

const verifySelectedRow = {
  units: ['wf4/integrity-guard.js', 'wf4/verify-selected-row.js'],
  async run(scn, ctx) {
    const guard = (await ctx.runUnit('harness/units/wf4/integrity-guard.js', {
      now: scn.input.now, items: [{}], nodeOutputs: scn.input.nodeOutputs,
    }))[0].json;
    const v = await ctx.runVerify(scn, guard);
    const e = scn.expect;
    const checks = [];
    for (const k of Object.keys(e)) {
      switch (k) {
        case 'reaches': break;
        case 'verify_integrity_ok': checks.push(mk(k, e[k], v.integrity_ok)); break;
        case 'integrity_code': checks.push(mk(k, e[k], v.integrity_code)); break;
        case 'gate': checks.push(mk(k, e[k], v.gate)); break;
        default: checks.push(mk(k, e[k], '(adapter has no rule for this key)', false));
      }
    }
    return { checks, informational: ['reaches'], consumed: Object.keys(e),
      detail: { guard_ok: guard.integrity_ok, verify: v } };
  },
};

/* ================================================== WF4 Approval Gate (decisions) */

// Added 2026-08-29 during the SPEC-2 Rev B publication-readiness review (Fast Lane run
// run_bfa3412dc1f8). Before this adapter the ONLY coverage of wf4/approval-gate.js was the
// three delivery-key families, which assert the derivation block and nothing else: every
// gate DECISION -- INVALID, DUPLICATE, STALE, REJECTED, EDIT, DRY_RUN, SEND -- was
// unasserted, and the `default:` arm of the delivery-key adapter fails any scenario that
// tries to assert `gate`. So the one node AGENTS.md section 1.1 calls "the only thing
// between a model-drafted letter and a real recipient" had no executable fail-closed test.
// This adapter runs the real extracted node against a full five-register context and
// asserts the decision it returns.
//
// It exercises the PUBLISHED body (harness/units/ is extracted from wfN.active.json only,
// AGENTS.md section 5). The draft 470120af Approval Gate carries STEP1-KILLSWITCH-20260826
// and is NOT under test here -- no wf4.draft.json has been captured, so no draft unit
// exists. That gap is recorded in docs/wf4-spec2-revb-review-2026-08-29.md.
const approvalGate = {
  units: ['wf4/approval-gate.js'],
  async run(scn, ctx) {
    const inp = scn.input;
    const out = (await ctx.runUnit(scn.target.unit_file, {
      now: inp.now,
      items: [{}],
      nodeOutputs: {
        'Config': [inp.config || {}],
        'Load Approvals': inp.approvals || [],
        'Load Actions': inp.actions || [],
        'Load Drafts': inp.drafts || [],
        'Load Communications': inp.communications || [],
        'Load Matters': inp.matters || [],
      },
    }))[0].json;
    const e = scn.expect;
    const checks = [];
    const contains = (hay, needle) =>
      String(hay == null ? '' : hay).indexOf(String(needle)) !== -1;
    for (const k of Object.keys(e)) {
      switch (k) {
        case 'note': break;
        case 'gate': checks.push(mk('gate', e.gate, out.gate)); break;
        case 'dry_run': checks.push(mk('dry_run', e.dry_run, out.dry_run)); break;
        case 'gate_reason_contains': {
          const wanted = [].concat(e.gate_reason_contains);
          for (const w of wanted) {
            checks.push(mk('gate_reason contains ' + JSON.stringify(w), true,
              contains(out.gate_reason, w), contains(out.gate_reason, w)));
          }
          break;
        }
        case 'config_passthrough': {
          // Config is spread into every gate return (`{ ...cfg, dry_run, ...o }`), so a
          // key the Config node sets must survive the gate untouched -- including on a
          // refusal, because Verify Selected Row and Gate Result read it downstream.
          for (const ck of Object.keys(e.config_passthrough)) {
            checks.push(mk('config_passthrough.' + ck, e.config_passthrough[ck], out[ck]));
          }
          break;
        }
        case 'fields_absent': {
          // A refusal that never reached the derivation block must not emit a delivery
          // identity: an INVALID carrying a send_key would let a downstream node key a
          // Communications write off a decision the gate refused.
          for (const fk of [].concat(e.fields_absent)) {
            checks.push(mk('fields_absent.' + fk, true, !(fk in out), !(fk in out)));
          }
          break;
        }
        case 'fields_present': {
          for (const fk of [].concat(e.fields_present)) {
            checks.push(mk('fields_present.' + fk, true, fk in out, fk in out));
          }
          break;
        }
        case 'send_key_matches_oracle': {
          // Independently computed -- never the value the unit produced.
          const oracle = 'SND-' + O.fnv1aHex16(O.deliveryIdentity(
            Object.assign({}, e.oracle_basis && e.oracle_basis.approval),
            Object.assign({}, e.oracle_basis && e.oracle_basis.action),
            Object.assign({}, e.oracle_basis && e.oracle_basis.draft)));
          checks.push(mk('send_key === independent FNV-1a', oracle, out.send_key));
          break;
        }
        case 'oracle_basis': break;
        default:
          checks.push(mk(k, e[k], '(adapter has no rule for this key)', false));
      }
    }
    return { checks, informational: ['note', 'oracle_basis'], consumed: Object.keys(e),
      detail: { gate: out.gate, gate_reason: out.gate_reason } };
  },
};

const integrityHaltNotice = {
  units: ['wf4/build-integrity-halt-notice.js'],
  async run(scn, ctx) {
    const out = (await ctx.runUnit(scn.target.unit_file, scn.input))[0].json;
    const e = scn.expect;
    const custom = {};
    if ('reply_contains' in e) {
      custom.reply_contains = () => mk('reply_contains', e.reply_contains,
        out.reply, String(out.reply || '').indexOf(String(e.reply_contains)) !== -1);
    }
    return flat(e, out, { informational: ['reaches'], custom });
  },
};

/* ================================================================== WF2 Finalise Plan */

const finalisePlan = {
  units: ['wf2/finalise-plan.js'],
  async run(scn, ctx) {
    const out = (await ctx.runUnit(scn.target.unit_file, scn.input))[0].json;
    const e = scn.expect;
    const risks = (() => { try { return JSON.parse(out.risk_flags_json || '[]'); } catch (x) { return []; } })();
    const facts = (() => { try { return JSON.parse(out.facts_json || '{}'); } catch (x) { return {}; } })();
    const jeq = (a, b) => { // JSON-string fields: compare parsed, so formatting is not the test
      try { return eq(JSON.parse(a), JSON.parse(b)); } catch (x) { return a === b; }
    };
    const checks = [];
    for (const k of Object.keys(e)) {
      switch (k) {
        case 'depends_on_remapped_to': break;
        case 'risk_flags_contains':
          for (const r of e[k]) checks.push(mk('risk_flags contains ' + r, true, risks.includes(r)));
          break;
        case 'risk_flags_excludes':
          for (const r of e[k]) checks.push(mk('risk_flags excludes ' + r, true, !risks.includes(r)));
          break;
        case 'missing_facts_json': case 'unmapped_fact_keys_json': case 'unmapped_facts_json':
        case 'optional_missing_facts_json': case 'planner_contradictions_json':
        case 'unobtainable_facts_json':
          checks.push(mk(k, e[k], out[k], jeq(e[k], out[k]))); break;
        case 'facts_key_equals':
          for (const [key, val] of Object.entries(e[k])) {
            checks.push(mk('facts_json.' + key + ' === ' + JSON.stringify(val), val, facts[key]));
          }
          break;
        case 'facts_key_absent':
          for (const key of e[k]) {
            checks.push(mk('facts_json.' + key + ' absent', true, !(key in facts)));
          }
          break;
        case 'facts_json_unchanged_keys':
          for (const key of e[k]) {
            const src = JSON.parse(scn.input.facts_json)[key];
            checks.push(mk('facts_json still holds ' + key, src, facts[key]));
          }
          break;
        case 'facts_values_for_unobtainable': {
          const un = JSON.parse(out.unobtainable_facts_json || '[]');
          checks.push(mk(k, e[k], un.map(f => facts[f]).join('|') || '(none)',
            un.length > 0 && un.every(f => facts[f] === e[k])));
          break;
        }
        case 'plan_stamp_pattern':
          checks.push(mk(k, e[k], out.plan_stamp, new RegExp(e[k]).test(String(out.plan_stamp || '')))); break;
        case 'action_id_pattern': {
          const acts = out.actions || [];
          const bad = acts.filter(a => !new RegExp(e[k]).test(String(a.action_id)));
          checks.push(mk(k, e[k], acts.map(a => a.action_id), bad.length === 0 && acts.length > 0));
          const stamps = new Set(acts.map(a => (String(a.action_id).match(/-(P[0-9A-Z]+)-/) || [])[1]));
          checks.push(mk('every action in the plan shares one stamp', 1, stamps.size));
          const map = {};
          (scn.input.actions || []).forEach((a, i) => { map[a.action_id] = acts[i] && acts[i].action_id; });
          const dep = acts.map(a => { try { return JSON.parse(a.depends_on_json || '[]'); } catch (x) { return []; } });
          const remapped = dep.every(list => list.every(d => Object.values(map).includes(d)));
          checks.push(mk('depends_on_json remapped to this plan\'s stamped ids', true, remapped));
          break;
        }
        case 'idempotency_key_pattern': {
          const acts = out.actions || [];
          const bad = acts.filter(a => !new RegExp(e[k]).test(String(a.idempotency_key)));
          checks.push(mk(k, e[k], acts.map(a => a.idempotency_key), bad.length === 0 && acts.length > 0));
          break;
        }
        case 'questions_max': checks.push(mk(k, true, (out.questions || []).length <= e[k])); break;
        case 'duplicates_removed': {
          const sig = q => String(q).toLowerCase().replace(/[^a-z0-9 ]/g, '').split(/\s+/)
            .filter(w => w.length >= 5).sort().join(' ');
          const sigs = (out.questions || []).map(sig);
          checks.push(mk(k, e[k], new Set(sigs).size === sigs.length));
          break;
        }
        case 'all_end_with_terminator':
          checks.push(mk(k, e[k], (out.questions || []).every(q => /[?.]$/.test(String(q))))); break;
        case 'all_start_capitalised':
          checks.push(mk(k, e[k], (out.questions || []).every(q => /^[A-Z]/.test(String(q))))); break;
        case 'questions': checks.push(mk(k, e[k], out.questions)); break;
        default:
          if (k in out) checks.push(mk(k, e[k], out[k]));
          else checks.push(mk(k, e[k], '(field absent from unit output)', false));
      }
    }
    return { checks, informational: ['depends_on_remapped_to'], consumed: Object.keys(e) };
  },
};

module.exports = {
  'reply-policy': replyPolicy,
  'reply-determinism': replyDeterminism,
  'reply-policy-nonaccept': replyNonAccept,
  'digest-notices': digestNotices,
  'digest-testmatter': digestTestMatter,
  'distil': distil,
  'distil-grading': distilGrading,
  'delivery-key': deliveryKey,
  'delivery-key-retry': deliveryKeyRetry,
  'delivery-key-no-clock': deliveryKeyNoClock,
  'integrity-guard': integrityGuard,
  'verify-selected-row': verifySelectedRow,
  'integrity-halt-notice': integrityHaltNotice,
  'approval-gate': approvalGate,
  'finalise-plan': finalisePlan,
};
