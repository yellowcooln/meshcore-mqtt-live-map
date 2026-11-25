"""Focused CLI tests for the offline, source-mounted replay tool."""
import copy
import asyncio
import collections
import json
import os
import runpy
import subprocess
import sys
import time
from pathlib import Path

import pytest


SCRIPT = Path(__file__).with_name("benchmark-large-map.py")


def test_help_names_injected_units_and_offline_boundaries():
  result = subprocess.run(
    [sys.executable, str(SCRIPT), "--help"],
    capture_output=True, text=True, check=False,
  )
  assert result.returncode == 0, result.stderr
  assert "--events-per-second" in result.stdout
  assert "--receivers {0,1}" in result.stdout
  assert "--history {on,off}" in result.stdout
  assert "not MQTT" in result.stdout


def test_fixture_shift_preserves_ages_and_never_changes_input():
  tool = runpy.run_path(str(SCRIPT))
  data = {
    "saved_at": 1000000.25,
    "devices": {"synthetic": {"ts": 999999.5}},
    "seen_devices": {"synthetic": 999990.5},
    "last_seen_in_path": {"synthetic": 0},
    "trails": {"synthetic": [[1, 2, 999980.5]]},
    "peer_history_pairs": {
      "synthetic-pair": {"a_id": "a", "b_id": "b", "last_ts": 999990,
                         "buckets": {"999900": 2, "900000": 1}},
    },
  }
  original = copy.deepcopy(data)
  shifted, delta = tool["shift_fixture"](data, 2000000.25)
  assert data == original
  assert delta % 300 == 0
  assert 0 <= 2000000.25 - shifted["saved_at"] < 300
  assert shifted["devices"]["synthetic"]["ts"] == 999999.5 + delta
  assert shifted["seen_devices"]["synthetic"] == 999990.5 + delta
  assert shifted["last_seen_in_path"]["synthetic"] == 0
  assert shifted["trails"]["synthetic"][0][2] == 999980.5 + delta
  assert shifted["peer_history_pairs"]["synthetic-pair"]["last_ts"] == (
    999990 + delta
  )
  assert tool["fixture_counts"](original, original["saved_at"]) == (
    tool["fixture_counts"](shifted, shifted["saved_at"])
  )
  assert tool["fixture_counts"](shifted, shifted["saved_at"])[
    "eligible_peer_buckets"
  ] == 1


def test_missing_or_aged_out_cardinality_is_an_error():
  tool = runpy.run_path(str(SCRIPT))
  with pytest.raises(ValueError, match="nonempty"):
    tool["require_counts"]({"devices": 0, "peer_pairs": 0,
                            "peer_buckets": 0}, (1, 1, 1))
  with pytest.raises(ValueError, match="peer_buckets"):
    tool["require_counts"]({"devices": 1660, "peer_pairs": 7236,
                            "peer_buckets": 0}, (1, 1, 1))


