#!/usr/bin/env python3
"""Mac client ON/OFF/OFF/ON probes. Results are not Zoom media statistics.
Uses about 32 MB of download data plus ICMP. Requires authorized SSH access.
Always attempts to leave Speedify connected; errors restoring it are fatal.
"""
import argparse
import concurrent.futures
import json
import math
import re
import subprocess
import time
from pathlib import Path


def summarize(output):
    samples = [(int(seq), float(value)) for seq, value in re.findall(r'icmp_seq=(\d+).*?time[=<]([\d.]+) ms', output)]
    match = re.search(r'(\d+) packets transmitted, (\d+) packets received', output)
    if not match:
        raise RuntimeError('Ping did not produce a valid summary')
    sent, received = map(int, match.groups())
    values = sorted(value for _, value in samples)
    def percentile(p):
        return values[max(0, math.ceil(len(values) * p) - 1)] if values else None
    deltas = [abs(b[1] - a[1]) for a, b in zip(samples, samples[1:]) if b[0] == a[0] + 1]
    return {'sent': sent, 'received': received, 'loss_percent': 100 * (sent - received) / sent,
            'median_rtt_ms': percentile(.5), 'p95_rtt_ms': percentile(.95),
            'mean_adjacent_rtt_change_ms': sum(deltas) / len(deltas) if deltas else None}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--router', required=True)
    parser.add_argument('--key', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    ssh = ['ssh', '-i', args.key, '-o', 'IdentitiesOnly=yes', '-o', 'BatchMode=yes',
           '-o', 'ConnectTimeout=5', '-o', 'StrictHostKeyChecking=yes', 'root@' + args.router]
    def control(action):
        p = subprocess.run(ssh + ['/usr/libexec/speedify-screen/control ' + action], capture_output=True, text=True, timeout=35)
        if p.returncode:
            raise RuntimeError('Router controller failed: ' + p.stdout)
        return json.loads(p.stdout)
    def settle(action):
        control(action)
        deadline = time.monotonic() + 40
        expected = 'CONNECTED' if action == 'on' else 'LOGGED_IN'
        while time.monotonic() < deadline:
            if control('status').get('state') == expected:
                time.sleep(5)
                return
            time.sleep(1)
        raise RuntimeError('Speedify did not reach ' + expected)
    def ping(host):
        p = subprocess.run(['ping', '-n', '-c', '120', '-i', '0.25', '-W', '1000', host], capture_output=True, text=True, timeout=38)
        return summarize(p.stdout)
    results = []
    try:
        for index, action in enumerate(('on', 'off', 'off', 'on'), 1):
            settle(action)
            print('Starting phase %s: Speedify %s' % (index, action), flush=True)
            with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
                jobs = {name: pool.submit(ping, host) for name, host in (
                    ('gateway', args.router), ('cloudflare', '1.1.1.1'),
                    ('google', '8.8.8.8'), ('zoom_endpoint', '170.114.52.3'))}
                time.sleep(10)
                load = subprocess.run(['curl', '-fsS', '--max-time', '18', '--limit-rate', '500k',
                                       '-o', '/dev/null', '-w', '%{size_download} %{speed_download} %{time_total}',
                                       'https://speed.cloudflare.com/__down?bytes=8000000'],
                                      capture_output=True, text=True, timeout=20)
                result = {'phase': index, 'speedify': action, 'targets': {name: job.result() for name, job in jobs.items()},
                          'download': {'curl_exit': load.returncode, 'bytes_bytes_per_second_seconds': load.stdout}}
            results.append(result)
            Path(args.output).write_text(json.dumps(results, indent=2) + '\n')
            print(json.dumps(result), flush=True)
    finally:
        settle('on')
        print('Restored Speedify CONNECTED', flush=True)


if __name__ == '__main__':
    main()
