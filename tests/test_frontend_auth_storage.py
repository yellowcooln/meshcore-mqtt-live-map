"""Exercise actual frontend auth scripts without Web Storage credentials."""
import json
from pathlib import Path
import re
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]
STORAGE_CASES = [
  "available", "local-get", "session-get", "local-remove",
  "session-remove", "both-get", "both-remove", "writes-blocked",
]

STORAGE_HARNESS = r"""
const assert = require('node:assert/strict');
const vm = require('node:vm');
const input = JSON.parse(require('node:fs').readFileSync(0, 'utf8'));
const key = 'meshmap_auth_token';
const stores = {};
const writes = [];
const removals = [];
const errors = [];
const window = {location: {search: '', href: input.base + '/'}};
for (const name of ['localStorage', 'sessionStorage']) {
  const short = name === 'localStorage' ? 'local' : 'session';
  const values = new Map([[key, 'legacy-copy'], ['unrelated-setting', 'keep']]);
  stores[name] = values;
  const blockedGet = input.storage === short + '-get'
    || input.storage === 'both-get';
  const blockedRemove = input.storage === short + '-remove'
    || input.storage === 'both-remove';
  const storage = {
    getItem: item => values.get(item) ?? null,
    setItem(item, value) {
      writes.push([name, item, value]);
      if (input.storage === 'writes-blocked') throw Error('storage write denied');
      values.set(item, value);
    },
    removeItem(item) {
      removals.push([name, item]);
      if (blockedRemove) throw Error('storage removal denied');
      values.delete(item);
    },
    clear() {throw Error('must not clear unrelated browser preferences');},
  };
  Object.defineProperty(window, name, {get() {
    if (blockedGet) throw Error('storage access denied');
    return storage;
  }});
}
const consoleStub = {log() {}, warn() {}, info() {},
  error: (...args) => errors.push(args.join(' '))};
function assertCleanup() {
  for (const [name, values] of Object.entries(stores)) {
    const short = name === 'localStorage' ? 'local' : 'session';
    const blocked = input.storage.startsWith(short + '-')
      || input.storage.startsWith('both-');
    assert.equal(values.has(key), blocked,
      name + ': accessible legacy copy must be removed');
    assert.equal(values.get('unrelated-setting'), 'keep');
  }
  assert(removals.every(([, item]) => item === key));
}
"""


def _run_node(script, **payload):
  result = subprocess.run(
    ["node", "-e", STORAGE_HARNESS + script],
    input=json.dumps(payload), capture_output=True, text=True, timeout=15,
  )
  assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("base", ["", "/livemap"])
