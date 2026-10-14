import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest


SOURCE = Path(__file__).resolve().parents[1] / 'router' / 'monitor.py'
spec = importlib.util.spec_from_file_location('speedify_monitor', SOURCE)
monitor = importlib.util.module_from_spec(spec)
spec.loader.exec_module(monitor)


class MonitorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.calls = []

    def fake_control(self, action):
        self.calls.append(action)
        return {'state': 'CONNECTING'}

    def enqueue(self, value):
        pending = self.base / 'pending'
        pending.mkdir()
        (pending / 'request.json').write_text(json.dumps(value))

    def test_actions_are_processed_once(self):
        for action in ['on', 'off']:
            self.enqueue({'action': action, 'timestamp': 100})
            self.assertEqual(monitor.process_request(self.base, self.fake_control, 100), {'action': action, 'error': None})
            self.assertIsNone(monitor.process_request(self.base, self.fake_control, 100))
        self.assertEqual(self.calls, ['on', 'off'])

    def test_bad_requests_never_invoke_controller(self):
        for value in [{'action': 'on; reboot', 'timestamp': 100},
                      {'action': 'on', 'timestamp': 60},
                      {'action': 'on', 'timestamp': 120}, {}, [], None]:
            self.enqueue(value)
            self.assertTrue(monitor.process_request(self.base, self.fake_control, 100))
            self.assertFalse((self.base / 'pending').exists())
        self.assertEqual(self.calls, [])

    def test_partial_enqueue_recovers_without_action(self):
        pending = self.base / 'pending'
        pending.mkdir()
        (pending / 'request.tmp').write_text('partial')
        os.utime(pending, (50, 50))
        self.assertIsNone(monitor.process_request(self.base, self.fake_control, 100))
        self.assertFalse(pending.exists())
        self.assertEqual(self.calls, [])

    def test_error_is_returned_and_request_is_consumed(self):
        self.enqueue({'action': 'on', 'timestamp': 100})
        self.assertEqual(monitor.process_request(self.base, lambda _: {'error': 'offline'}, 100), {'action': 'on', 'error': 'offline'})
        self.assertFalse((self.base / 'pending').exists())

    def test_atomic_state_file_is_private(self):
        path = self.base / 'state.json'
        monitor.atomic_json(path, {'state': 'CONNECTED', 'timestamp': 100})
        self.assertEqual(json.loads(path.read_text())['state'], 'CONNECTED')
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertFalse(path.with_suffix('.tmp').exists())

    def test_connect_error_clears_only_after_actual_connection(self):
        attempt = {'action': 'on', 'error': 'timeout'}
        self.assertEqual(monitor.unresolved_attempt(attempt, 'LOGGED_IN'), attempt)
        self.assertEqual(monitor.unresolved_attempt(attempt, 'CONNECTING'), attempt)
        self.assertIsNone(monitor.unresolved_attempt(attempt, 'CONNECTED'))
        self.assertIsNone(monitor.unresolved_attempt(None, 'LOGGED_IN'))

    def test_disconnect_error_clears_only_after_actual_disconnect(self):
        attempt = {'action': 'off', 'error': 'timeout'}
        self.assertEqual(monitor.unresolved_attempt(attempt, 'CONNECTED'), attempt)
        self.assertEqual(monitor.unresolved_attempt(attempt, 'UNKNOWN'), attempt)
        self.assertIsNone(monitor.unresolved_attempt(attempt, 'LOGGED_IN'))

    def test_idle_worker_does_not_query_but_socket_action_wakes_it(self):
        import socket
        import threading
        import time
        stop = threading.Event()
        calls = []
        def run(action):
            calls.append(action)
            return {'state': 'LOGGED_IN'}
        thread = threading.Thread(target=monitor.serve,
                                  args=(str(self.base), run, lambda: False, stop.is_set, 0.05, 0.01))
        thread.start()
        self.addCleanup(lambda: (stop.set(), thread.join(1)))
        deadline = time.monotonic() + 1
        while not (self.base / 'state.json').exists() and time.monotonic() < deadline:
            time.sleep(0.005)
        time.sleep(0.12)
        self.assertEqual(calls, ['status'])
        self.enqueue({'action': 'off', 'timestamp': time.time()})
        with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as sender:
            sender.sendto(b'w', str(self.base / 'wake.sock'))
        deadline = time.monotonic() + 1
        while 'off' not in calls and time.monotonic() < deadline:
            time.sleep(0.005)
        self.assertEqual(calls[:3], ['status', 'off', 'status'])
        stop.set()
        thread.join(1)
        self.assertFalse(thread.is_alive())
        self.assertFalse((self.base / 'wake.sock').exists())

    def test_dashboard_wake_refreshes_stale_idle_state(self):
        import socket
        import threading
        import time
        stop, awake = threading.Event(), threading.Event()
        calls = []
        def run(action):
            calls.append(action)
            return {'state': 'CONNECTED'}
        thread = threading.Thread(target=monitor.serve,
                                  args=(str(self.base), run, awake.is_set, stop.is_set, 0.1, 0.02))
        thread.start()
        self.addCleanup(lambda: (stop.set(), thread.join(1)))
        deadline = time.monotonic() + 1
        while not (self.base / 'state.json').exists() and time.monotonic() < deadline:
            time.sleep(0.005)
        self.assertEqual(calls, ['status'])
        awake.set()
        with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as sender:
            sender.sendto(b'w', str(self.base / 'wake.sock'))
        deadline = time.monotonic() + 1
        while len(calls) < 2 and time.monotonic() < deadline:
            time.sleep(0.005)
        self.assertGreaterEqual(len(calls), 2)
        stop.set()
        thread.join(1)
        self.assertFalse(thread.is_alive())
