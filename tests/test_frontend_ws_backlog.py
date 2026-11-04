"""Realtime messages must not pile up while the tab is hidden."""

import json
import subprocess
from pathlib import Path


APP_JS = Path(__file__).resolve().parents[1] / "backend/static/app.js"


def _ws_section(source):
  # Queue, visibility handling and connectWS, through the snapshot handler.
  start = source.index("const pendingWsMessages = [];")
  end = source.index("async function runLosCheck(options")
  return source[start:end]


def test_hidden_tab_flushes_pauses_and_catches_up():
  section = _ws_section(APP_JS.read_text(encoding="utf-8"))
  script = r"""
const assert = require('node:assert/strict');
const sockets = [], handled = [], removed = [];
let visListener = null, historyCleared = 0, pauseFn = null;
class WebSocket {
  constructor(url) { this.url = url; this.closed = false; sockets.push(this); }
  close() { this.closed = true; setImmediate(() => this.onclose && this.onclose()); }
}
const realSetTimeout = setTimeout;
const location = {protocol: 'https:', host: 'example.test'};
const prodMode = false, apiToken = '', apiPath = (p) => p;
// A hidden tab never runs animation frames.
const window = {requestAnimationFrame() {}};
const document = {
  hidden: false,
  addEventListener(type, fn) { if (type === 'visibilitychange') visListener = fn; }
};
let deferStats = false;
const deviceData = new Map([['old', {}], ['keep', {}]]);
const historyCache = new Map([['edge', {}]]);
const routeHistoryEnabled = true;
function scheduleStatsUpdate() {}
function setStats() {}
function setServerTimeOffset() {}
function tryFocusLinkedDevice() {}
function upsertDevice(d) { deviceData.set(d.device_id, d); }
function removeDevices(ids) { removed.push(...ids); ids.forEach((id) => deviceData.delete(id)); }
function clearRoutes() {}
function seedHeat() {}
function upsertRoute() {}
function upsertHistoryEdge() {}
function clearHistoryLayer() { historyCleared += 1; }
function applyMqttPresenceSummary() {}
function updateHistoryWindowLabel() {}
function setUpdateBanner() {}
""" + section.replace(
    "function handleRealtimeMessage(msg) {",
    "function handleRealtimeMessage(msg) { handled.push(msg); return;",
  ) + r"""
const sleep = (ms) => new Promise((r) => realSetTimeout(r, ms));
const send = (socket, msg) => socket.onmessage({data: JSON.stringify(msg)});
(async () => {
  connectWS();
  assert.equal(sockets.length, 1);
  for (let i = 0; i < 50; i += 1) send(sockets[0], {type: 'route', i});
  assert.equal(pendingWsMessages.length, 50);
  await sleep(WS_FLUSH_FALLBACK_MS + 100);
  assert.equal(pendingWsMessages.length, 0, 'fallback timer flushes without rAF');
  assert.equal(handled.length, 50);

  connectWS();
  assert.equal(sockets.length, 1, 'no second socket while connected');

  // Brief hide: the pending pause is cancelled.
  globalThis.setTimeout = (fn, ms) => (ms === WS_HIDDEN_DISCONNECT_MS
    ? (pauseFn = fn, 1) : realSetTimeout(fn, ms));
  document.hidden = true;
  visListener();
  assert.ok(pauseFn);
  document.hidden = false;
  visListener();
  assert.equal(sockets[0].closed, false);

  // Long hide: socket closes, queue is dropped, no auto-reconnect.
  document.hidden = true;
  wsHiddenTimer = null;
  visListener();
  send(sockets[0], {type: 'route'});
  pauseFn();
  assert.ok(sockets[0].closed);
  assert.equal(pendingWsMessages.length, 0);
  send(sockets[0], {type: 'route'});
  assert.equal(pendingWsMessages.length, 0, 'closed socket is ignored');
  await sleep(1700);
  assert.equal(sockets.length, 1, 'no reconnect while hidden');

  // Shown again: reconnect, and the snapshot drops what expired meanwhile.
  document.hidden = false;
  visListener();
  assert.equal(sockets.length, 2);
  send(sockets[1], {
    type: 'snapshot',
    devices: {keep: {device_id: 'keep'}, fresh: {device_id: 'fresh'}},
    history_edges: [],
  });
  assert.deepEqual(removed, ['old']);
  assert.deepEqual([...deviceData.keys()].sort(), ['fresh', 'keep']);
  assert.equal(historyCleared, 1);
  assert.equal(historyCache.size, 0);

  // An unexpected drop while visible still retries.
  sockets[1].close();
  await sleep(1700);
  assert.equal(sockets.length, 3);
  process.exit(0);
})().catch((e) => { console.error(e); process.exit(1); });
"""
  result = subprocess.run(
    ["node", "-e", script], capture_output=True, text=True, timeout=30
  )
  assert result.returncode == 0, result.stderr


