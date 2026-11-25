#!/usr/bin/env python3
"""Bounded offline replay of application events, not MQTT or RF packets.

Use an EXISTING runtime image: --network none --cpus 1 --memory 2g. Mount
frozen source at /source:ro, this tool separately at /harness:ro, the private
fixture read-only, and evidence outside Git. No ASGI lifespan/MQTT startup.

Arrival schedule: repeating route/seen/route/device/route/name/route/seen/
route/role, with payload types 2/5/8/9/4. A separate producer thread offers
events on fixed monotonic deadlines even when the application loop stalls.
Rates describe broadcaster queue events, not MQTT messages or RF traffic.

The REAL state loader, resolver, broadcaster, history recorder, reaper,
state saver and history saver execute unchanged. HTTP and optional receiving
WebSocket use actual loopback TCP and FastAPI; no browser/rendering, broker,
raw-packet decoder, TLS, reverse proxy, WAN, or slow-client coverage. Client
and instrumentation CPU are included. Initial HTTP/WS setup is outside the
steady-state timer. Default 40k route-history segments are SYNTHETIC geometry
from eligible fixture peers; real peer buckets come from the private fixture.
Fixture timestamps shift uniformly by a whole 300-second multiple in a
DISPOSABLE copy, preserving bucket alignment and assessment ages within 5m.
No private identities are exported; temporary state is removed on exit.

Exit 0: complete replay and requested minimum work/cardinality verified.
Exit 1: incomplete/failed verification (metrics retained). Exit 2: setup error.
Use a host-side timeout as an independent hard stop for a wedged event loop.
"""
import argparse
import asyncio
import collections
import contextlib
import copy
import hashlib
import importlib
import importlib.metadata
import inspect
import json
import logging
import math
import os
from pathlib import Path
import resource
import socket
import subprocess
import sys
import tempfile
import threading
import time
from decimal import Decimal


class BenchmarkError(ValueError):
  """Only deliberately identity-free validation messages may be exported."""


MIX = ("route", "device_seen", "route", "device", "route",
       "device_name", "route", "device_seen", "route", "device_role")


def shift_fixture(data, target_now):
  """Uniform epoch shift of a detached copy; zero sentinels stay zero."""
  saved_at = float(data.get("saved_at") or 0)
  if not math.isfinite(saved_at) or saved_at <= 0:
    raise BenchmarkError("fixture requires a positive saved_at assessment time")
  delta = math.floor((target_now - saved_at) / 300) * 300
  shifted = copy.deepcopy(data)
  shifted["saved_at"] = saved_at + delta

  def moved(value):
    if isinstance(value, (int, float)) and value > 0:
      return value + delta
    return value

  for device in shifted.get("devices", {}).values():
    device["ts"] = moved(device.get("ts"))
  for field in ("seen_devices", "first_seen_devices", "last_seen_in_path",
                "last_seen_in_advert"):
    for key, value in shifted.get(field, {}).items():
      shifted[field][key] = moved(value)
  for trail in shifted.get("trails", {}).values():
    for point in trail:
      if len(point) >= 3:
        point[2] = moved(point[2])
  for pair in shifted.get("peer_history_pairs", {}).values():
    pair["last_ts"] = moved(pair.get("last_ts"))
    pair["buckets"] = {
      str(int(float(key)) + delta): value
      for key, value in pair.get("buckets", {}).items()
    }
  return shifted, delta


def fixture_counts(data, now):
  pairs = data.get("peer_history_pairs") or {}
  buckets = [
    (float(key), int(value)) for pair in pairs.values()
    for key, value in pair.get("buckets", {}).items()
  ]
  return {
    "devices": len(data.get("devices") or {}),
    "peer_pairs": len(pairs),
    "peer_buckets": len(buckets),
    "eligible_peer_buckets": sum(
      value > 0 and key + 300 >= now - 86400 for key, value in buckets
    ),
    "peer_observations": sum(value for _, value in buckets),
  }


def require_counts(counts, minimum):
  for key, floor in zip(("devices", "peer_pairs", "peer_buckets"), minimum):
    if counts.get(key, 0) < max(1, floor):
      raise BenchmarkError(f"nonempty cardinality required: {key} below {floor}")


