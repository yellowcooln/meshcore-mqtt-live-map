"""Deterministic fairness checks; modeled handler cost, not a benchmark."""
import json
from pathlib import Path
import subprocess

import pytest


APP_JS = Path(__file__).resolve().parents[1] / "backend/static/app.js"


@pytest.mark.parametrize("frames_run", [True, False])
@pytest.mark.parametrize("handler_cost", [0, 1])
def test_realtime_burst_yields_and_preserves_order(frames_run, handler_cost):
  source = APP_JS.read_text(encoding="utf-8")
  start = source.index("const pendingWsMessages = [];")
  end = source.index("// Nobody sees a hidden tab", start)
  section = source[start:end]
  script = r"""
const assert = require('node:assert/strict');
let clock = 0, nextId = 0, sentinelHandled = null, statsUpdates = 0;
const tasks = new Map(), handled = [];
function schedule(fn, ms) {
  const id = ++nextId;
  tasks.set(id, {fn, at: clock + ms});
  return id;
}
const setTimeout = schedule;
const clearTimeout = id => tasks.delete(id);
const performance = {now: () => clock};
const window = {
  requestAnimationFrame: fn => FRAMES_RUN ? schedule(fn, 16) : ++nextId,
  cancelAnimationFrame: id => tasks.delete(id),
};
let deferStats = false;
function scheduleStatsUpdate() {statsUpdates++;}
function handleRealtimeMessage(msg) {
  handled.push(msg.seq);
  clock += HANDLER_COST; // Model scheduling cost, not host CPU speed.
  if (msg.seq === 0) {
    setTimeout(() => {sentinelHandled = handled.length;}, 0);
    queueRealtimeMessage({seq: 1000}); // Appends behind existing work.
  }
}
SECTION
for (let i = 0; i < 1000; i++) queueRealtimeMessage({seq: i});
let turns = 0;
while (tasks.size) {
  assert.ok(++turns < 10000, 'queue must eventually drain without timer leaks');
  const [id, task] = [...tasks].sort((a,b) => a[1].at-b[1].at || a[0]-b[0])[0];
  tasks.delete(id);
  clock = Math.max(clock, task.at);
  task.fn();
}
assert.ok(sentinelHandled > 0 && sentinelHandled < 1000,
  'a sibling timer must run before the burst finishes, not after all events');
assert.deepEqual(handled, Array.from({length: 1001}, (_, i) => i));
assert.equal(pendingWsMessages.length, 0);
assert.equal(deferStats, false);
assert.ok(statsUpdates > 1, 'stats/render work is scheduled between slices');
assert.equal(wsFlushScheduled, false);
assert.equal(wsFlushTimer, null);
"""
  script = script.replace("FRAMES_RUN", json.dumps(frames_run), 1)
  script = script.replace("HANDLER_COST", str(handler_cost), 1)
  script = script.replace("SECTION", section, 1)
  result = subprocess.run(
    ["node", "-e", script], capture_output=True, text=True, timeout=10
  )
  assert result.returncode == 0, result.stderr
