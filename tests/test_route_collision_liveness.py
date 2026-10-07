"""Real resolver/broadcaster/reaper bodies, isolated from startup and persistence."""
import ast
import asyncio
from pathlib import Path
from typing import List, Optional

import pytest

import decoder
import history
import state

OLD = '01742BDDB6B4BDE6A05C7C6259CA6840CF46317C7C6B7EF14DA072BB6189274D'
NEW = '01742A2DA42F11A33CA9E51175D87653C7867AB66399AFFE143D5E8487F7B35D'
ORIGIN = 'AA0011' + '11' * 29
RECEIVER = 'DD0011' + '22' * 29
NOW = 2_000_000.0
STALE = NOW - 345600 - 1000


@pytest.fixture
def chain(monkeypatch):
  # Replace shared containers instead of clearing application or other tests' state.
  containers = ('devices', 'seen_devices', 'last_seen_in_path', 'neighbor_edges',
                'node_hash_candidates', 'node_hash_to_device', 'peer_history_pairs',
                'route_history_edges')
  for name in containers:
    value = {}
    monkeypatch.setattr(state, name, value)
    if hasattr(decoder, name):
      monkeypatch.setattr(decoder, name, value)
  monkeypatch.setattr(state, 'node_hash_collisions', set())
  monkeypatch.setattr(decoder, 'node_hash_collisions', state.node_hash_collisions)
  monkeypatch.setattr(state, 'route_history_segments', [])
  monkeypatch.setattr(state, 'state_dirty', False)
  for name, value in [('ROUTE_ALLOW_AMBIGUOUS_ONE_BYTE_FALLBACK', False),
                      ('ROUTE_INFRA_ONLY', False), ('ROUTE_MAX_HOP_DISTANCE', 100),
                      ('ROUTE_PATH_MAX_LEN', 16), ('ROUTE_NEIGHBOR_DEBUG', False)]:
    monkeypatch.setattr(decoder, name, value)
  monkeypatch.setattr(history, 'ROUTE_HISTORY_ENABLED', False)
  monkeypatch.setattr(history, 'ROUTE_HISTORY_ALLOWED_MODES_SET', set())
  monkeypatch.setattr(history, '_peer_history_payload_allowed', lambda _: True)

  class Clock:
    @staticmethod
    def time():
      return NOW

  class OneTick:
    CancelledError = asyncio.CancelledError

    @staticmethod
    async def sleep(delay):
      # Broadcaster fairness yields are real; stop only the reaper's timer.
      if delay == 0:
        await asyncio.sleep(0)
        return
      raise asyncio.CancelledError()

  async def noop_async(*args):
    pass

  def noop(*args):
    pass

  ns = dict(List=List, Optional=Optional, state=state, time=Clock, asyncio=OneTick,
            devices=state.devices, seen_devices=state.seen_devices,
            neighbor_edges=state.neighbor_edges, trails={}, routes={}, clients=set(),
            mqtt_seen={}, last_seen_in_advert={}, first_seen_devices={},
            mqtt_presence_last_summary=None, DEVICE_TTL_WINDOW_SECONDS=345600,
            PATH_TTL_SECONDS=172800, HEAT_TTL_SECONDS=0, heat_events=[],
            message_origins={}, MESSAGE_ORIGIN_TTL_SECONDS=300,
            _refresh_mqtt_presence=noop, _broadcast_payloads=noop_async,
            _stable_dict_copy=lambda d: d.copy(),
            _rebuild_node_hash_map=decoder._rebuild_node_hash_map,
            _coords_are_zero=decoder._coords_are_zero,
            _prune_route_history=lambda: ([], []), _prune_neighbors=noop,
            _mqtt_presence_summary=lambda now: {}, _prune_peer_history=lambda now: False,
            _route_points_from_hashes=decoder._route_points_from_hashes,
            _route_points_from_device_ids=decoder._route_points_from_device_ids,
            _route_hidden_by_blocked_name=lambda route: False,
            MAP_RADIUS_KM=0, ROUTE_TTL_SECONDS=120, _append_heat_points=noop,
            _record_route_history=history._record_route_history,
            _history_edge_payload=lambda edge: edge,
            _route_payload=lambda route: route, broadcaster_stats={})
  source = Path(decoder.__file__).with_name('app.py')
  names = {'_touch_neighbor', '_record_neighbors', '_update_path_timestamps',
           'broadcaster', 'reaper'}
  bodies = [node for node in ast.parse(source.read_text()).body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name in names]
  assert {node.name for node in bodies} == names
  exec(compile(ast.Module(body=bodies, type_ignores=[]), str(source), 'exec'), ns)
  for key, lat, lon, stamp in [(OLD, 42.479255, -71.338813, STALE),
                                (NEW, 42.479259, -71.338814, NOW),
                                (ORIGIN, 42.4790, -71.3390, NOW),
                                (RECEIVER, 42.4800, -71.3380, NOW)]:
    state.devices[key] = state.DeviceState(device_id=key, lat=lat, lon=lon,
                                           ts=stamp, role='repeater')
    state.seen_devices[key] = stamp
  decoder._rebuild_node_hash_map()

  class OneEvent:
    def __init__(self, event):
      self.event = event

    async def get(self):
      if self.event is None:
        raise asyncio.CancelledError()
      event, self.event = self.event, None
      return event

  def deliver(hop, origin=ORIGIN, receiver=RECEIVER):
    ns['update_queue'] = OneEvent(dict(type='route', route_id='collision',
                                     path_hashes=hop if isinstance(hop, list) else [hop],
                                     origin_id=origin,
                                     receiver_id=receiver, ts=NOW))
    with pytest.raises(asyncio.CancelledError):
      asyncio.run(ns['broadcaster']())
    return ns['routes']['collision']

  def reap():
    with pytest.raises(asyncio.CancelledError):
      asyncio.run(ns['reaper']())

  return deliver, reap