def test_initially_hidden_tab_pauses_and_recovers():
  section = _ws_section(APP_JS.read_text(encoding="utf-8"))
  script = r"""
const assert = require('node:assert/strict');
const vm = require('node:vm');
function boot(hidden) {
  let now = 0, nextId = 0;
  const timers = new Map(), sockets = [], listeners = {};
  const context = {
    console: {log() {}},
    WebSocket: class {
      constructor() { this.closed = false; sockets.push(this); }
      close() { this.closed = true; this.onclose?.(); }
    },
    location: {protocol: 'https:', host: 'example.test'},
    prodMode: false, apiToken: '', apiPath: p => p,
    window: {requestAnimationFrame() {}},
    performance: {now: () => now},
    document: {hidden, addEventListener: (type, fn) => {listeners[type] = fn;}},
    setTimeout: (fn, ms) => {
      const id = ++nextId;
      timers.set(id, {fn, at: now + ms});
      return id;
    },
    clearTimeout: id => timers.delete(id),
    deviceData: new Map([['old', {device_id: 'old'}]]),
    historyCache: new Map(), routeHistoryEnabled: true, deferStats: false,
    scheduleStatsUpdate() {}, setStats() {}, setServerTimeOffset() {},
    tryFocusLinkedDevice() {}, clearRoutes() {}, seedHeat() {}, upsertRoute() {},
    upsertHistoryEdge() {}, clearHistoryLayer() {}, applyMqttPresenceSummary() {},
    updateHistoryWindowLabel() {}, setUpdateBanner() {},
    upsertDevice: d => {now++; context.deviceData.set(d.device_id, d);},
    removeDevices: ids => ids.forEach(id => context.deviceData.delete(id)),
  };
  vm.createContext(context);
  vm.runInContext(SECTION, context);
  vm.runInContext('connectWS()', context);
  function advance(ms) {
    const target = now + ms;
    while (true) {
      const due = [...timers].filter(([, t]) => t.at <= target)
        .sort((a, b) => a[1].at - b[1].at || a[0] - b[0]);
      if (!due.length) break;
      const [id, timer] = due[0];
      timers.delete(id);
      now = timer.at;
      timer.fn();
    }
    now = target;
  }
  function visibility(hidden) {
    context.document.hidden = hidden;
    listeners.visibilitychange();
  }
  return {context, sockets, timers, advance, visibility,
    evaluate: source => vm.runInContext(source, context)};
}
// No visibilitychange event: initial hidden state alone must arm the timer.
const hidden = boot(true);
hidden.advance(59999);
assert.equal(hidden.sockets[0].closed, false, 'keep the 60-second grace period');
hidden.advance(1);
assert.equal(hidden.sockets[0].closed, true, 'initially hidden socket must pause');
hidden.advance(120000);
assert.equal(hidden.sockets.length, 1, 'no automatic reconnect while paused');
hidden.visibility(false);
assert.equal(hidden.sockets.length, 2, 'showing a paused tab reconnects');
hidden.visibility(false);
assert.equal(hidden.sockets.length, 2, 'repeated show does not duplicate sockets');
hidden.sockets[1].onmessage({data: JSON.stringify({
  type: 'snapshot', devices: {fresh: {device_id: 'fresh'}}, history_edges: []
})});
assert.deepEqual([...hidden.context.deviceData.keys()], ['fresh']);
// Late delivery from the retired socket cannot reintroduce an expired node.
hidden.sockets[0].onmessage({data: JSON.stringify({
  type: 'update', device: {device_id: 'old'}
})});
hidden.advance(2000);
assert.equal(hidden.context.deviceData.has('old'), false);

// Showing an initially hidden tab before the deadline cancels the pause.
const brief = boot(true);
brief.advance(30000);
brief.visibility(false);
brief.advance(61000);
assert.equal(brief.sockets[0].closed, false);
assert.equal(brief.sockets.length, 1);

// Repeated hidden notifications must not postpone the original deadline.
const repeated = boot(true);
repeated.advance(30000);
repeated.visibility(true);
repeated.advance(30000);
assert.equal(repeated.sockets[0].closed, true);

const visible = boot(false);
visible.advance(120000);
assert.equal(visible.sockets[0].closed, false, 'initially visible stays connected');
assert.equal(visible.sockets.length, 1);

// A partially drained old connection must not replay over the next snapshot.
const reconnect = boot(false);
for (let i = 0; i < 100; i++) {
  reconnect.sockets[0].onmessage({data: JSON.stringify({
    type: 'update', device: {device_id: 'retired-' + i}
  })});
}
reconnect.evaluate('flushQueuedWsMessages()');
assert.ok(reconnect.evaluate('pendingWsMessages.length > wsQueueHead'));
reconnect.sockets[0].close();
reconnect.advance(1500);
assert.equal(reconnect.sockets.length, 2);
reconnect.sockets[1].onmessage({data: JSON.stringify({
  type: 'snapshot', devices: {fresh: {device_id: 'fresh'}}, history_edges: []
})});
reconnect.advance(30000);
assert.deepEqual([...reconnect.context.deviceData.keys()], ['fresh'],
  'queued messages from the old connection must not revive expired nodes');

const replacement = boot(false);
for (let i = 0; i < 100; i++) {
  replacement.sockets[0].onmessage({data: JSON.stringify({
    type: 'update', device: {device_id: 'old-' + i}
  })});
}
replacement.evaluate('flushQueuedWsMessages()');
replacement.sockets[0].onmessage({data: JSON.stringify({
  type: 'snapshot', devices: {fresh: {device_id: 'fresh'}}, history_edges: []
})});
replacement.sockets[0].onmessage({data: JSON.stringify({
  type: 'update', device: {device_id: 'after-snapshot'}
})});
replacement.advance(30000);
assert.deepEqual([...replacement.context.deviceData.keys()],
  ['fresh', 'after-snapshot'], 'snapshot clears old work, not subsequent events');
"""
  script = script.replace("SECTION", json.dumps(section), 1)
  result = subprocess.run(
    ["node", "-e", script], capture_output=True, text=True, timeout=10
  )
  assert result.returncode == 0, result.stderr
