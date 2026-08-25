'use strict';
/**
 * n8n-shim.js -- a tiny, deterministic stand-in for the n8n Code-node runtime.
 *
 * It provides just enough of the n8n globals for the extracted units in
 * harness/units/ to run in plain Node with no n8n and no network:
 *
 *   $input.all()          -> array of { json }
 *   $input.first()        -> { json }
 *   $input.last()         -> { json }
 *   $input.item           -> { json }   (first item; convenience)
 *   $('Node Name').first()-> { json }
 *   $('Node Name').all()  -> array of { json }
 *   $now                  -> Luxon-ish DateTime (frozen; NEVER the system clock)
 *   $json                 -> first item's .json (runOnceForEachItem style)
 *
 * Determinism: `now` must be supplied by the caller. There is no fallback to
 * Date.now(); omitting it throws, so a test can never accidentally depend on
 * wall-clock time.
 */

/* ------------------------------------------------------------------ items */

/** Accept either raw payloads or n8n's { json } shape; always return { json }. */
function toItem(x) {
  if (x && typeof x === 'object' && !Array.isArray(x) && Object.prototype.hasOwnProperty.call(x, 'json')) {
    const it = { json: x.json };
    if (x.binary !== undefined) it.binary = x.binary;
    // pairedItem is real n8n item metadata, not a payload field: WF4 Distil Sources uses
    // it as the ONLY provenance link from an HTTP response back to its Source Registry
    // entry. Dropping it here silently graded every fixture SOURCE_PROVENANCE_UNKNOWN.
    if (x.pairedItem !== undefined) it.pairedItem = x.pairedItem;
    return it;
  }
  return { json: x };
}

function toItems(arr) {
  if (arr === undefined || arr === null) return [];
  if (!Array.isArray(arr)) arr = [arr];
  return arr.map(toItem);
}

/* ------------------------------------------------------------- DateTime-ish */

const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December'];
const DAYS = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];

const pad = (n, w) => String(Math.abs(n)).padStart(w, '0');

/**
 * A frozen, UTC-only, Luxon-compatible-*enough* DateTime.
 *
 * The extracted units currently only call `$now.toISO()`, but toFormat() is
 * implemented over the common Luxon tokens (yyyy LL dd HH mm ss ...), which
 * covers `yyyyLLddHHmmss` and friends, so new code paths do not immediately
 * break the harness.
 */
class FakeDateTime {
  constructor(date) {
    const d = date instanceof Date ? new Date(date.getTime()) : new Date(date);
    if (Number.isNaN(d.getTime())) throw new TypeError('n8n-shim: invalid date: ' + String(date));
    this._d = d;
  }

  /* --- Luxon-ish accessors (all UTC) --- */
  get year() { return this._d.getUTCFullYear(); }
  get month() { return this._d.getUTCMonth() + 1; }
  get day() { return this._d.getUTCDate(); }
  get hour() { return this._d.getUTCHours(); }
  get minute() { return this._d.getUTCMinutes(); }
  get second() { return this._d.getUTCSeconds(); }
  get millisecond() { return this._d.getUTCMilliseconds(); }
  get weekday() { const w = this._d.getUTCDay(); return w === 0 ? 7 : w; }
  get isValid() { return true; }
  get zoneName() { return 'UTC'; }

  toISO() { return this._d.toISOString(); }
  toISODate() { return this._d.toISOString().slice(0, 10); }
  toISOTime() { return this._d.toISOString().slice(11); }
  toMillis() { return this._d.getTime(); }
  toSeconds() { return Math.floor(this._d.getTime() / 1000); }
  toJSDate() { return new Date(this._d.getTime()); }
  toJSON() { return this.toISO(); }
  toString() { return this.toISO(); }
  valueOf() { return this._d.getTime(); }

  setZone() { return this; }   // UTC only
  toUTC() { return this; }