def parser():
  result = argparse.ArgumentParser(
    description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter,
  )
  for name in ("source", "fixture", "output"):
    result.add_argument(f"--{name}", required=True)
  result.add_argument("--label", default="offline-replay")
  result.add_argument("--expect-source-sha256")
  result.add_argument("--duration-seconds", type=float, default=30)
  result.add_argument("--events-per-second", type=float, default=28,
                      help="broadcaster queue events/second, not MQTT messages")
  result.add_argument("--receivers", type=int, choices=(0, 1), default=1)
  result.add_argument("--history", choices=("on", "off"), default="on")
  for name, default in (("drain-seconds", 10),
                        ("sample-interval-seconds", 1),
                        ("http-interval-seconds", 15),
                        ("state-save-interval-seconds", 5),
                        ("compact-interval-seconds", 120),
                        ("retain-fraction", 0.9)):
    result.add_argument(f"--{name}", type=float, default=default)
  for name, default in (("min-devices", 1), ("min-peer-pairs", 1),
                        ("min-peer-buckets", 1), ("min-state-saves", 2),
                        ("min-cleanup-cycles", 2),
                        ("min-history-compactions", 0),
                        ("seed-history-segments", 40000),
                        ("history-max-segments", 40000)):
    result.add_argument(f"--{name}", type=int, default=default)
  return result


def distribution(values):
  if not values:
    return {"count": 0}
  values = sorted(values)
  return {
    "count": len(values), "mean": sum(values) / len(values),
    "p50": values[math.ceil(len(values) * 0.5) - 1],
    "p95": values[math.ceil(len(values) * 0.95) - 1],
    "p99": values[math.ceil(len(values) * 0.99) - 1], "max": values[-1],
  }


def source_manifest(source):
  files = {}
  for path in sorted((source / "backend").rglob("*")):
    if any(p in {"__pycache__", "node_modules", ".pytest_cache"}
           for p in path.parts):
      continue
    if path.is_file() and path.suffix in {
      ".py", ".js", ".css", ".html", ".txt", ".json",
    }:
      files[str(path.relative_to(source))] = hashlib.sha256(
        path.read_bytes()
      ).hexdigest()
  for name in ("VERSION.txt", "requirements-dev.txt"):
    if (source / name).is_file():
      files[name] = hashlib.sha256((source / name).read_bytes()).hexdigest()
  digest = hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()
  return digest, files


def state_counts(state):
  return {
    "devices": len(state.devices),
    "peer_pairs": len(state.peer_history_pairs),
    "peer_buckets": sum(len(p.get("buckets", {}))
                        for p in state.peer_history_pairs.values()),
    "history_segments": len(state.route_history_segments),
    "history_edges": len(state.route_history_edges),
    "active_routes": len(state.routes),
  }


def cpu_seconds():
  usage = resource.getrusage(resource.RUSAGE_SELF)
  return usage.ru_utime + usage.ru_stime


class MeasuredQueue(asyncio.Queue):
  """Observe complete event iterations, not merely dequeue/start counts."""
  def __init__(self, latencies):
    super().__init__()
    self.admitted = collections.Counter()
    self.started = collections.Counter()
    self.processed = collections.Counter()
    self.current = None
    self.latencies = latencies

  def admit(self, event):
    event["_bench_admitted"] = time.monotonic()
    self.latencies["handoff_ms"].append(
      (event["_bench_admitted"] - event["_bench_offered"]) * 1000
    )
    self.latencies["producer_lateness_ms"].append(
      max(0, event["_bench_offered"] - event["_bench_due"]) * 1000
    )
    self.admitted[event["type"]] += 1
    self.put_nowait(event)

  async def get(self):
    now = time.monotonic()
    # The broadcaster asks for the next event only after the preceding event
    # and all its awaited broadcasts/history work have finished. No join():
    # production broadcaster does not use Queue.task_done().
    if self.current is not None:
      event = self.current
      self.processed[event["type"]] += 1
      self.latencies["event_processing_ms"].append(
        (now - event["_bench_started"]) * 1000
      )
      self.latencies["event_completion_from_due_ms"].append(
        (now - event["_bench_due"]) * 1000
      )
      self.current = None
    event = await super().get()
    now = time.monotonic()
    self.current = event
    event["_bench_started"] = now
    self.started[event["type"]] += 1
    self.latencies["queue_wait_ms"].append(
      (now - event["_bench_admitted"]) * 1000
    )
    return event


