"""Execute production route admission and realtime handlers with a fake clock.

Only Leaflet/DOM, transport and timer boundaries are modeled. Route admission,
cache updates, expiry, removal, queue dispatch and snapshot reset are real code.
"""
import json
from pathlib import Path
import subprocess

import pytest


APP_JS = Path(__file__).resolve().parents[1] / "backend/static/app.js"


def _section(source, start, end):
  assert source.count(start) == 1, start
  assert source.count(end) == 1, end
  return source[source.index(start):source.index(end, source.index(start))]


def run_case(case):
  source = APP_JS.read_text(encoding="utf-8")
  functions = "\n".join([
    _section(source, "function setServerTimeOffset(", "const envStartLat"),
    _section(source, "function clearRouteDisplay(", "function clearHistoryLayer("),
    _section(source, "function upsertRoute(", "async function initialSnapshot("),
    _section(source, "const pendingWsMessages = [];", "async function runLosCheck("),
  ])
  script = r"""
const assert = require('node:assert/strict');
let now = 2_000_000, serverTimeOffsetMs = 0, nextTimer = 0;
const timers = new Map(), sockets = [], created = [], heat = [], hopsRemoved = [];
const routeCache = new Map(), routeLines = new Map(), markers = new Map();
const deviceData = new Map(), historyCache = new Map();
const Date = {now: () => now};
const performance = {now: () => 0};
const setTimeout = (fn, ms) => {
  const id = ++nextTimer; timers.set(id, {fn, ms, at: now + ms}); return id;
};
const clearTimeout = id => timers.delete(id);
const window = {requestAnimationFrame: () => ++nextTimer,
  cancelAnimationFrame() {}};
const document = {hidden: false, addEventListener() {}};
const location = {protocol: 'http:', host: 'example.test'};
const prodMode = true, apiToken = '', apiPath = p => p;
let deferStats = false, activeRouteDetailsId = null;
const routeDetailsPanel = null, routeHistoryEnabled = false;
const animatedLineRenderer = {}, arcadeModeEnabled = false;
const routeLayer = {
  members: new Set(), removeLayer(line) {this.members.delete(line);}
};
const L = {polyline(points, style) {
  const line = {points, style, changes: 0,
    addTo(layer) {layer.members.add(this); return this;},
    on() {return this;},
    setLatLngs(points) {this.points = points; this.changes++; return this;},
    setStyle(style) {this.style = style; return this;},
    getElement() {return null;}
  };
  created.push(line); return line;
}};
const routeStyleForDisplay = () => ({color: 'blue'});
const buildRouteLogMeta = route => ({...route});
const syncRouteEntryDisplay = () => {};
const removeArcadeMarker = () => {};
const clearAllHopMarkers = () => {};
const clearHopMarkersForRoute = id => hopsRemoved.push(id);
const stopArcadeLoop = () => {};
const hideRouteDetailsPanel = () => {activeRouteDetailsId = null;};
const showRouteDetails = () => {};
const refreshStats = () => {};
const scheduleStatsUpdate = () => {};
const setStats = () => {};
const addHeatPoints = (points, ts, type) => heat.push({points, ts, type});
const tryFocusLinkedDevice = () => {};
const seedHeat = () => {};
const applyMqttPresenceSummary = () => {};
const upsertDevice = d => deviceData.set(d.device_id, d);
const removeDevices = ids => ids.forEach(id => deviceData.delete(id));
class WebSocket {
  constructor() {sockets.push(this);}
  close() {this.onclose?.();}
}
__SOURCE__
const route = (extra = {}) => ({id: 'message:observer-a',
  points: [[34.25, -118.5], [34.5, -118.25]],
  point_ids: ['a'.repeat(64), 'b'.repeat(64)],
  hashes: ['aa', 'bb'], snr_values: [1.5, 2.5],
  payload_type: 2, route_mode: 'path', ts: 1999.125,
  expires_at: 2060.125, ...extra});
const connect = () => {connectWS(); return sockets.at(-1);};
const send = msg => {
  if (!sockets.length) connect();
  sockets.at(-1).onmessage({data: JSON.stringify(msg)});
  flushQueuedWsMessages();
};
const advance = ms => {
  const target = now + ms;
  while (true) {
    const due = [...timers].filter(([, t]) => t.at <= target)
      .sort((a, b) => a[1].at - b[1].at || a[0] - b[0]);
    if (!due.length) break;
    const [id, timer] = due[0]; timers.delete(id);
    now = timer.at; timer.fn();
  }
  now = target;
};
__CASE__
"""
  script = script.replace("__SOURCE__", functions, 1)
  script = script.replace("__CASE__", case, 1)
  result = subprocess.run(
    ["node", "-e", script], capture_output=True, text=True, timeout=15
  )
  if result.returncode:
    pytest.fail(result.stdout + result.stderr, pytrace=False)


