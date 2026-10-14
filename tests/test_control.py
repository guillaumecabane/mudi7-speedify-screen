import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import time
import unittest


CONTROL = Path(__file__).resolve().parents[1] / 'router' / 'speedify-control'


class ControlTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.state_file = self.root / 'state.json'
        self.log = self.root / 'calls'
        self.state_file.write_text('{"state":"LOGGED_IN"}')
        self.env = dict(os.environ, MOCK_STATE=str(self.state_file), MOCK_LOG=str(self.log))
        self.env['SPEEDIFY_LOCK_DIR'] = str(self.root / 'lock')
        self.env['SPEEDIFY_CLI'] = self.script('cli', '''
import json, os, pathlib, sys, time
action = sys.argv[1]
with open(os.environ['MOCK_LOG'], 'a') as f:
    f.write(action + '\\n')
if os.environ.get('MOCK_FAIL') == action:
    sys.exit(1)
time.sleep(float(os.environ.get('MOCK_DELAY_' + action.upper(), '0')))
path = pathlib.Path(os.environ['MOCK_STATE'])
if action == 'state':
    print(path.read_text())
elif action == 'connect':
    path.write_text('{"state":"CONNECTING"}')
    if os.environ.get('MOCK_FAIL_AFTER_ACCEPT'):
        sys.exit(1)
elif action == 'disconnect':
    path.write_text('{"state":"DISCONNECTING"}')
    if os.environ.get('MOCK_FAIL_AFTER_ACCEPT'):
        sys.exit(1)
else:
    sys.exit(2)
''')
        self.env['SPEEDIFY_JSONFILTER'] = self.script('jsonfilter', '''
import json, sys
try:
    print(json.load(sys.stdin)['state'])
except (ValueError, KeyError, TypeError):
    sys.exit(1)
''')
        self.env['SPEEDIFY_TIMEOUT_BIN'] = self.script('timeout', '''
import subprocess, sys
try:
    sys.exit(subprocess.run(sys.argv[2:], timeout=float(sys.argv[1])).returncode)
except subprocess.TimeoutExpired:
    sys.exit(124)
''')

    def script(self, name, source):
        path = self.root / name
        # Avoid shebang path-length limits on macOS temporary directories.
        code = self.root / (name + '.py')
        code.write_text(source)
        path.write_text('#!/bin/sh\nexec ' + shlex.quote(sys.executable) + ' ' + shlex.quote(str(code)) + ' "$@"\n')
        path.chmod(0o700)
        return str(path)

    def call(self, action, success=True):
        result = subprocess.run(['sh', str(CONTROL), action], env=self.env,
                                capture_output=True, text=True, timeout=8)
        self.assertEqual(result.returncode == 0, success, result.stdout + result.stderr)
        return json.loads(result.stdout)

    def state(self, value):
        self.state_file.write_text(json.dumps({'state': value}))

    def calls(self):
        return self.log.read_text().splitlines() if self.log.exists() else []

    def test_status_is_read_only(self):
        self.state('CONNECTED')
        self.assertEqual(self.call('status'), {'state': 'CONNECTED'})
        self.assertEqual(self.calls(), ['state'])
        self.assertFalse(Path(self.env['SPEEDIFY_LOCK_DIR']).exists())

    def test_connect_reports_transition_not_success(self):
        self.assertEqual(self.call('on'), {
            'requested': 'on', 'command_sent': True, 'state': 'CONNECTING'})
        self.assertEqual(self.calls(), ['state', 'connect', 'state'])

    def test_disconnect_preserves_login_and_settings(self):
        self.state('CONNECTED')
        self.assertEqual(self.call('off'), {
            'requested': 'off', 'command_sent': True, 'state': 'DISCONNECTING'})
        self.assertEqual(self.calls(), ['state', 'disconnect', 'state'])

    def test_repeated_requests_are_idempotent(self):
        for action, states in [('on', ['CONNECTED', 'CONNECTING', 'AUTO_CONNECTING']),
                               ('off', ['LOGGED_IN', 'LOGGED_OUT', 'DISCONNECTING'])]:
            for state in states:
                with self.subTest(action=action, state=state):
                    self.state(state)
                    result = self.call(action)
                    self.assertFalse(result['command_sent'])
        self.assertTrue(all(c == 'state' for c in self.calls()))

    def test_off_can_cancel_connecting(self):
        for state in ['CONNECTING', 'AUTO_CONNECTING']:
            self.state(state)
            self.assertTrue(self.call('off')['command_sent'])

    def test_unsafe_states_do_not_issue_commands(self):
        for action in ['on', 'off']:
            for state in ['UNKNOWN', 'LOGGING_IN', 'OVERLIMIT']:
                with self.subTest(action=action, state=state):
                    self.state(state)
                    self.call(action, success=False)
        self.state('LOGGED_OUT')
        self.call('on', success=False)
        self.state('DISCONNECTING')
        self.call('on', success=False)
        self.assertTrue(all(c == 'state' for c in self.calls()))

    def test_invalid_cli_responses_fail_closed(self):
        for response in ['not json', '{}', '{"state":"CONNECTED; echo bad"}',
                         '{"state":null}', '{"state":"NEW_STATE"}']:
            self.state_file.write_text(response)
            self.call('on', success=False)
        self.assertTrue(all(c == 'state' for c in self.calls()))

    def test_errors_release_lock(self):
        self.env['MOCK_FAIL'] = 'connect'
        self.call('on', success=False)
        self.assertFalse(Path(self.env['SPEEDIFY_LOCK_DIR']).exists())
        del self.env['MOCK_FAIL']
        self.assertTrue(self.call('on')['command_sent'])

    def test_cli_timeout_releases_lock(self):
        self.env.update(SPEEDIFY_TIMEOUT_SECONDS='1', MOCK_DELAY_STATE='2')
        self.call('on', success=False)
        self.assertFalse(Path(self.env['SPEEDIFY_LOCK_DIR']).exists())
        self.assertEqual(self.calls(), ['state'])

    def test_cli_error_after_accept_uses_actual_state(self):
        self.env['MOCK_FAIL_AFTER_ACCEPT'] = '1'
        self.assertEqual(self.call('on')['state'], 'CONNECTING')
        self.state('CONNECTED')
        self.assertEqual(self.call('off')['state'], 'DISCONNECTING')
        self.assertFalse(Path(self.env['SPEEDIFY_LOCK_DIR']).exists())

    def test_busy_lock_rejects_actions_but_allows_status(self):
        Path(self.env['SPEEDIFY_LOCK_DIR']).mkdir()
        self.call('on', success=False)
        self.assertEqual(self.calls(), [])
        self.assertEqual(self.call('status')['state'], 'LOGGED_IN')

    def test_concurrent_taps_send_one_command(self):
        self.env['MOCK_DELAY_CONNECT'] = '0.5'
        first = subprocess.Popen(['sh', str(CONTROL), 'on'], env=self.env,
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            for _ in range(100):
                if 'connect' in self.calls():
                    break
                time.sleep(0.02)
            self.assertIn('connect', self.calls())
            self.call('on', success=False)
            output, error = first.communicate(timeout=5)
            self.assertEqual(first.returncode, 0, output + error)
            self.assertEqual(self.calls().count('connect'), 1)
        finally:
            if first.poll() is None:
                first.kill()
                first.communicate()

    def test_invalid_action_does_not_invoke_cli(self):
        self.call('toggle', success=False)
        self.assertEqual(self.calls(), [])

    def test_missing_cli_is_an_error(self):
        self.env['SPEEDIFY_CLI'] = str(self.root / 'absent')
        self.call('status', success=False)
        self.assertEqual(self.calls(), [])

    def test_invalid_timeouts_fail_before_cli(self):
        for timeout in ['0', '31', 'abc', '1; echo bad']:
            self.env['SPEEDIFY_TIMEOUT_SECONDS'] = timeout
            self.call('on', success=False)
        self.assertEqual(self.calls(), [])


if __name__ == '__main__':
    unittest.main()