def route_pool(app, state, fixture_pairs, retention_at):
  def retained(node):
    device = state.devices.get(node)
    if device is None:
      return False
    observed = max(float(device.ts or 0),
                   float(state.seen_devices.get(node) or 0),
                   float(state.last_seen_in_advert.get(node) or 0))
    expired = []
    if app.DEVICE_TTL_WINDOW_SECONDS > 0:
      expired.append(retention_at - observed > app.DEVICE_TTL_WINDOW_SECONDS)
    if app.PATH_TTL_SECONDS > 0:
      expired.append(retention_at - float(
        state.last_seen_in_path.get(node) or 0
      ) > app.PATH_TTL_SECONDS)
    return not (expired and all(expired))

  pool = []
  # Choose identical arrivals from the immutable fixture, not from each
  # source's already-pruned rolling peer dictionary. Avoid nodes whose normal
  # retention can remove them during this bounded replay, with 5m clock margin.
  for key in sorted(fixture_pairs):
    pair = fixture_pairs[key]
    a, b = pair.get("a_id"), pair.get("b_id")
    if a == b or not retained(a) or not retained(b):
      continue
    if any(len(state.node_hash_candidates.get(node[:6], [])) != 1
           for node in (a, b)):
      continue
    trusted = []
    points, hashes, ids = app._route_points_from_hashes(
      [a[:6], b[:6]], a, b, time.time(), evidence_ids=trusted,
    )
    if points and ids == [a, b] and trusted == [a, b] and hashes:
      pool.append((a, b, points))
    if len(pool) >= 1024:
      break
  if not pool:
    raise BenchmarkError("no drawable, authoritative fixture peer routes")
  return pool


def seed_history(path, pool, count, now):
  # This is a controlled synthetic route-history load, NOT recovered RF data.
  with path.open("w") as handle:
    for index in range(count):
      a, b, points = pool[index % len(pool)]
      entry = {
        "ts": now - 85800 + index * 85800 / max(1, count),
        "a": points[0], "b": points[1], "a_id": a, "b_id": b,
        "origin_id": a, "receiver_id": b, "route_mode": "path",
        "payload_type": 2, "message_hash": f"offline-seed-{index}",
        "route_byte_widths": [3], "topic": "offline/benchmark",
      }
      handle.write(json.dumps(entry) + "\n")