@pytest.mark.parametrize("expiry", [1999.875, 2000])
@pytest.mark.parametrize("delivery", ["direct", "realtime", "snapshot"])
def test_expired_route_never_creates_or_caches_a_frame(expiry, delivery):
  case = r"""
const expired = route({expires_at: EXPIRY});
if (DELIVERY === 'direct') upsertRoute(expired);
if (DELIVERY === 'realtime') send({type: 'route', route: expired});
if (DELIVERY === 'snapshot') send({type: 'snapshot', routes: [expired]});
assert.equal(routeCache.size, 0, 'expired frames must not enter routeCache');
assert.equal(routeLines.size, 0, 'expired frames must not enter routeLines');
assert.equal(created.length, 0, 'expired frames must not allocate Leaflet lines');
assert.equal(timers.size, 0, 'expired frames must not schedule a display timeout');
assert.equal(heat.length, 0, 'expired frames must not create new heat work');
"""
  run_case(case.replace("EXPIRY", str(expiry)).replace(
    "DELIVERY", json.dumps(delivery)
  ))


@pytest.mark.parametrize("remaining_ms", [125, 500, 999])
def test_subsecond_route_expires_without_a_one_second_floor(remaining_ms):
  run_case(r"""
setServerTimeOffset(4000);
const r = route({ts: 3998.125, expires_at: 4000 + REMAINING / 1000});
send({type: 'route', route: r});
assert.equal(routeCache.get(r.id).ts, r.ts, 'keep original observation time');
assert.equal(routeCache.get(r.id).expires_at, r.expires_at, 'keep original expiry');
assert.equal(timers.size, 1);
assert.equal([...timers.values()][0].ms, REMAINING,
  'schedule only the actual remaining lifetime, not a 1000ms floor');
advance(REMAINING - 1);
assert.equal(routeLines.has(r.id), true, 'retain a still-valid route');
advance(1);
assert.equal(routeLines.has(r.id), false, 'remove at original server expiry');
assert.equal(routeCache.has(r.id), false);
assert.equal(routeLayer.members.size, 0);
""".replace("REMAINING", str(remaining_ms)))


def test_valid_same_id_updates_the_existing_line_without_restamping():
  run_case(r"""
const first = route();
send({type: 'route', route: first});
const line = routeLines.get(first.id).line;
const oldTimeout = routeLines.get(first.id).timeout;
const next = route({ts: 1999.875, expires_at: 2090.625,
  points: [[34.3, -118.4], [34.6, -118.2]]});
send({type: 'route', route: next});
assert.equal(created.length, 1, 'valid same-ID updates reuse their Leaflet line');
assert.equal(routeLines.get(first.id).line, line);
assert.deepEqual(line.points, next.points);
assert.equal(line.changes, 1);
assert.equal(timers.has(oldTimeout), false, 'cancel the superseded timer');
assert.equal(routeCache.get(first.id).ts, 1999.875);
assert.equal(routeCache.get(first.id).expires_at, 2090.625);
assert.equal(heat.length, 2, 'do not blanket-deduplicate accepted observations');
assert.deepEqual(heat.map(point => point.ts), [1999.125, 1999.875]);
const cache = routeCache.get(first.id);
send({type: 'route', route: route({expires_at: 1999})});
assert.equal(routeCache.get(first.id), cache,
  'an expired late frame must not overwrite an active same-ID route');
assert.equal(routeLines.get(first.id).line, line);
assert.equal(line.changes, 1);
""")


