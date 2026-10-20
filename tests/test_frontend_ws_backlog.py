"""Realtime messages must not pile up while the tab is hidden."""

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
  hidden: true,
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
