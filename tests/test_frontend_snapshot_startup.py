"""Production startup/queue orchestration with modeled render boundaries."""
import json
from pathlib import Path
import subprocess

import pytest


APP_JS = Path(__file__).resolve().parents[1] / "backend/static/app.js"


def run_case(case):
  source = APP_JS.read_text(encoding="utf-8")
  start = source.index("async function initialSnapshot()")
  end = source.index("async function runLosCheck(", start)
  stats_start = source.index("function refreshStats()")
  stats_end = source.index("function formatOnlineWindow(", stats_start)
  functions = source[start:end] + source[stats_start:stats_end]
  script = r"""
const assert = require('node:assert/strict');
const vm = require('node:vm');
const SOURCE = __SOURCE__;
const turn = () => new Promise(setImmediate);
function deferred() {
  let resolve, reject;
  const promise = new Promise((ok, fail) => {resolve = ok; reject = fail;});
  return {promise, resolve, reject};
}
function boot() {
  const headers = deferred(), body = deferred(), timers = new Map();
  const sockets = [], trace = [], warnings = [];
  let nextId = 0;
  const context = {
    performance, console: {log() {}, warn: (...args) => warnings.push(args)},
    location: {protocol: 'https:', host: 'example.test'},
    document: {hidden: false, addEventListener() {}},
    window: {requestAnimationFrame: () => ++nextId, cancelAnimationFrame() {}},
    setTimeout: (fn, ms) => {
      const id = ++nextId; timers.set(id, {fn, ms}); return id;
    },
    clearTimeout: id => timers.delete(id),
    WebSocket: class {
      constructor() {this.readyState = 0; sockets.push(this);}
      open() {this.readyState = 1; this.onopen?.();}
      close() {this.readyState = 3; this.onclose?.();}
    },
    fetch: () => headers.promise,
    withToken: path => path, tokenHeaders: () => ({}), apiPath: path => path,
    prodMode: false, apiToken: '', deferStats: false, routeHistoryEnabled: true,
    deviceData: new Map(), markers: new Map(), trails: new Map(),
    routes: new Map(), historyCache: new Map(), heat: [],
    historyWindowSeconds: 0, serverTime: null, presence: null, banner: null,
    statsCalls: 0, statsScheduled: 0, jsonReads: 0, failUpsert: false,
    setStats() {context.statsCalls++;},
    scheduleStatsUpdate() {context.statsScheduled++;},
    setServerTimeOffset(ts) {trace.push('time'); context.serverTime = ts;},
    tryFocusLinkedDevice() {trace.push('focus');},
    seedHeat(points) {trace.push('heat'); context.heat = points;},
    clearRoutes() {trace.push('clear routes'); context.routes.clear();},
    upsertRoute(r) {
      trace.push('route'); context.routes.set(r.id, r); context.refreshStats();
    },
    upsertHistoryEdge(e) {
      trace.push('edge'); context.historyCache.set(e.id, e);
      context.refreshStats();
    },
    clearHistoryLayer() {trace.push('clear history');},
    applyMqttPresenceSummary(summary) {
      trace.push('presence'); context.presence = summary;
    },
    updateHistoryWindowLabel() {trace.push('window');},
    setUpdateBanner(banner) {trace.push('banner'); context.banner = banner;},
    removeRoutes(ids) {ids.forEach(id => context.routes.delete(id));},
    removeHistoryEdges(ids) {ids.forEach(id => context.historyCache.delete(id));},
    removeDevices(ids) {
      trace.push('remove');
      ids.forEach(id => {context.deviceData.delete(id); context.trails.delete(id);});
    },
    upsertDevice(d, trail) {
      if (context.failUpsert) throw Error('injected rendering failure');
      trace.push('device'); context.deviceData.set(d.device_id, {...d});
      context.trails.set(d.device_id, trail); context.refreshStats();
    },
  };
  vm.createContext(context);
  vm.runInContext(SOURCE, context);
  const evaluate = code => vm.runInContext(code, context);
  function connect() {evaluate('connectWS()'); sockets.at(-1).open();}
  function send(msg) {sockets.at(-1).onmessage({data: JSON.stringify(msg)});}
  function flush() {evaluate('flushQueuedWsMessages()');}
  return {context, headers, body, timers, sockets, trace, warnings,
    evaluate, connect, send, flush};
}
const old = {
  server_time: 100,
  devices: {keep: {device_id: 'keep', last_seen_ts: 100},
    removed: {device_id: 'removed', last_seen_ts: 100}},
  trails: {keep: [[1, 2, 100]]}, routes: [{id: 'old'}], heat: [[1, 2, 100]],
  history_edges: [{id: 'old edge'}], mqtt_presence: {connected_total: 1},
  history_window_seconds: 100, update: {version: 'old'},
};
const current = {
  type: 'snapshot', server_time: 200,
  devices: {keep: {device_id: 'keep', last_seen_ts: 200}},
  trails: {keep: [[1, 2, 200]]}, routes: [{id: 'current'}], heat: [[1, 2, 200]],
  history_edges: [{id: 'current edge'}], mqtt_presence: {connected_total: 2},
  history_window_seconds: 200, update: {version: 'current'},
};
async function startHttp(b) {
  b.done = b.evaluate('initialSnapshot()');
  b.headers.resolve({json: () => {b.context.jsonReads++; return b.body.promise;}});
  await turn();
  assert.equal(b.context.jsonReads, 1, 'pause inside response JSON resolution');
}
async function finishHttp(b, snapshot = old) {
  b.body.resolve(snapshot); await b.done;
}
function deltas(b) {
  b.send({type: 'device_seen', device_id: 'keep', last_seen_ts: 300});
  b.send({type: 'route', route: {id: 'delta'}});
  b.flush();
}
function checkpoint(b) {
  const c = b.context;
  return JSON.stringify({devices: [...c.deviceData], trails: [...c.trails],
    routes: [...c.routes], history: [...c.historyCache], heat: c.heat,
    clock: c.serverTime, presence: c.presence, banner: c.banner,
    window: c.historyWindowSeconds, trace: b.trace,
    stats: c.statsCalls, deferred: c.deferStats});
}
(async () => {
__CASE__
})().catch(error => {console.error(error); process.exitCode = 1;});
"""
  script = script.replace("__SOURCE__", json.dumps(functions), 1)
  script = script.replace("__CASE__", case, 1)
  result = subprocess.run(
    ["node", "-e", script], capture_output=True, text=True, timeout=15
  )
  assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("connection", ["connected", "closed", "reconnected"])