def event_for(index, pool, due, due_wall):
  a, b, points = pool[(index // 2) % len(pool)]
  kind = MIX[index % len(MIX)]
  event = {"type": kind, "device_id": a, "_bench_due": due}
  if kind == "route":
    event.update({
      "origin_id": a, "receiver_id": b, "ts": due_wall,
      "path_hashes": [a[:6], b[:6]], "route_mode": "path",
      "payload_type": (2, 5, 8, 9, 4)[(index // 2) % 5],
      "route_id": f"offline-route-{index}",
      "message_hash": f"offline-message-{index}", "topic": "offline/benchmark",
    })
  elif kind == "device":
    event["data"] = {
      "device_id": a, "lat": points[0][0], "lon": points[0][1],
      "ts": due_wall,
    }
  elif kind == "device_seen":
    event["last_seen_ts"] = due_wall
  return event


def instrument(app, source, work, latencies, origin, rate):
  """Thin observation wrappers; every wrapped production function executes."""
  broadcast = app._broadcast_payloads

  async def measured_broadcast(payloads):
    started = time.monotonic()
    for payload in payloads:
      kind = payload.get("type")
      work[f"payload_{kind}"] += 1
      if kind == "route":
        index = int(payload["route"]["id"].rsplit("-", 1)[1])
        due = origin[0] + (index + 0.5) / rate
        latencies["route_created_from_due_ms"].append(
          (started - due) * 1000
        )
    await broadcast(payloads)
    latencies["broadcast_call_ms"].append(
      (time.monotonic() - started) * 1000
    )

  app._broadcast_payloads = measured_broadcast
  history = sys.modules["history"]

  def peer_count(route):
    ids = route.get("point_ids") or []
    bucket = str(history._peer_history_bucket_start(route["ts"]))
    return sum(
      history.state.peer_history_pairs.get(f"{a}|{b}", {}).get(
        "buckets", {}
      ).get(bucket, 0) for a, b in zip(ids, ids[1:]) if a and b and a != b
    )

  def measure(module, name, metric, counter):
    original = getattr(module, name)

    def completed(started, before, args):
      work[counter] += 1
      latencies[metric].append((time.monotonic() - started) * 1000)
      if counter == "history_record_calls":
        work["peer_observations_recorded"] += peer_count(args[0]) - before

    if inspect.iscoroutinefunction(original):
      async def measured_async(*args, **kwargs):
        before = peer_count(args[0]) if counter == "history_record_calls" else 0
        started = time.monotonic()
        result = await original(*args, **kwargs)
        completed(started, before, args)
        return result
      measured = measured_async
    else:
      def measured_sync(*args, **kwargs):
        before = peer_count(args[0]) if counter == "history_record_calls" else 0
        started = time.monotonic()
        result = original(*args, **kwargs)
        completed(started, before, args)
        return result
      measured = measured_sync

    setattr(module, name, measured)

  # Select names actually called by the imported loops, not merely a legacy
  # synchronous compatibility helper that happens to remain in the module.
  record_name = next(name for name in (
    "_record_route_history_async", "_record_route_history",
  ) if name in app.broadcaster.__code__.co_names)
  cleanup_name = next(name for name in (
    "_prune_peer_history_background", "_prune_peer_history",
  ) if name in app.reaper.__code__.co_names)
  measure(app, "_prune_route_history", "route_history_cleanup_ms",
          "route_history_cleanup_calls")
  measure(app, cleanup_name, "peer_cleanup_reaper_ms", "cleanup_cycles")
  measure(app, record_name, "route_history_record_ms", "history_record_calls")
  measure(history, "_prune_peer_history", "peer_cleanup_sync_ms",
          "peer_cleanup_sync_calls")
  append = history._append_route_history_file

  def measured_append(entries):
    path = Path(app.ROUTE_HISTORY_FILE)
    before = path.stat().st_size if path.exists() else 0
    result = append(entries)
    if entries and path.exists() and path.stat().st_size > before:
      work["history_segments_appended"] += len(entries)
    elif entries:
      work["history_append_failures"] += 1
    return result

  setattr(history, "_append_route_history_file", measured_append)
  # Module-local os proxies (not a global stdlib monkeypatch) observe actual
  # successful atomic writes in baseline or imported persistence helpers.
  real_os = os

  class ObservedOS:
    def __getattr__(self, name):
      return getattr(real_os, name)

    def replace(self, src, dst, *args, **kwargs):
      result = real_os.replace(src, dst, *args, **kwargs)
      if real_os.fspath(dst) == app.STATE_FILE:
        work["state_saves"] += 1
      elif real_os.fspath(dst) == app.ROUTE_HISTORY_FILE:
        work["history_compactions"] += 1
      return result

  proxy = ObservedOS()
  for module in list(sys.modules.values()):
    filename = getattr(module, "__file__", None)
    if (filename and Path(filename).resolve().is_relative_to(source)
        and Path(filename).resolve() != Path(__file__).resolve()):
      if getattr(module, "os", None) is real_os:
        setattr(module, "os", proxy)
  return {
    "instrumented_history_entrypoint": record_name,
    "instrumented_peer_cleanup_entrypoint": cleanup_name,
  }


async def replay(args, app, state, pool, report, output):
  import httpx
  import uvicorn
  from websockets.asyncio.client import connect

  latencies = collections.defaultdict(list)
  work = collections.Counter()
  queue = MeasuredQueue(latencies)
  app.update_queue = queue
  origin = [0.0]
  report["workload"].update(instrument(
    app, Path(args.source), work, latencies, origin, args.events_per_second,
  ))
  expected = int(Decimal(str(args.duration_seconds)) *
                 Decimal(str(args.events_per_second)))
  offered = collections.Counter()
  stop = threading.Event()
  producer_errors = []
  sockets = socket.socket()
  sockets.bind(("127.0.0.1", 0))
  sockets.listen(128)
  port = sockets.getsockname()[1]
  server = uvicorn.Server(uvicorn.Config(
    app.app, host="127.0.0.1", port=port, loop="asyncio", http="h11",
    ws="websockets", lifespan="off", access_log=False, log_level="critical",
    ws_per_message_deflate=False, timeout_graceful_shutdown=2,
  ))
  tasks = [asyncio.create_task(server.serve(sockets=[sockets]))]
  ws = None
  producer = None
  samples = []
  minimum = None
  failures = []
  base = f"http://127.0.0.1:{port}"

  async def probe(client):
    before = time.monotonic()
    try:
      response = await client.get(base + "/snapshot")
      if response.status_code != 200:
        work["http_failures"] += 1
        return
      payload = response.json()
      if not payload.get("devices"):
        work["http_failures"] += 1
        return
      work["http_snapshots"] += 1
      work["http_bytes"] += len(response.content)
      latencies["http_snapshot_ms"].append(
        (time.monotonic() - before) * 1000
      )
    except Exception:
      work["http_failures"] += 1

  async def receiver():
    assert ws is not None
    async for message in ws:
      payload = json.loads(message)
      kind = payload.get("type")
      work[f"received_{kind}"] += 1
      if kind == "route":
        index = int(payload["route"]["id"].rsplit("-", 1)[1])
        due = origin[0] + (index + 0.5) / args.events_per_second
        latencies["route_received_from_due_ms"].append(
          (time.monotonic() - due) * 1000
        )

  def produce():
    try:
      for index in range(expected):
        due = origin[0] + (index + 0.5) / args.events_per_second
        if stop.wait(max(0, due - time.monotonic())):
          break
        event = event_for(index, pool, due,
                          wall_origin + due - origin[0])
        event["_bench_offered"] = time.monotonic()
        offered[event["type"]] += 1
        loop.call_soon_threadsafe(queue.admit, event)
    except Exception as exc:
      producer_errors.append(type(exc).__name__)

  def sample(handle, phase):
    nonlocal minimum
    now = time.monotonic()
    counts = state_counts(state)
    if minimum is None:
      minimum = counts.copy()
    else:
      minimum = {key: min(minimum[key], val) for key, val in counts.items()}
    depth = queue.qsize()
    front = getattr(queue, "_queue")[0] if depth else None
    pending = sum(offered.values()) - sum(queue.admitted.values())
    next_due = origin[0] + (sum(queue.admitted.values()) + 0.5) / (
      args.events_per_second
    )
    record = {
      "elapsed_seconds": now - origin[0], "phase": phase,
      "offered": sum(offered.values()),
      "admitted": sum(queue.admitted.values()),
      "started": sum(queue.started.values()),
      "processed": sum(queue.processed.values()),
      "queue_depth": depth, "handoff_pending": pending,
      "oldest_queued_from_due_ms": (
        max(0, now - front["_bench_due"]) * 1000 if front else 0
      ),
      "oldest_handoff_from_due_ms": (
        max(0, now - next_due) * 1000 if pending else 0
      ),
      "event_in_flight": int(queue.current is not None),
      "clients": len(app.clients), "cpu_seconds": cpu_seconds() - cpu_start,
      "max_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
      "cardinality": counts, "work": dict(work),
    }
    samples.append(record)
    handle.write(json.dumps(record, sort_keys=True) + "\n")
    handle.flush()

  async def lag_monitor():
    while True:
      due = time.monotonic() + 0.1
      await asyncio.sleep(0.1)
      latencies["event_loop_lag_ms"].append(
        max(0, time.monotonic() - due) * 1000
      )

  try:
    async with asyncio.timeout(15):
      while not server.started:
        if tasks[0].done():
          raise BenchmarkError("loopback server failed to start")
        await asyncio.sleep(0.01)
    async with httpx.AsyncClient(timeout=5, trust_env=False) as client:
      await probe(client)
      if not work["http_snapshots"]:
        raise BenchmarkError("actual loopback HTTP snapshot not received")
      if args.receivers:
        ws = await connect(
          f"ws://127.0.0.1:{port}/ws", max_size=32 * 1024 * 1024,
          max_queue=16, compression=None, ping_interval=None, open_timeout=10,
        )
        snapshot = json.loads(await asyncio.wait_for(ws.recv(), 10))
        if snapshot.get("type") != "snapshot" or not snapshot.get("devices"):
          raise BenchmarkError("actual WebSocket snapshot not received")
        work["received_snapshot"] += 1
        tasks.append(asyncio.create_task(receiver()))
      loop = asyncio.get_running_loop()
      origin[0] = time.monotonic()
      wall_origin = time.time()
      cpu_start = cpu_seconds()
      state.state_dirty = True
      tasks.extend(asyncio.create_task(coro) for coro in (
        app.broadcaster(), app.reaper(), app._state_saver(),
        app._route_history_saver(), lag_monitor(),
      ))
      producer = threading.Thread(target=produce, name="replay-arrivals")
      producer.start()
      next_http = origin[0] + args.http_interval_seconds
      with (output / "samples.jsonl").open("w") as handle:
        sample(handle, "injection")
        while time.monotonic() < origin[0] + args.duration_seconds:
          await asyncio.sleep(min(args.sample_interval_seconds, max(
            0, origin[0] + args.duration_seconds - time.monotonic(),
          )))
          if time.monotonic() >= next_http:
            await probe(client)
            next_http = time.monotonic() + args.http_interval_seconds
          sample(handle, "injection")
          for task in tasks:
            if task.done() and not task.cancelled() and task.exception():
              failures.append("background task failed: " +
                              type(task.exception()).__name__)
              stop.set()
        report["injection_end"] = samples[-1]
        drain_end = time.monotonic() + args.drain_seconds
        while time.monotonic() < drain_end:
          done = (not producer.is_alive() and
                  sum(queue.processed.values()) == expected and
                  (not ws or work["received_route"] == work["payload_route"]))
          if done:
            break
          await asyncio.sleep(0.05)
        sample(handle, "drain_end")
      elapsed = time.monotonic() - origin[0]
      cpu_used = cpu_seconds() - cpu_start
      report["runtime"] = {
        "elapsed_seconds_including_drain": elapsed,
        "process_cpu_seconds": cpu_used,
        "process_cpu_percent_one_core": 100 * cpu_used / elapsed,
        "max_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
      }
  finally:
    stop.set()
    if producer:
      producer.join(timeout=2)
    if ws:
      await ws.close()
    server.should_exit = True
    for task in tasks:
      task.cancel()
    results = await asyncio.gather(*tasks, return_exceptions=True)
    failures.extend("background task failed: " + type(result).__name__
                    for result in results
                    if isinstance(result, Exception))
    sockets.close()
    work["state_saves_steady"] = work["state_saves"]
    try:
      if hasattr(app, "_flush_state"):
        await app._flush_state()
      else:
        # Run the real baseline saver through its first write, then cancel
        # its timed wait. No replacement serializer or fake writer is used.
        final_saver = asyncio.create_task(app._state_saver())
        await asyncio.sleep(0)
        final_saver.cancel()
        await asyncio.gather(final_saver, return_exceptions=True)
    except Exception as exc:
      failures.append("final state flush failed: " + type(exc).__name__)
    work["state_saves_final"] = work["state_saves"] - work["state_saves_steady"]

  report["counts"] = {
    "expected": expected, "offered": sum(offered.values()),
    "admitted": sum(queue.admitted.values()),
    "started": sum(queue.started.values()),
    "processed": sum(queue.processed.values()),
    "offered_by_type": dict(offered),
    "processed_by_type": dict(queue.processed),
    "routes_created": work["payload_route"],
    "routes_received": work["received_route"],
    "route_history_observations_completed": work["history_record_calls"],
    "route_observations_without_live_emit": max(
      0, work["history_record_calls"] - work["payload_route"]
    ),
    "queue_remaining": queue.qsize(),
  }
  report["work"] = dict(work)
  report["latency_ms"] = {key: distribution(vals)
                           for key, vals in sorted(latencies.items())}
  report["cardinality"]["minimum_sampled"] = minimum
  report["cardinality"]["end"] = state_counts(state)
  during = [s for s in samples if s["phase"] == "injection"]
  xs = [s["elapsed_seconds"] for s in during]
  ys = [s["queue_depth"] for s in during]
  mean_x, mean_y = sum(xs) / len(xs), sum(ys) / len(ys)
  denom = sum((x - mean_x) ** 2 for x in xs)
  report["queue"] = {
    "max_depth": max(ys),
    "injection_end_depth": during[-1]["queue_depth"],
    "depth_slope_events_per_second": (
      sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys)) / denom
      if denom else 0
    ),
    "max_oldest_queued_from_due_ms": max(
      s["oldest_queued_from_due_ms"] for s in samples
    ),
    "max_handoff_pending": max(s["handoff_pending"] for s in samples),
  }
  for key in ("offered", "admitted", "processed"):
    if report["counts"][key] != expected:
      failures.append(f"{key} count does not equal expected admissions")
  if not work["payload_route"]:
    failures.append("no actual routes created")
  # Expired observations may legitimately retain peer/history evidence but
  # produce no live line. Verify their completed evidence/write boundary,
  # independently of live-emission and actual receiving-client counts.
  for key in ("history_record_calls", "peer_observations_recorded"):
    if work[key] != offered["route"]:
      failures.append(f"{key} does not equal offered route observations")
  if args.history == "on" and (
    work["history_segments_appended"] != offered["route"]
  ):
    failures.append("actual history file appends incomplete")
  if work["history_append_failures"]:
    failures.append("actual history file append failed")
  if args.receivers and work["received_route"] != work["payload_route"]:
    failures.append("actual WebSocket route receipt incomplete")
  if work["http_failures"]:
    failures.append("loopback HTTP failures")
  for key, floor in (("state_saves_steady", args.min_state_saves),
                      ("cleanup_cycles", args.min_cleanup_cycles),
                      ("history_compactions", args.min_history_compactions)):
    if work[key] < floor:
      failures.append(f"{key} below requested minimum {floor}")
  assert minimum is not None
  retained_keys = ["devices", "peer_pairs", "peer_buckets"]
  if report["cardinality"]["loaded"]["history_segments"]:
    retained_keys.append("history_segments")
  for key in retained_keys:
    if minimum[key] < report["cardinality"]["loaded"][key] * (
      args.retain_fraction
    ):
      failures.append(f"fixture cardinality aged out: {key}")
  try:
    require_counts(minimum, (args.min_devices, args.min_peer_pairs,
                             args.min_peer_buckets))
  except BenchmarkError as exc:
    failures.append(str(exc))
  failures.extend("producer thread failed: " + err for err in producer_errors)
  return failures


def run(args):
  if not (0 < args.duration_seconds <= 900 and
          0 < args.events_per_second <= 200 and
          1 <= args.duration_seconds * args.events_per_second <= 100000):
    raise BenchmarkError("require duration (0,900], rate (0,200], 1..100000 events")
  for name in ("drain_seconds", "sample_interval_seconds",
               "http_interval_seconds", "state_save_interval_seconds",
               "compact_interval_seconds"):
    value = getattr(args, name)
    if not math.isfinite(value) or not 0 < value <= 900:
      raise BenchmarkError(f"{name} must be finite in (0,900]")
  if not 0 < args.retain_fraction <= 1:
    raise BenchmarkError("retain-fraction must be in (0,1]")
  if not (0 <= args.seed_history_segments <= args.history_max_segments <= 40000):
    raise BenchmarkError("require 0 <= seed <= history limit <= 40000")
  if args.history == "off" and args.min_history_compactions:
    raise BenchmarkError("history off cannot require history compactions")
  source = Path(args.source).resolve()
  args.source = str(source)
  output = Path(args.output).resolve()
  if any((p / ".git").exists() for p in (output, *output.parents)):
    raise BenchmarkError("evidence must be outside any Git checkout")
  if output.is_relative_to(source) or source.is_relative_to(output):
    raise BenchmarkError("evidence and source trees must be separate")
  if output.exists():
    raise BenchmarkError("output directory already exists; choose a fresh run")
  if not (source / "backend" / "app.py").is_file():
    raise BenchmarkError("source must contain backend/app.py")
  output.mkdir(parents=True, mode=0o700)
  os.umask(0o077)
  fixture_path = Path(args.fixture).resolve()
  raw = fixture_path.read_bytes()
  fixture = json.loads(raw)
  original_counts = fixture_counts(fixture, float(fixture.get("saved_at", 0)))
  minimum = (args.min_devices, args.min_peer_pairs, args.min_peer_buckets)
  require_counts(original_counts, minimum)
  if not original_counts["eligible_peer_buckets"]:
    raise BenchmarkError("fixture has no eligible buckets at assessment time")
  fixture, delta = shift_fixture(fixture, time.time())
  digest, manifest = source_manifest(source)
  if args.expect_source_sha256 and args.expect_source_sha256 != digest:
    raise BenchmarkError("source manifest does not match expected sha256")
  report = {
    "status": "running", "label": args.label, "arguments": vars(args),
    "boundaries": __doc__, "cardinality": {"original": original_counts},
    "provenance": {
      "source_sha256": digest, "source_files_sha256": manifest,
      "fixture_sha256": hashlib.sha256(raw).hexdigest(),
      "fixture_saved_at": fixture["saved_at"] - delta,
      "fixture_shift_seconds": delta,
      "fixture_shifted_saved_at": fixture["saved_at"],
      "harness_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
      "python": sys.version, "command": [sys.executable, *sys.argv],
      "python_packages": {
        name: importlib.metadata.version(name)
        for name in ("fastapi", "uvicorn", "httpx", "websockets")
      },
    },
  }
  node = subprocess.run(["node", "--version"], capture_output=True,
                        text=True, timeout=5, check=True)
  report["provenance"]["node_version"] = node.stdout.strip()
  decoder_package = Path("/app/node_modules/@michaelhart/meshcore-decoder/"
                         "package.json")
  if decoder_package.is_file():
    report["provenance"]["decoder_package_version_not_exercised"] = (
      json.loads(decoder_package.read_bytes()).get("version")
    )
  # Save the exact invocation/provenance even if later setup fails.
  (output / "provenance.json").write_text(json.dumps(report, indent=2) + "\n")
  with tempfile.TemporaryDirectory(prefix="state-", dir=output) as temporary:
    directory = Path(temporary)
    (directory / "state.json").write_text(json.dumps(fixture))
    environment = {
      "STATE_DIR": str(directory), "STATE_FILE": str(directory / "state.json"),
      "ROUTE_HISTORY_FILE": str(directory / "route_history.jsonl"),
      "ROUTE_HISTORY_ENABLED": str(args.history == "on").lower(),
      "ROUTE_HISTORY_HOURS": "24",
      "ROUTE_HISTORY_MAX_SEGMENTS": str(args.history_max_segments),
      "ROUTE_HISTORY_COMPACT_INTERVAL": str(args.compact_interval_seconds),
      "STATE_SAVE_INTERVAL": str(args.state_save_interval_seconds),
      "ROUTE_HISTORY_ALLOWED_MODES": "path", "ROUTE_PAYLOAD_TYPES": "2,5,8,9,4",
      "ROUTE_HISTORY_PAYLOAD_TYPES": "2,5,8,9,4", "TRAIL_LEN": "0",
      "DEVICE_TTL_HOURS": "96", "PATH_TTL_SECONDS": "172800",
      "ROUTE_TTL_SECONDS": "120", "ROUTE_INFRA_ONLY": "false",
      "ROUTE_MAX_HOP_DISTANCE": "100", "ROUTE_NEIGHBOR_DEBUG": "false",
      "MAP_RADIUS_KM": "0", "MAP_BOUNDARY_MODE": "radius",
      "PROD_MODE": "false", "TURNSTILE_ENABLED": "false", "APP_BASE_PATH": "",
      "GIT_CHECK_ENABLED": "false", "BACKUP_ENABLED": "false",
      "COVERAGE_API_URL": "", "DECODE_WITH_NODE": "false",
      "DEBUG_PAYLOAD": "false", "BLOCKED_NAME_SYMBOL_FILTER_ENABLED": "false",
      "MQTT_ONLINE_FORCE_NAMES": "", "MQTT_HOST": "offline.invalid",
    }
    for name, filename in (("DEVICE_ROLES_FILE", "roles.json"),
                           ("DEVICE_COORDS_FILE", "coords.json"),
                           ("NEIGHBOR_OVERRIDES_FILE", "neighbors.json"),
                           ("AUTO_NEIGHBOR_OVERRIDES_FILE", "auto.json"),
                           ("CHANNEL_SECRETS_FILE", "channels.json")):
      environment[name] = str(directory / filename)
    os.environ.update(environment)
    report["environment_overrides"] = environment
    os.chdir(source / "backend")
    sys.path.insert(0, str(source / "backend"))
    logging.disable(logging.WARNING)
    with contextlib.redirect_stdout(sys.stderr):
      app = importlib.import_module("app")
      state = importlib.import_module("state")
      for name in ("app", "state", "history", "decoder", "config"):
        filename = getattr(sys.modules[name], "__file__", "") or ""
        if Path(filename).resolve().parent != source / "backend":
          raise BenchmarkError("application import escaped frozen source mount")
      app._load_state()
      pool = route_pool(
        app, state, fixture["peer_history_pairs"],
        fixture["saved_at"] + args.duration_seconds + args.drain_seconds + 600,
      )
      seeded = args.seed_history_segments if args.history == "on" else 0
      seed_history(directory / "route_history.jsonl", pool, seeded, time.time())
      app._load_route_history()
      report["cardinality"]["loaded"] = state_counts(state)
      require_counts(report["cardinality"]["loaded"], minimum)
      if len(state.route_history_segments) != seeded:
        raise BenchmarkError("actual route-history seed cardinality missing")
      report["workload"] = {
        "arrival_mix": list(MIX), "route_pool_size": len(pool),
        "route_pool_sha256": hashlib.sha256(json.dumps(pool).encode()).hexdigest(),
        "synthetic_history_segments_seeded": seeded,
        "shifted_fixture_age_seconds_at_start": time.time() - fixture["saved_at"],
      }
      report["failures"] = asyncio.run(
        replay(args, app, state, pool, report, output)
      )
    saved = json.loads((directory / "state.json").read_bytes())
    report["persistence_readback"] = fixture_counts(saved, time.time())
    require_counts(report["persistence_readback"], minimum)
    lines, live_rows, live_indices = 0, 0, set()
    with (directory / "route_history.jsonl").open() as handle:
      for line in handle:
        entry = json.loads(line)
        lines += 1
        message = str(entry.get("message_hash") or "")
        if message.startswith("offline-message-"):
          live_rows += 1
          live_indices.add(int(message.rsplit("-", 1)[1]))
    report["persistence_readback"].update({
      "history_jsonl_lines": lines,
      "history_live_observation_rows": live_rows,
      "history_unique_live_observations": len(live_indices),
    })
    expected_routes = report["counts"]["offered_by_type"].get("route", 0)
    if (args.history == "on" and expected_routes <= args.history_max_segments
        and report["counts"]["processed"] == report["counts"]["expected"]
        and (live_rows != expected_routes or len(live_indices) != expected_routes)):
      report["failures"].append("persisted route-history observations incomplete")
    if source_manifest(source) != (digest, manifest):
      report["failures"].append("source changed during measurement")
    if hashlib.sha256(fixture_path.read_bytes()).hexdigest() != (
      report["provenance"]["fixture_sha256"]
    ):
      report["failures"].append("read-only input fixture changed")
  report["status"] = "ok" if not report["failures"] else "failed"
  (output / "summary.json").write_text(json.dumps(report, indent=2) + "\n")
  print(json.dumps({key: report[key] for key in (
    "status", "counts", "runtime", "queue", "work", "failures",
  )}, sort_keys=True))
  return 0 if report["status"] == "ok" else 1


if __name__ == "__main__":
  try:
    sys.exit(run(parser().parse_args()))
  except Exception as exc:
    # Do not expose exception payloads/tracebacks that could contain node IDs.
    error = {"status": "error", "error_type": type(exc).__name__}
    if isinstance(exc, BenchmarkError):
      error["error"] = str(exc)
    print(json.dumps(error, sort_keys=True))
    sys.exit(2)
