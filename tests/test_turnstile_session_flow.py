"""Characterize browser auth through real HTTP/WebSocket route dispatch.

Each case imports the app in a fresh process with synthetic configuration.
TestClient is deliberately NOT entered: its context manager would start MQTT
and persistence tasks. Only Cloudflare's HTTP transport is replaced. Cookie-
only reconnection models absent browser storage; browser JS runs elsewhere.
"""
from functools import partial
from http.cookies import SimpleCookie
from pathlib import Path
import os
import subprocess
import sys
import time
from urllib.parse import parse_qs

import httpx
import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect


BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
PROD_TOKEN = "session-flow-api-token"
SITE_KEY = "session-flow-site-key"
SECRET_KEY = "session-flow-secret-key"
VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"


class _SessionFlow:
  def __init__(self, module):
    self.module = module
    self.verifier = module.turnstile_verifier
    self.requests = []
    self.client = TestClient(module.app, follow_redirects=False)

  def path(self, path):
    return self.module.APP_BASE_PATH + path

  def siteverify(self, request):
    assert request.method == "POST"
    assert str(request.url) == VERIFY_URL
    form = parse_qs(request.content.decode("ascii"))
    assert form["secret"] == [SECRET_KEY]
    assert set(form) == {"secret", "response"}
    challenge = form["response"][0]
    self.requests.append(challenge)
    if challenge == "transport-error":
      raise httpx.ConnectError("synthetic transport failure", request=request)
    return httpx.Response(200, json={
      "success": challenge == "accepted-challenge",
      "error-codes": ["invalid-input-response"],
    })

  def issue(self):
    before = time.time()
    count = len(self.requests)
    response = self.client.post(
      self.path("/api/verify-turnstile"),
      json={"token": "accepted-challenge"},
    )
    after = time.time()
    assert response.status_code == 200, response.text
    assert self.requests[count:] == ["accepted-challenge"]
    payload = response.json()
    assert payload["success"] is True
    token = payload["auth_token"]
    assert isinstance(token, str) and token
    assert token not in (PROD_TOKEN, "accepted-challenge")
    issued = self.verifier.issued_tokens[token]
    assert issued.token == token
    assert before <= issued.created_at <= after
    ttl = self.module.TURNSTILE_TOKEN_TTL_SECONDS
    assert issued.expires_at - issued.created_at == ttl
    cookie = SimpleCookie(response.headers["set-cookie"])["meshmap_auth"]
    assert cookie.value == token
    assert cookie["path"] == (self.module.APP_BASE_PATH or "/")
    assert cookie["max-age"] == str(ttl)
    assert cookie["samesite"].lower() == "lax"
    assert self.client.cookies.get("meshmap_auth") == token
    return token

  def reject_ws(self, suffix="", headers=None):
    with pytest.raises(WebSocketDisconnect) as error:
      with self.client.websocket_connect(
        self.path("/ws") + suffix, headers=headers or {}
      ) as websocket:
        websocket.receive_json()
    assert error.value.code == 1008
    assert not self.module.clients

  def snapshot(self):
    # No ?auth=, ?token= or Authorization: the jar supplies the cookie.
    with self.client.websocket_connect(self.path("/ws")) as websocket:
      snapshot = websocket.receive_json()
      assert snapshot["type"] == "snapshot"
      assert snapshot["devices"] == {}
      for field in ("trails", "routes", "history_edges", "heat"):
        assert field in snapshot
      assert isinstance(snapshot["server_time"], (int, float))
    assert not self.module.clients


def _unauthenticated(flow):
  landing = flow.client.get(flow.path("/"))
  assert landing.status_code == 200
  assert 'id="turnstile-container"' in landing.text
  assert SITE_KEY in landing.text
  assert f'data-app-base-path="{flow.module.APP_BASE_PATH}"' in landing.text
  assert flow.path("/static/turnstile.js") in landing.text
  assert 'id="map"' not in landing.text
  denied = flow.client.get(flow.path("/map"))
  assert denied.status_code == 303
  assert f"window.location.href = '{flow.path('/')}';" in denied.text
  flow.reject_ws()
  flow.reject_ws(headers={"cookie": "meshmap_auth=unissued-token"})
  flow.reject_ws("?auth=unissued-token")
  flow.reject_ws(headers={"authorization": "Bearer unissued-token"})
  flow.reject_ws("?token=wrong-api-token")
  assert flow.verifier.issued_tokens == {}
  assert flow.requests == []


def _verification_failure(flow):
  for kwargs in (
    {"content": "{"},
    {"json": {"token": " "}},
    {"json": {"token": "rejected-challenge"}},
    {"json": {"token": "transport-error"}},
  ):
    response = flow.client.post(flow.path("/api/verify-turnstile"), **kwargs)
    assert response.status_code == 400, response.text
    payload = response.json()
    assert payload["success"] is False
    assert payload.get("error")
    assert "auth_token" not in payload
    assert "set-cookie" not in response.headers
    assert flow.client.cookies.get("meshmap_auth") is None
    assert flow.verifier.issued_tokens == {}
    flow.reject_ws()
  assert flow.requests == ["rejected-challenge", "transport-error"]


