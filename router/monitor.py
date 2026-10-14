#!/usr/bin/python3
"""Root-local state cache and serialized action worker; opens no network ports."""
import fcntl
import json
import os
import signal
import socket
import subprocess
import time


BASE = '/var/run/speedify-screen'
CONTROL = '/usr/libexec/speedify-screen/control'


def atomic_json(path, value):
    tmp = os.path.splitext(os.fspath(path))[0] + '.tmp'
    with open(tmp, 'w') as output:
        json.dump(value, output)
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)


def remove_if_present(path):
    try:
        os.unlink(path)
    except FileNotFoundError:
        pass


def run_control(action):
    process = subprocess.Popen([CONTROL, action], stdout=subprocess.PIPE,
                               stderr=subprocess.DEVNULL, text=True, start_new_session=True)
    try:
        output, _ = process.communicate(timeout=28)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGTERM)
        try:
            process.communicate(timeout=2)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.communicate()
        return {'error': 'Speedify control timed out'}
    except BaseException:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.communicate(timeout=2)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.communicate()
        raise
    try:
        value = json.loads(output)
    except (ValueError, TypeError):
        return {'error': 'Invalid controller response'}
    if not isinstance(value, dict):
        return {'error': 'Invalid controller response'}
    if process.returncode and 'error' not in value:
        return {'error': 'Speedify control failed'}
    return value


def process_request(base, run, now=None):
    now = time.time() if now is None else now
    pending = os.path.join(base, 'pending')
    request = os.path.join(pending, 'request.json')
    if not os.path.exists(request):
        # Recover an interrupted enqueue without ever executing a partial request.
        if os.path.isdir(pending) and now - os.stat(pending).st_mtime > 35:
            remove_if_present(os.path.join(pending, 'request.tmp'))
            try:
                os.rmdir(pending)
            except OSError:
                pass
        return None
    try:
        with open(request) as source:
            value = json.load(source)
        age = now - float(value['timestamp'])
        if value['action'] not in ('on', 'off') or age < -1 or age > 30:
            return {'error': 'Expired or invalid request'}
        return {'action': value['action'], 'error': run(value['action']).get('error')}
    except (ValueError, KeyError, TypeError, OSError):
        return {'error': 'Cannot read control request'}
    finally:
        remove_if_present(request)
        try:
            os.rmdir(pending)
        except OSError:
            pass


def unresolved_attempt(attempt, state):
    if attempt and ((attempt.get('action') == 'on' and state == 'CONNECTED')
                    or (attempt.get('action') == 'off' and state in ('LOGGED_IN', 'LOGGED_OUT'))):
        return None
    return attempt


def screen_awake():
    """Use blanking state: brightness remains nonzero while this screen sleeps."""
    for path in ('/sys/class/backlight/soc:backlight/bl_power',
                 '/sys/class/backlight/backlight/bl_power'):
        try:
            with open(path) as source:
                return source.read().strip() == '0'
        except OSError:
            continue
    return True  # Unknown hardware: preserve responsive control.


def serve(base, run, awake, stopping=lambda: False, idle_interval=30, active_interval=2):
    """Private datagrams wake the worker; only validated files request actions."""
    endpoint = os.path.join(base, 'wake.sock')
    remove_if_present(endpoint)
    with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as wake:
        wake.bind(endpoint)
        os.chmod(endpoint, 0o600)
        last_attempt = None
        transition_until = 0
        first = True
        try:
            while not stopping():
                attempt = process_request(base, run)
                if attempt is not None:
                    last_attempt = attempt
                    transition_until = time.monotonic() + 30
                active = awake() or time.monotonic() < transition_until
                if first or attempt is not None or active:
                    result = run('status')
                    state = result.get('state', 'UNKNOWN')
                    snapshot = {'state': state, 'timestamp': int(time.time())}
                    last_attempt = unresolved_attempt(last_attempt, state)
                    error = result.get('error') or (last_attempt or {}).get('error')
                    if error:
                        snapshot['error'] = error
                    atomic_json(os.path.join(base, 'state.json'), snapshot)
                    if state not in ('CONNECTING', 'AUTO_CONNECTING', 'DISCONNECTING'):
                        transition_until = 0
                    first = False
                wake.settimeout(active_interval if active else idle_interval)
                try:
                    wake.recv(16)
                except socket.timeout:
                    pass
        finally:
            remove_if_present(endpoint)


def main():
    os.umask(0o077)
    os.makedirs(BASE, mode=0o700, exist_ok=True)
    with open(os.path.join(BASE, 'daemon.lock'), 'w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        # Raising unwinds communicate() and terminates any active child group.
        def stop(signum, frame):
            raise SystemExit(0)
        signal.signal(signal.SIGTERM, stop)
        serve(BASE, run_control, screen_awake)


if __name__ == '__main__':
    main()