@pytest.mark.parametrize("history,receivers", [
  ("on", 1), ("on", 0), ("off", 1), ("off", 0),
])
def test_cli_exercises_actual_source_and_receiver(tmp_path, history, receivers):
  source = Path(os.getenv("BENCHMARK_SOURCE", "/source"))
  if not (source / "backend" / "app.py").is_file():
    pytest.skip("mount frozen application source; set BENCHMARK_SOURCE")
  now = time.time()
  ids = ["001122" + "01" * 29, "334455" + "02" * 29]
  devices = {key: {"device_id": key, "lat": 40 + i / 100,
                   "lon": -70 + i / 100, "ts": now,
                   "role": "repeater", "name": "synthetic"}
             for i, key in enumerate(ids)}
  fixture = tmp_path / "fixture.json"
  fixture.write_text(json.dumps({
    "saved_at": now, "devices": devices,
    "seen_devices": dict.fromkeys(ids, now),
    "device_roles": dict.fromkeys(ids, "repeater"),
    "device_role_sources": dict.fromkeys(ids, "explicit"),
    "peer_history_pairs": {"|".join(ids): {
      "a_id": ids[0], "b_id": ids[1], "last_ts": now,
      "buckets": {str(int(now // 300) * 300): 5},
    }},
  }))
  original_bytes = fixture.read_bytes()
  output = tmp_path / f"result-{history}-{receivers}"
  command = [
    sys.executable, str(SCRIPT), "--source", str(source),
    "--fixture", str(fixture), "--output", str(output),
    "--duration-seconds", "1", "--events-per-second", "10",
    "--history", history, "--receivers", str(receivers),
    "--sample-interval-seconds", "0.25",
    "--state-save-interval-seconds", "1", "--min-state-saves", "1",
    "--min-cleanup-cycles", "1", "--seed-history-segments", "8",
    "--history-max-segments", "8", "--compact-interval-seconds", "5",
  ]
  result = subprocess.run(command, capture_output=True, text=True, timeout=25)
  assert result.returncode == 0, result.stdout + result.stderr
  report = json.loads((output / "summary.json").read_text())
  assert report["status"] == "ok"
  assert report["counts"]["expected"] == 10
  assert report["counts"]["offered"] == 10
  assert report["counts"]["admitted"] == 10
  assert report["counts"]["processed"] == 10
  assert report["counts"]["routes_created"] == 5
  assert report["counts"]["routes_received"] == (5 if receivers else 0)
  assert report["work"]["state_saves"] >= 1
  assert report["work"]["cleanup_cycles"] >= 1
  assert report["work"]["history_record_calls"] == 5
  assert report["work"]["peer_observations_recorded"] == 5
  assert report["work"].get("history_segments_appended", 0) == (
    5 if history == "on" else 0
  )
  assert report["persistence_readback"]["history_unique_live_observations"] == (
    5 if history == "on" else 0
  )
  expected_entrypoint = (
    "_record_route_history_async"
    if "await _record_route_history_async(" in (
      source / "backend" / "app.py"
    ).read_text() else "_record_route_history"
  )
  assert report["workload"]["instrumented_history_entrypoint"] == (
    expected_entrypoint
  )
  assert report["cardinality"]["minimum_sampled"]["peer_buckets"] >= 1
  assert report["cardinality"]["end"]["history_segments"] == (
    8 if history == "on" else 0
  )
  assert len((output / "samples.jsonl").read_text().splitlines()) >= 2
  assert report["provenance"]["source_files_sha256"]["backend/app.py"]
  assert report["provenance"]["fixture_sha256"]
  assert fixture.read_bytes() == original_bytes
  assert not list(output.glob("state-*")), "disposable private state leaked"
  assert all(key not in (output / "summary.json").read_text() for key in ids)
  assert all(key not in result.stdout + result.stderr for key in ids)


@pytest.mark.parametrize("rate", ["0", "-1", "nan", "inf", "201"])
def test_cli_rejects_invalid_rates_before_import(tmp_path, rate):
  result = subprocess.run([
    sys.executable, str(SCRIPT), "--source", str(tmp_path / "absent"),
    "--fixture", str(tmp_path / "absent.json"),
    "--output", str(tmp_path / "result"), "--events-per-second", rate,
  ], capture_output=True, text=True, timeout=5)
  assert result.returncode == 2
  assert "require duration" in json.loads(result.stdout)["error"]


def test_cli_rejects_empty_fixture_before_application_import(tmp_path):
  source = Path(os.getenv("BENCHMARK_SOURCE", "/source"))
  if not (source / "backend" / "app.py").is_file():
    pytest.skip("mount frozen application source; set BENCHMARK_SOURCE")
  fixture = tmp_path / "empty.json"
  fixture.write_text(json.dumps({"saved_at": time.time()}))
  result = subprocess.run([
    sys.executable, str(SCRIPT), "--source", str(source),
    "--fixture", str(fixture), "--output", str(tmp_path / "result"),
  ], capture_output=True, text=True, timeout=5)
  assert result.returncode == 2
  assert "nonempty cardinality" in json.loads(result.stdout)["error"]
  assert "startup" not in result.stderr


def test_empty_queue_does_not_mean_an_inflight_event_finished():
  tool = runpy.run_path(str(SCRIPT))

  async def exercise():
    queue = tool["MeasuredQueue"](collections.defaultdict(list))
    now = time.monotonic()
    queue.admit({"type": "route", "_bench_due": now,
                 "_bench_offered": now})
    await queue.get()
    assert queue.empty()
    assert queue.current is not None
    assert sum(queue.processed.values()) == 0
    await asyncio.sleep(0)
    assert sum(queue.processed.values()) == 0
    # Only asking for the next event proves the actual broadcaster finished
    # the previous event's awaited history/file/broadcast work.
    next_get = asyncio.create_task(queue.get())
    await asyncio.sleep(0)
    assert queue.processed["route"] == 1
    assert queue.current is None
    next_get.cancel()
    await asyncio.gather(next_get, return_exceptions=True)

  asyncio.run(exercise())