  /**
   * Luxon-style token formatting (UTC). Supported tokens:
   *   yyyy yy | LLLL LLL LL L | MMMM MMM MM M | dd d | HH H | hh h
   *   mm m | ss s | SSS | EEEE EEE | a | ZZ Z | X x
   * Literal text can be quoted with single quotes, as in Luxon.
   */
  toFormat(fmt) {
    if (typeof fmt !== 'string') throw new TypeError('n8n-shim: toFormat expects a string');
    const t = {
      yyyy: () => pad(this.year, 4),
      yy: () => pad(this.year % 100, 2),
      LLLL: () => MONTHS[this.month - 1],
      LLL: () => MONTHS[this.month - 1].slice(0, 3),
      LL: () => pad(this.month, 2),
      L: () => String(this.month),
      MMMM: () => MONTHS[this.month - 1],
      MMM: () => MONTHS[this.month - 1].slice(0, 3),
      MM: () => pad(this.month, 2),
      M: () => String(this.month),
      dd: () => pad(this.day, 2),
      d: () => String(this.day),
      HH: () => pad(this.hour, 2),
      H: () => String(this.hour),
      hh: () => pad(this.hour % 12 || 12, 2),
      h: () => String(this.hour % 12 || 12),
      mm: () => pad(this.minute, 2),
      m: () => String(this.minute),
      ss: () => pad(this.second, 2),
      s: () => String(this.second),
      SSS: () => pad(this.millisecond, 3),
      EEEE: () => DAYS[this._d.getUTCDay()],
      EEE: () => DAYS[this._d.getUTCDay()].slice(0, 3),
      a: () => (this.hour < 12 ? 'AM' : 'PM'),
      ZZZ: () => 'UTC',
      ZZ: () => '+00:00',
      Z: () => '+0:00',
      X: () => String(this.toSeconds()),
      x: () => String(this.toMillis()),
    };
    // longest token first so `yyyy` wins over `yy`
    const tokens = Object.keys(t).sort((a, b) => b.length - a.length);
    const re = new RegExp("'([^']*)'|" + tokens.join('|'), 'g');
    return fmt.replace(re, (match, quoted) => (quoted !== undefined ? quoted : t[match]()));
  }

  _shift(obj, sign) {
    const d = new Date(this._d.getTime());
    const o = obj || {};
    const g = (a, b) => Number(o[a] || o[b] || 0) * sign;
    if (g('years', 'year')) d.setUTCFullYear(d.getUTCFullYear() + g('years', 'year'));
    if (g('months', 'month')) d.setUTCMonth(d.getUTCMonth() + g('months', 'month'));
    const ms =
      g('weeks', 'week') * 6048e5 +
      g('days', 'day') * 864e5 +
      g('hours', 'hour') * 36e5 +
      g('minutes', 'minute') * 6e4 +
      g('seconds', 'second') * 1e3 +
      g('milliseconds', 'millisecond');
    return new FakeDateTime(new Date(d.getTime() + ms));
  }

  plus(obj) { return this._shift(obj, 1); }
  minus(obj) { return this._shift(obj, -1); }

  startOf(unit) {
    const d = new Date(this._d.getTime());
    switch (unit) {
      case 'year': d.setUTCMonth(0); // falls through
      case 'month': d.setUTCDate(1); // falls through
      case 'day': d.setUTCHours(0); // falls through
      case 'hour': d.setUTCMinutes(0); // falls through
      case 'minute': d.setUTCSeconds(0); // falls through
      case 'second': d.setUTCMilliseconds(0); break;
      default: throw new RangeError('n8n-shim: startOf(' + unit + ') not supported');
    }
    return new FakeDateTime(d);
  }

  endOf(unit) { return this.startOf(unit)._shift({ [unit + 's']: 1 }, 1)._shift({ milliseconds: 1 }, -1); }

