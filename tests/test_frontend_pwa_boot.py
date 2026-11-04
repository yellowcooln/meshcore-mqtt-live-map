"""The ESM bootstrap can start app.js after the document load event."""
import json
import subprocess
from pathlib import Path

import pytest


@pytest.mark.parametrize("ready", ["loading", "complete"])
def test_service_worker_registers_even_after_document_load(ready):
  source = (Path(__file__).resolve().parents[1]
            / "backend/static/app.js").read_text()
  start = source.index("if ('serviceWorker' in navigator)")
  end = source.index("const hopsToggle", start)
  script = r"""
const assert = require('node:assert/strict');
const document = {readyState: READY};
const publicPathPrefix = '/audit';
const apiPath = path => '/audit' + path;
const calls = [], events = {};
const window = {addEventListener(name, callback) {events[name] = callback;}};
const navigator = {serviceWorker: {
  register(path, options) {calls.push({path, options});return Promise.resolve();}
}};
PRODUCTION
if (document.readyState === 'loading') {
  assert.equal(calls.length, 0); events.load();
}
assert.deepEqual(calls, [{path: '/audit/sw.js', options: {scope: '/audit/'}}]);
""".replace("READY", json.dumps(ready)).replace(
    "PRODUCTION", source[start:end])
  result = subprocess.run(["node", "-e", script],
                          capture_output=True, text=True)
  assert result.returncode == 0, result.stdout + result.stderr
