'use strict';
/**
 * oracles.js -- independent re-implementations of the hash functions the units use.
 *
 * These exist so a scenario's expected hash can be computed WITHOUT asking the code
 * under test what it produces. An oracle that calls the unit is not an oracle, it is a
 * restatement, and _groupA-notes.md is explicit that the five delivery-key expectations
 * must be regenerated this way rather than copied from the JavaScript.
 *
 * Independence here is arithmetic, not textual: the units use the FNV-1a shift-add form
 *   h + (h<<1) + (h<<4) + (h<<7) + (h<<8) + (h<<24)
 * and these use the multiply form
 *   Math.imul(h, 0x01000193)
 * They are the same function by definition of the FNV prime, so agreement is a real
 * cross-check of the surrounding derivation (basis string, salting, padding, ordering)
 * rather than of the loop body alone.
 */

function fnv32(str, basis) {
  let h = basis >>> 0;
  const s = String(str == null ? '' : str);
  for (let i = 0; i < s.length; i++) {
    h = (h ^ s.charCodeAt(i)) >>> 0;
    h = Math.imul(h, 0x01000193) >>> 0;
  }
  return h >>> 0;
}

// The units pad with SEVEN zeros and slice(-8). Reproduced exactly, pad width included:
// a different pad width would silently change short digests.
const pad7 = h => ('0000000' + h.toString(16)).slice(-8);
const pad8 = h => ('00000000' + h.toString(16)).slice(-8);

/** Approval Gate / resolveReply single-pass form -> 8 hex. */
function fnv1aHex8(s) { return pad7(fnv32(s, 0x811c9dc5)); }

/** Approval Gate post-F-02 doubled form -> 16 hex. */
function fnv1aHex16(s) {
  const t = String(s == null ? '' : s);
  return pad7(fnv32(t, 0x811c9dc5)) + pad7(fnv32('K2|' + t + '|K2', 0x01000193));
}

/** Integrity Guard / Verify Selected Row form -> 8 hex, EIGHT-zero pad. */
function fnvGuard(s) { return pad8(fnv32(s, 0x811c9dc5)); }

const FP_FIELDS = ['action_id', 'matter_id', 'action_type', 'priority', 'depends_on_json',
  'recipient', 'channel', 'requires_approval', 'idempotency_key', 'created_at'];
const S = v => String(v === null || v === undefined ? '' : v).trim();

function rowFingerprint(row) {
  const basis = FP_FIELDS.map(f => S(row[f])).join('|');
  return 'FP-' + fnvGuard(basis) + fnvGuard(basis.split('').reverse().join('') + '|salt2');
}

function normEmail(s) {
  const raw = String(s == null ? '' : s);
  const m = raw.match(/<([^>]+)>/);
  return String(m ? m[1] : raw).trim().toLowerCase();
}

function deliveryIdentity(approval, action, draft) {
  return 'apr=' + S(approval.approval_id)
    + ' act=' + S(action.action_id)
    + ' draft=' + S(draft.draft_id)
    + ' chan=' + S(action.channel || 'NONE').toUpperCase()
    + ' to=' + normEmail(action.recipient);
}

const canon = s => String(s == null ? '' : s).replace(/\s+/g, ' ').trim();

/** Build Reply Context ingress fingerprint. */
function ingressFingerprint(e) {
  const parts = [
    'pmid=' + S(e.provider_message_id),
    'thread=' + S(e.thread_id),
    'from=' + normEmail(e.from),
    'subject=' + canon(e.subject),
    'body=' + canon(e.body),
    'ts=' + S(e.received_at)
  ].join(' ');
  return 'ING-' + fnv1aHex8(parts) + '-' + String(canon(e.body).length);
}

module.exports = {
  fnv32, fnv1aHex8, fnv1aHex16, fnvGuard,
  FP_FIELDS, rowFingerprint, normEmail, deliveryIdentity, canon, ingressFingerprint,
};