  diff(other, unit) {
    const ms = this.toMillis() - (other instanceof FakeDateTime ? other.toMillis() : new Date(other).getTime());
    const per = { milliseconds: 1, seconds: 1e3, minutes: 6e4, hours: 36e5, days: 864e5 };
    const u = unit || 'milliseconds';
    if (!per[u]) throw new RangeError('n8n-shim: diff unit ' + u + ' not supported');
    const v = ms / per[u];
    return { [u]: v, as: (x) => ms / (per[x] || 1), toMillis: () => ms, valueOf: () => ms };
  }
}

/** Build a frozen $now. `now` may be an ISO string, epoch ms, or Date. */
function makeNow(now) {
  if (now === undefined || now === null) {
    throw new Error(
      'n8n-shim: makeContext requires an explicit `now` (ISO string, epoch ms, or Date). ' +
      'The shim never reads the system clock, so unit tests stay deterministic.'
    );
  }
  if (now instanceof FakeDateTime) return now;
  return new FakeDateTime(now);
}

/* ------------------------------------------------------------------ $input */

function makeItemBag(items, label) {
  const arr = toItems(items);
  const bag = {
    all() { return arr.slice(); },
    first() {
      if (arr.length === 0) throw new Error('n8n-shim: ' + label + '.first() -- no items available');
      return arr[0];
    },
    last() {
      if (arr.length === 0) throw new Error('n8n-shim: ' + label + '.last() -- no items available');
      return arr[arr.length - 1];
    },
    isEmpty() { return arr.length === 0; },
  };
  Object.defineProperty(bag, 'item', { get: () => bag.first(), enumerable: true });
  return bag;
}

/* --------------------------------------------------------------- makeContext */

/**
 * makeContext({ items, nodeOutputs, now })
 *
 *   items       -- input items for this node. Raw objects or { json } shapes.
 *   nodeOutputs -- { 'Node Name': [ ...items ] } for `$('Node Name')`.
 *                  A single object is accepted and treated as a one-item array.
 *   now         -- REQUIRED. ISO string / epoch ms / Date. Backs $now.
 *   helpers     -- optional stubs for `this.helpers.*` (e.g. getBinaryDataBuffer).
 *   json        -- optional explicit $json override.
 *
 * Returns the context object passed to a unit's run(); it is also bound as `this`.
 */
function makeContext(opts) {
  const o = opts || {};
  const $now = makeNow(o.now);
  const $input = makeItemBag(o.items, '$input');

  const outputs = o.nodeOutputs || {};
  const $ = function (nodeName) {
    if (!Object.prototype.hasOwnProperty.call(outputs, nodeName)) {
      throw new Error(
        "n8n-shim: $('" + nodeName + "') -- no output registered for that node. " +
        'Add it to makeContext({ nodeOutputs: { "' + nodeName + '": [ ... ] } }). ' +
        'Known nodes: ' + (Object.keys(outputs).join(', ') || '(none)')
      );
    }
    return makeItemBag(outputs[nodeName], "$('" + nodeName + "')");
  };

  const ctx = {
    $input,
    $,
    $now,
    $items: (nodeName) => $(nodeName).all(),
    // `this` inside a unit is bound to this context object, so node code that
    // calls `this.helpers.getBinaryDataBuffer(...)` reaches whatever the test
    // supplies here. Unstubbed helpers throw a clear message rather than
    // silently returning undefined.
    helpers: o.helpers || new Proxy({}, {
      get(_t, name) {
        return () => {
          throw new Error(
            'n8n-shim: this.helpers.' + String(name) + '() is not stubbed. ' +
            'Pass makeContext({ helpers: { ' + String(name) + ': ... } }) from your test.'
          );
        };
      },
    }),
  };
  // $json mirrors n8n's runOnceForEachItem global: the current item's payload.
  Object.defineProperty(ctx, '$json', {
    enumerable: true,
    get: () => (o.json !== undefined ? o.json : ($input.isEmpty() ? undefined : $input.first().json)),
  });
  return ctx;
}

module.exports = { makeContext, makeNow, FakeDateTime, toItem, toItems };