@pytest.mark.parametrize('hop,fallback,drawn', [
  ('01', False, False), ('01', True, True),
  ('0174', False, True), ('0174', True, True), ('01742B', False, True),
])
def test_collision_widths_preserve_display_without_evidence(chain, monkeypatch, hop, fallback, drawn):
  deliver, reap = chain
  monkeypatch.setattr(decoder, 'ROUTE_ALLOW_AMBIGUOUS_ONE_BYTE_FALLBACK', fallback)
  if hop == '01742B':
    alternate = '01742B' + '33' * 29
    state.devices[alternate] = state.DeviceState(
      device_id=alternate, lat=42.479259, lon=-71.338814, ts=NOW, role='repeater')
    decoder._rebuild_node_hash_map()
  route = deliver(hop)
  assert (OLD in route['point_ids']) == drawn
  assert OLD not in state.last_seen_in_path
  assert all(OLD not in edges for edges in state.neighbor_edges.values())
  assert all(OLD not in pair for pair in state.peer_history_pairs)
  reap()
  assert OLD not in state.devices


@pytest.mark.parametrize('edge', [
  {'count': 1000, 'last_seen': NOW},
  {'count': 1000, 'last_seen': NOW, 'auto': True},
])
def test_existing_dynamic_neighbor_is_not_independent_identity_evidence(chain, edge):
  deliver, reap = chain
  state.neighbor_edges[ORIGIN] = {OLD: dict(edge)}
  route = deliver('0174')
  assert OLD in route['point_ids']
  assert OLD not in state.last_seen_in_path
  assert state.neighbor_edges[ORIGIN][OLD] == edge
  assert not state.peer_history_pairs
  reap()
  assert OLD not in state.devices


@pytest.mark.parametrize('hop', ['01', '0174', '01742B'])
def test_unique_hash_is_liveness_and_peer_evidence(chain, hop):
  deliver, reap = chain
  del state.devices[NEW]
  decoder._rebuild_node_hash_map()
  route = deliver(hop)
  assert OLD in route['point_ids']
  assert state.last_seen_in_path[OLD] == NOW
  assert state.neighbor_edges[ORIGIN][OLD]['count'] == 1
  assert state.neighbor_edges[OLD][RECEIVER]['count'] == 1
  assert state.peer_history_pairs
  reap()
  assert OLD in state.devices


def test_distinct_three_byte_hash_resolves_replacement(chain):
  deliver, reap = chain
  route = deliver('01742A')
  assert NEW in route['point_ids']
  assert OLD not in route['point_ids']
  assert state.last_seen_in_path[NEW] == NOW
  assert state.neighbor_edges[ORIGIN][NEW]['count'] == 1
  reap()
  assert OLD not in state.devices


@pytest.mark.parametrize('endpoint', ['origin', 'receiver'])
def test_full_id_endpoint_is_independently_live_despite_prefix_collision(chain, endpoint):
  deliver, reap = chain
  kwargs = {endpoint: OLD}
  route = deliver('0174', **kwargs)
  assert OLD in route['point_ids']
  assert state.last_seen_in_path[OLD] == NOW
  reap()
  assert OLD in state.devices