@pytest.mark.parametrize("storage", STORAGE_CASES)
@pytest.mark.parametrize("verified", [True, False])
def test_verification_keeps_cookie_redirect_without_storage_copies(
  base, storage, verified
):
  script = r"""
const listeners = {};
const timers = [];
const intervals = [];
const requests = [];
const cookies = [];
let cookie = 'preference=keep; meshmap_auth=existing-session';
let resets = 0;
let renders = 0;
const elements = new Map();
for (const selector of ['#error-message', '#success-message',
  '#turnstile-container']) {
  elements.set(selector, {textContent: '', innerHTML: '',
    classList: {add() {}, remove() {}}});
}
const document = {
  body: {dataset: {appBasePath: input.base}}, readyState: 'loading',
  querySelector: selector => selector === 'code'
    ? {textContent: 'synthetic-site-key'} : elements.get(selector),
  getElementById: () => null,
  addEventListener: (name, callback) => {listeners[name] = callback;},
};
Object.defineProperty(document, 'cookie', {
  get: () => cookie,
  set: value => {cookie = value; cookies.push(value);},
});
window.turnstile = {render() {renders++;}, reset() {resets++;}};
const context = {window, document, URLSearchParams, Date,
  console: consoleStub,
  fetch: async (url, options) => {
    requests.push({url, ...options});
    return {json: async () => input.verified
      ? {success: true, auth_token: 'synthetic-issued-bearer'}
      : {success: false, error: 'synthetic verification rejection'}};
  },
  setTimeout: (callback, delay) => {timers.push({callback, delay}); return 1;},
  setInterval: callback => {intervals.push(callback); return 1;},
  clearInterval() {},
};
for (const name of ['localStorage', 'sessionStorage']) {
  Object.defineProperty(context, name, {get: () => window[name]});
}
vm.createContext(context);
vm.runInContext(input.source, context);
(async () => {
  assert.equal(typeof listeners.DOMContentLoaded, 'function');
  listeners.DOMContentLoaded();
  assert.equal(intervals.length, 1);
  intervals.shift()();
  // Allow the real async init/render continuation to finish.
  for (let i = 0; i < 5; i++) await Promise.resolve();
  assert.equal(renders, 1, 'storage restrictions must not block widget startup');
  assert.equal(cookie, 'preference=keep; meshmap_auth=existing-session');
  vm.runInContext("TurnstileAuth.state.token = 'synthetic-widget-token'", context);
  await vm.runInContext('TurnstileAuth.submitToken()', context);
  assert.equal(requests.length, 1);
  assert.equal(requests[0].url, input.base + '/api/verify-turnstile');
  assert.equal(requests[0].method, 'POST');
  assert.deepEqual(JSON.parse(requests[0].body),
    {token: 'synthetic-widget-token'});
  if (input.verified) {
    assert.equal(cookies.length, 1, 'existing cookie behavior is preserved');
    assert(cookie.startsWith('meshmap_auth=synthetic-issued-bearer;'));
    assert(cookie.includes('path=' + (input.base ? input.base + '/' : '/')));
    assert(cookie.endsWith('SameSite=Lax'));
    const redirects = timers.filter(item => item.delay === 1500);
    assert.equal(redirects.length, 1, 'verification must still redirect');
    redirects[0].callback();
    assert.equal(window.location.href, input.base + '/map');
    assert.equal(resets, 0);
    assert.deepEqual(errors, []);
  } else {
    assert.equal(cookies.length, 0, 'failed verification must not change cookies');
    assert.equal(timers.filter(item => item.delay === 1500).length, 0);
    assert.equal(window.location.href, input.base + '/');
    assert.equal(resets, 1);
    assert.equal(vm.runInContext('TurnstileAuth.state.verifying', context), false);
    assert.equal(elements.get('#error-message').textContent,
      'synthetic verification rejection');
  }
  assert.deepEqual(writes, [], 'bearers must never be written to Web Storage');
  assertCleanup();
})().catch(error => {console.error(error); process.exitCode = 1;});
"""
  _run_node(
    script, base=base, storage=storage, verified=verified,
    source=(ROOT / "backend/static/turnstile.js").read_text(),
  )


@pytest.mark.parametrize("base", ["", "/livemap"])
@pytest.mark.parametrize("storage", STORAGE_CASES)
@pytest.mark.parametrize("enabled", [True, False])
def test_map_startup_retires_legacy_copies_without_changing_auth(
  base, storage, enabled
):
  html = (ROOT / "backend/static/index.html").read_text()
  scripts = [
    text for text in re.findall(r"<script>(.*?)</script>", html, re.S)
    if "// Check Turnstile authentication" in text
  ]
  assert len(scripts) == 1, "execute the actual unique map-auth inline script"
  script = r"""
const cookie = 'preference=keep; meshmap_auth=existing-valid-session';
let cookieWrites = 0;
const messages = [];
const document = {
  body: {dataset: {appBasePath: input.base},
    getAttribute: name => name === 'data-turnstile-enabled'
      ? String(input.enabled) : null},
  getElementById: () => null,
};
Object.defineProperty(document, 'cookie', {
  get: () => cookie, set() {cookieWrites++;},
});
const context = {window, document,
  console: {...consoleStub, log: message => messages.push(message)}};
vm.createContext(context);
// Returning verified visitors skip the landing page. Cleanup must run here,
// including when Turnstile is disabled, and must remain safe on another visit.
for (let visit = 0; visit < 2; visit++) {
  vm.runInContext(input.source, context);
  assertCleanup();
  assert.equal(document.cookie, cookie);
  assert.equal(cookieWrites, 0, 'cleanup must not replace a working session');
  assert.equal(window.__meshmapStarted, false);
  assert.equal(typeof window.__meshmapReportError, 'function');
}
const expected = input.enabled
  ? '[auth] On map page, server verified authentication'
  : '[auth] Turnstile disabled, loading map';
assert.deepEqual(messages, [expected, expected]);
assert.deepEqual(writes, []);
assert.deepEqual(errors, []);
"""
  _run_node(
    script, base=base, storage=storage, enabled=enabled, source=scripts[0],
  )
