"""Exercise the lifespan TLS block with real Paho and TLS handshakes."""
import ast
from pathlib import Path
import socket
import ssl
import subprocess
import threading

import paho.mqtt.client as mqtt
import pytest


APP_PATH = Path(__file__).resolve().parents[1] / "backend" / "app.py"


def configured_client(insecure=False, ca_cert="", enabled=True):
  # Execute the actual startup block without starting unrelated state/tasks.
  tree = ast.parse(APP_PATH.read_text())
  lifespan = next(n for n in tree.body
                  if isinstance(n, ast.AsyncFunctionDef)
                  and n.name == "_lifespan")
  tls_block = next(n for n in lifespan.body
                   if isinstance(n, ast.If)
                   and isinstance(n.test, ast.Name)
                   and n.test.id == "MQTT_TLS")
  ssl_imports = [n for n in tree.body if isinstance(n, ast.Import)
                 and any(a.name == "ssl" for a in n.names)]
  client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
  namespace = {"mqtt_client": client, "MQTT_TLS": enabled,
               "MQTT_TLS_INSECURE": insecure, "MQTT_CA_CERT": ca_cert}
  code = ast.Module(body=ssl_imports + [tls_block], type_ignores=[])
  exec(compile(code, str(APP_PATH), "exec"), namespace)
  return client


@pytest.fixture(scope="module")
def expired_cert(tmp_path_factory):
  directory = tmp_path_factory.mktemp("mqtt-expired-tls")
  key, csr, cert = [directory / name for name in
                    ("key.pem", "request.pem", "cert.pem")]
  subprocess.run([
    "openssl", "req", "-new", "-newkey", "rsa:2048", "-nodes",
    "-keyout", str(key), "-out", str(csr), "-subj", "/CN=localhost",
  ], check=True, capture_output=True)
  # Explicit historical dates work across OpenSSL releases; newer versions
  # reject negative -days values used by the old test fixture.
  (directory / "index.txt").write_text("")
  (directory / "serial").write_text("01\n")
  config = directory / "ca.cnf"
  config.write_text(
    "[ca]\ndefault_ca = test\n[test]\n"
    f"database = {directory / 'index.txt'}\n"
    f"serial = {directory / 'serial'}\n"
    f"new_certs_dir = {directory}\n"
    "default_md = sha256\npolicy = policy\n"
    "[policy]\ncommonName = supplied\n"
  )
  subprocess.run([
    "openssl", "ca", "-selfsign", "-batch", "-config", str(config),
    "-in", str(csr), "-keyfile", str(key), "-out", str(cert),
    "-startdate", "20000101000000Z", "-enddate", "20000102000000Z",
  ], check=True, capture_output=True)
  return cert, key


def handshake(client, cert, key):
  context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
  context.load_cert_chain(str(cert), str(key))
  listener = socket.socket()
  listener.bind(("127.0.0.1", 0))
  listener.listen(1)
  listener.settimeout(5)
  errors = []

  def serve():
    try:
      with listener:
        conn, _ = listener.accept()
        with conn:
          conn.settimeout(5)
          with context.wrap_socket(conn, server_side=True) as wrapped:
            wrapped.recv(1)
    except (ssl.SSLError, OSError) as exc:
      errors.append(exc)

  thread = threading.Thread(target=serve, daemon=True)
  address = listener.getsockname()
  thread.start()
  try:
    with socket.create_connection(address, timeout=5) as raw:
      with client._ssl_context.wrap_socket(
          raw, server_hostname="localhost") as wrapped:
        wrapped.sendall(b"x")
  finally:
    thread.join(timeout=6)
    assert not thread.is_alive(), "TLS test server did not finish"
  return errors


def test_insecure_tls_accepts_expired_certificate(expired_cert):
  client = configured_client(insecure=True, ca_cert=str(expired_cert[0]))
  assert handshake(client, *expired_cert) == []


def test_verified_tls_rejects_expired_trusted_certificate(expired_cert):
  client = configured_client(ca_cert=str(expired_cert[0]))
  with pytest.raises(ssl.SSLCertVerificationError) as error:
    handshake(client, *expired_cert)
  assert error.value.verify_code == 10  # X509_V_ERR_CERT_HAS_EXPIRED


def test_default_tls_requires_certificate_verification():
  client = configured_client()
  assert client._ssl_context.verify_mode == ssl.CERT_REQUIRED
  assert client._ssl_context.check_hostname is True


def test_insecure_tls_ignores_custom_ca_path(expired_cert):
  client = configured_client(insecure=True, ca_cert="/nonexistent/ca.pem")
  assert handshake(client, *expired_cert) == []


def test_tls_disabled_does_not_create_context():
  client = configured_client(insecure=True, enabled=False)
  assert client._ssl_context is None