def test_manual_edge_after_guess_does_not_launder_trust_and_unique_recovers(chain):
  deliver, reap = chain
  second = 'BC0011' + '33' * 29
  other = 'BC0011' + '44' * 29
  unique = 'EE0011' + '55' * 29
  for key, lat in [(second, 42.4795), (other, 42.4796), (unique, 42.4798)]:
    state.devices[key] = state.DeviceState(
      device_id=key, lat=lat, lon=-71.3388, ts=NOW, role='repeater')
  state.neighbor_edges[OLD] = {second: {'manual': True, 'count': 0, 'last_seen': NOW}}
  decoder._rebuild_node_hash_map()
  evidence = []
  points, hashes, ids = decoder._route_points_from_hashes(
    ['0174', 'BC0011', 'EE'], ORIGIN, RECEIVER, NOW, evidence_ids=evidence)
  assert points and hashes == ['0174', 'BC0011', 'EE']
  assert ids == [ORIGIN, OLD, second, unique, RECEIVER]
  assert evidence == [ORIGIN, None, None, unique, RECEIVER]
  route = deliver(['0174', 'BC0011', 'EE'])
  assert route['point_ids'] == ids
  assert OLD not in state.last_seen_in_path
  assert second not in state.last_seen_in_path
  assert state.last_seen_in_path[unique] == NOW
  assert state.neighbor_edges[OLD][second]['count'] == 0
  assert state.neighbor_edges[unique][RECEIVER]['count'] == 1
  assert all(OLD not in pair and second not in pair for pair in state.peer_history_pairs)
  reap()
  assert OLD not in state.devices


def test_history_keeps_guessed_geometry_without_persisting_guessed_peer_ids(chain, monkeypatch):
  deliver, _ = chain
  monkeypatch.setattr(history, 'ROUTE_HISTORY_ENABLED', True)
  monkeypatch.setattr(history, '_history_payload_allowed', lambda _: True)
  monkeypatch.setattr(history, '_append_route_history_file', lambda _: None)
  route = deliver('0174')
  assert OLD in route['point_ids']
  assert len(state.route_history_segments) == 2
  assert [(segment['a_id'], segment['b_id']) for segment in state.route_history_segments] == [
    (ORIGIN, None), (None, RECEIVER)]
  assert not state.peer_history_pairs
  history._rebuild_peer_history_from_segments()
  assert not state.peer_history_pairs


def test_time_based_guess_without_origin_is_not_authoritative(chain):
  deliver, _ = chain
  route = deliver('0174', origin=None)
  assert NEW in route['point_ids']  # temporal fallback selects recent device
  assert NEW not in state.last_seen_in_path
  assert state.last_seen_in_path[RECEIVER] == NOW
  assert not state.neighbor_edges
  assert not state.peer_history_pairs


def test_two_byte_guess_drawn_but_not_liveness_or_neighbor_evidence(chain):
  deliver, reap = chain
  route = deliver('0174')
  assert OLD in route['point_ids']  # preserve proximity-based visualization
  assert len(route['points']) == 3
  assert OLD not in state.last_seen_in_path
  assert state.last_seen_in_path[ORIGIN] == NOW
  assert state.last_seen_in_path[RECEIVER] == NOW
  assert not state.neighbor_edges  # do not bridge across an uncertain hop
  assert not state.peer_history_pairs
  assert state.devices[OLD].ts == STALE
  assert state.seen_devices[OLD] == STALE
  deliver('0174')
  assert OLD not in state.last_seen_in_path
  reap()
  assert OLD not in state.devices


@pytest.mark.parametrize('hop', ['01', '0174', '01742B'])
def test_manual_neighbor_precedes_first_hop_proximity(chain, hop):
  deliver, reap = chain
  # Three-byte collision too: retain the same deliberately colocated identities.
  if hop == '01742B':
    alternate = '01742B' + '33' * 29
    state.devices[alternate] = state.DeviceState(
      device_id=alternate, lat=42.479259, lon=-71.338814, ts=NOW, role='repeater')
    target = alternate
    decoder._rebuild_node_hash_map()
  else:
    target = NEW
  state.neighbor_edges[ORIGIN] = {target: {'manual': True, 'count': 0, 'last_seen': NOW}}
  route = deliver(hop)
  assert target in route['point_ids']
  assert OLD not in route['point_ids']
  assert state.last_seen_in_path[target] == NOW
  assert state.neighbor_edges[target][RECEIVER]['count'] == 1
  assert state.peer_history_pairs
  reap()
  assert OLD not in state.devices