@pytest.mark.parametrize("http_server_time", [100, 400])
def test_late_http_cannot_overwrite_accepted_ws_snapshot(
  connection, http_server_time
):
  case = r"""
const b = boot();
await startHttp(b);
b.connect(); b.send(current); deltas(b);
if (CONNECTION !== 'connected') {
  b.sockets.at(-1).close();
  if (CONNECTION === 'reconnected') {
    b.connect(); b.send(current); deltas(b);
  }
}
const before = checkpoint(b);
await finishHttp(b, {...old, server_time: HTTP_SERVER_TIME});
assert.equal(checkpoint(b), before,
  'late HTTP must not mutate devices, routes, history, clock, HUD or metadata');
assert.equal(b.context.deviceData.get('keep').last_seen_ts, 300);
assert.equal(b.context.deviceData.has('removed'), false);
assert.equal(b.context.routes.has('current'), true);
assert.equal(b.context.routes.has('delta'), true);
"""
  case = case.replace("CONNECTION", json.dumps(connection))
  case = case.replace("HTTP_SERVER_TIME", str(http_server_time))
  run_case(case)


@pytest.mark.parametrize("socket_open", [False, True])
def test_http_fallback_remains_until_ws_supplies_a_snapshot(socket_open):
  case = r"""
const b = boot();
await startHttp(b);
if (SOCKET_OPEN) b.connect(); // OPEN alone does not establish synchronized state.
await finishHttp(b);
assert.equal(b.context.deviceData.get('keep').last_seen_ts, 100);
assert.equal(b.context.deviceData.has('removed'), true);
assert.equal(b.context.routes.has('old'), true);
assert.equal(b.context.historyCache.has('old edge'), true);
assert.equal(b.context.historyWindowSeconds, 100);
assert.equal(b.context.deferStats, false);
if (!SOCKET_OPEN) b.connect();
b.send(current); deltas(b);
assert.equal(b.context.deviceData.get('keep').last_seen_ts, 300);
assert.equal(b.context.deviceData.has('removed'), false);
assert.equal(b.context.routes.has('old'), false);
assert.equal(b.context.routes.has('current'), true);
assert.equal(b.context.routes.has('delta'), true);
assert.equal(b.context.historyCache.has('old edge'), false);
"""
  run_case(case.replace("SOCKET_OPEN", json.dumps(socket_open)))


@pytest.mark.parametrize("failure", ["fetch", "json"])
def test_ws_recovers_when_initial_http_fails(failure):
  case = r"""
const b = boot();
if (FAILURE === 'fetch') {
  b.done = b.evaluate('initialSnapshot()');
  b.headers.reject(Error('injected HTTP failure'));
} else {
  await startHttp(b); b.body.reject(Error('injected JSON failure'));
}
await b.done;
assert.equal(b.context.deviceData.size, 0);
assert.equal(b.context.deferStats, false);
assert.equal(b.warnings.length, 1);
b.connect(); b.send(current); deltas(b);
assert.equal(b.context.deviceData.get('keep').last_seen_ts, 300);
assert.equal(b.context.routes.has('delta'), true);
"""
  run_case(case.replace("FAILURE", json.dumps(failure)))


def test_http_fallback_batches_hud_stats_until_application_finishes():
  run_case(r"""
const b = boot();
await startHttp(b); await finishHttp(b);
assert.equal(b.context.statsCalls, 1,
  'HTTP snapshot must not scan the whole map after every device/route/edge');
assert.ok(b.context.statsScheduled > 0);
assert.equal(b.context.deferStats, false);
b.context.refreshStats();
assert.equal(b.context.statsCalls, 2, 'normal updates are not left deferred');
""")


def test_http_render_failure_does_not_leave_stats_deferred():
  run_case(r"""
const b = boot(); b.context.failUpsert = true;
await startHttp(b); await finishHttp(b);
assert.equal(b.warnings.length, 1);
assert.equal(b.context.deferStats, false);
b.context.failUpsert = false;
b.connect(); b.send(current);
assert.equal(b.context.deviceData.get('keep').last_seen_ts, 200);
assert.equal(b.context.deferStats, false);
const before = b.context.statsCalls;
b.context.refreshStats();
assert.equal(b.context.statsCalls, before + 1);
""")