@pytest.mark.parametrize("state", ["active", "cache-only", "line-only"])
def test_obsolete_wire_removal_does_not_delete_a_newer_generation(state):
  run_case(r"""
const fresh = route({generation: 42});
send({type: 'route', route: fresh});
if (STATE === 'cache-only') clearRouteDisplay();
if (STATE === 'line-only') routeCache.delete(fresh.id);
activeRouteDetailsId = fresh.id;
const line = routeLines.get(fresh.id);
const cached = routeCache.get(fresh.id);
const timerIds = [...timers.keys()];
send({type: 'route_remove', route_ids: [fresh.id],
  route_generations: {[fresh.id]: 41}});
assert.equal(routeCache.get(fresh.id), cached,
  'old generation removal must preserve the newer cache');
assert.equal(routeLines.get(fresh.id), line,
  'old generation removal must preserve the newer active line');
assert.equal(activeRouteDetailsId, fresh.id, 'keep current route details');
assert.equal(hopsRemoved.length, 0, 'keep current route hop markers');
assert.deepEqual([...timers.keys()], timerIds, 'keep current expiry timer');
""".replace("STATE", json.dumps(state)))


@pytest.mark.parametrize("generation", [42, 43, None])
def test_equal_newer_or_legacy_removal_still_removes_the_route(generation):
  run_case(r"""
const fresh = route({generation: 42});
send({type: 'route', route: fresh});
activeRouteDetailsId = fresh.id;
const removal = {type: 'route_remove', route_ids: [fresh.id]};
if (GENERATION !== null) removal.route_generations = {[fresh.id]: GENERATION};
send(removal);
assert.equal(routeCache.size, 0);
assert.equal(routeLines.size, 0);
assert.equal(routeLayer.members.size, 0);
assert.equal(timers.size, 0);
assert.equal(activeRouteDetailsId, null);
assert.deepEqual(hopsRemoved, [fresh.id]);
""".replace("GENERATION", json.dumps(generation)))


def test_mixed_generation_removal_keeps_legacy_id_behavior():
  run_case(r"""
const first = route({generation: 42});
const other = route({id: 'message:observer-b', generation: 90});
const legacy = route({id: 'legacy:observer-c'});
[first, other, legacy].forEach(r => send({type: 'route', route: r}));
send({type: 'route_remove', route_ids: [first.id, other.id, legacy.id],
  route_generations: {[first.id]: 41, [legacy.id]: 1}});
assert.deepEqual([...routeCache.keys()], [first.id],
  'missing per-ID generation and unversioned routes keep legacy removal');
assert.deepEqual([...routeLines.keys()], [first.id]);
""")


@pytest.mark.parametrize("state", ["active", "cache-only", "line-only"])
def test_late_older_generation_cannot_overwrite_a_current_route(state):
  run_case(r"""
const fresh = route({generation: 42});
send({type: 'route', route: fresh});
if (STATE === 'cache-only') clearRouteDisplay();
if (STATE === 'line-only') routeCache.delete(fresh.id);
const cached = routeCache.get(fresh.id), entry = routeLines.get(fresh.id);
const timerIds = [...timers.keys()];
send({type: 'route', route: route({generation: 41, expires_at: 2100,
  points: [[35, -117], [36, -116]]})});
assert.equal(routeCache.get(fresh.id), cached, 'keep the latest cached generation');
assert.equal(routeLines.get(fresh.id), entry, 'keep the latest active generation');
assert.deepEqual([...timers.keys()], timerIds);
assert.equal(heat.length, 1, 'an obsolete display revision adds no new heat work');
assert.equal(created.length, 1);
""".replace("STATE", json.dumps(state)))


def test_snapshot_allows_a_lower_generation_after_process_restart():
  run_case(r"""
send({type: 'route', route: route({generation: 42})});
const reset = route({generation: 1, ts: 2000.125, expires_at: 2030.125});
send({type: 'snapshot', routes: [reset]});
assert.equal(routeCache.get(reset.id).generation, 1,
  'generation ordering is not comparable across authoritative snapshots');
assert.equal(routeLines.size, 1);
assert.equal(created.length, 2, 'snapshot clears the prior process line');
assert.equal(routeCache.get(reset.id).ts, reset.ts);
assert.equal(heat.length, 1, 'snapshot route seeding still skips heat');
""")


def test_equal_generation_updates_and_distinct_observers_are_not_deduplicated():
  run_case(r"""
const first = route({generation: 42});
const updated = route({generation: 42, ts: 1999.875});
const observer = route({id: 'message:observer-b', generation: 43});
[first, updated, observer].forEach(r => send({type: 'route', route: r}));
assert.equal(routeLines.size, 2, 'retain distinct observer-aware route IDs');
assert.equal(created.length, 2);
assert.equal(routeCache.get(first.id).ts, updated.ts);
assert.equal(routeLines.get(first.id).line.changes, 1);
assert.equal(heat.length, 3, 'no blanket message or observer deduplication');
""")