def _cookie_session(flow):
  flow.issue()
  # Retain no JSON token copy or storage-derived header/query credential.
  # Deleting local/session storage must not revoke the server-side session.
  for path in ("/", "/map"):
    response = flow.client.get(flow.path(path))
    assert response.status_code == 200, response.text
    assert 'id="map"' in response.text
    assert 'id="turnstile-container"' not in response.text
    assert 'data-turnstile-enabled="true"' in response.text
    assert f'data-app-base-path="{flow.module.APP_BASE_PATH}"' in response.text
  flow.snapshot()
  flow.snapshot()  # Reconnect without reconstructing any client token cache.
  token = flow.client.cookies.get("meshmap_auth")
  assert flow.verifier.verify_auth_token(token) is True
  assert list(flow.verifier.issued_tokens) == [token]
  flow.client.cookies.clear()
  flow.reject_ws()


def _expired_session(flow):
  token = flow.issue()
  assert flow.verifier.verify_auth_token(token) is True
  expires_at = flow.verifier.issued_tokens[token].expires_at
  # Use a real one-second configured TTL, not a stubbed verifier or clock.
  time.sleep(max(0, expires_at - time.time()) + 0.05)
  flow.client.cookies.clear()
  # Explicitly transmit the expired token; cookie-jar expiry alone is not
  # evidence that the server rejected it.
  headers = {"cookie": f"meshmap_auth={token}"}
  flow.reject_ws(headers=headers)
  assert token not in flow.verifier.issued_tokens
  flow.reject_ws("?auth=" + token)
  denied = flow.client.get(flow.path("/map"), headers=headers)
  assert denied.status_code == 303
  landing = flow.client.get(flow.path("/"), headers=headers)
  assert 'id="turnstile-container"' in landing.text


def _separate_api_token(flow):
  token = flow.issue()
  for path in ("/snapshot", "/api/nodes"):
    url = flow.path(path)
    # A valid browser cookie or token must not authorize protected APIs.
    for kwargs in (
      {},
      {"params": {"token": token}},
      {"headers": {"authorization": "Bearer " + token}},
    ):
      response = flow.client.get(url, **kwargs)
      assert response.status_code == 401
      assert response.json()["detail"] == "unauthorized"
  flow.client.cookies.clear()
  for path, field in (("/snapshot", "devices"), ("/api/nodes", "data")):
    url = flow.path(path)
    assert flow.client.get(url).status_code == 401
    for kwargs in (
      {"params": {"token": PROD_TOKEN}},
      {"params": {"access_token": PROD_TOKEN}},
      {"headers": {"authorization": "Bearer " + PROD_TOKEN}},
      {"headers": {"x-token": PROD_TOKEN}},
    ):
      response = flow.client.get(url, **kwargs)
      assert response.status_code == 200, response.text
      assert field in response.json()
  assert flow.verifier.verify_auth_token(token) is True


CASES = {
  "unauthenticated": _unauthenticated,
  "verification_failure": _verification_failure,
  "cookie_session": _cookie_session,
  "expired_session": _expired_session,
  "separate_api_token": _separate_api_token,
}


@pytest.mark.parametrize("base_path", ("", "/livemap"), ids=("root", "mounted"))
@pytest.mark.parametrize("case", CASES)
def test_turnstile_session_dispatch(case, base_path, tmp_path):
  # Do not inherit operator auth, data paths, proxies, or optional services.
  env = {
    key: value for key, value in os.environ.items()
    if key in ("PATH", "LANG", "LC_ALL", "LD_LIBRARY_PATH", "SYSTEMROOT")
  }
  env.update({
    "APP_BASE_PATH": base_path,
    "PROD_MODE": "true",
    "PROD_TOKEN": PROD_TOKEN,
    "TURNSTILE_ENABLED": "true",
    "TURNSTILE_SITE_KEY": SITE_KEY,
    "TURNSTILE_SECRET_KEY": SECRET_KEY,
    "TURNSTILE_API_URL": VERIFY_URL,
    "TURNSTILE_TOKEN_TTL_SECONDS": "1" if case == "expired_session" else "321",
    "TURNSTILE_BOT_BYPASS": "false",
    "STATE_DIR": str(tmp_path),
    "BACKUP_DIR": str(tmp_path / "backup"),
    "GIT_CHECK_ENABLED": "false",
    "MQTT_HOST": "127.0.0.1",
    "TMPDIR": str(tmp_path),
    "PYTHONDONTWRITEBYTECODE": "1",
  })
  result = subprocess.run(
    [sys.executable, str(Path(__file__).resolve()), case],
    cwd=BACKEND_DIR, env=env, capture_output=True, text=True, timeout=30,
  )
  assert result.returncode == 0, result.stdout + result.stderr
  assert not list(tmp_path.iterdir()), "Dispatch must not write state files"


def _run_case(case):
  sys.path.insert(0, str(BACKEND_DIR))
  import app
  import decoder
  import turnstile

  assert app.APP_BASE_PATH == os.environ["APP_BASE_PATH"]
  assert app.TURNSTILE_TOKEN_TTL_SECONDS == int(
    os.environ["TURNSTILE_TOKEN_TTL_SECONDS"]
  )
  assert isinstance(app.turnstile_verifier, turnstile.TurnstileVerifier)
  flow = _SessionFlow(app)
  try:
    # Inject a MockTransport into the real HTTPX client; retain the real
    # verify_turnstile_token, issue_auth_token and verify_auth_token methods.
    client = partial(
      httpx.AsyncClient,
      transport=httpx.MockTransport(flow.siteverify), trust_env=False,
    )
    with pytest.MonkeyPatch.context() as patch:
      patch.setattr(turnstile.httpx, "AsyncClient", client)
      CASES[case](flow)
  finally:
    flow.client.close()
  assert app.mqtt_client is None
  assert app.broadcaster_task is None
  assert not app.background_tasks
  assert not app.clients
  assert decoder._node_worker_proc is None


if __name__ == "__main__":
  _run_case(sys.argv[1])
