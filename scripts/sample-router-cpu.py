#!/usr/bin/env python3
"""Read-only CPU sample; execute on the router. No non-stdlib dependencies."""
import json
import os
import sys
import time


def read(path):
    with open(path) as source:
        return source.read()


def processes():
    result = {}
    for entry in os.listdir('/proc'):
        if not entry.isdigit():
            continue
        try:
            command = read('/proc/' + entry + '/cmdline').replace('\0', ' ')
            comm = read('/proc/' + entry + '/comm').strip()
            if '/usr/libexec/speedify-screen/monitor.py' in command:
                result['monitor'] = int(entry)
            elif comm == 'gl_screen':
                result['screen'] = int(entry)
            elif comm == 'speedifyservice':
                result['speedify'] = int(entry)
        except OSError:
            pass
    return result


def proc(pid):
    fields = read('/proc/%s/stat' % pid).rsplit(')', 1)[1].split()
    status = dict(line.split(':', 1) for line in read('/proc/%s/status' % pid).splitlines() if ':' in line)
    return {
        'ticks': sum(int(fields[i]) for i in (11, 12)),
        'child_ticks': sum(int(fields[i]) for i in (13, 14)),
        'rss_kib': int(status.get('VmRSS', '0').split()[0]),
        'context_switches': sum(int(status.get(k, '0')) for k in ('voluntary_ctxt_switches', 'nonvoluntary_ctxt_switches'))
    }


def screen_power():
    for path in ('/sys/class/backlight/backlight/bl_power', '/sys/class/backlight/soc:backlight/bl_power'):
        try:
            return {'path': path, 'value': read(path).strip()}
        except OSError:
            pass
    return None


def main():
    duration = int(sys.argv[1]) if len(sys.argv) > 1 else 45
    ticks_per_second = os.sysconf('SC_CLK_TCK')
    ids = processes()
    initial = {name: proc(pid) for name, pid in ids.items()}
    start_power = screen_power()
    start = time.monotonic()
    print(json.dumps({'sampling_seconds': duration, 'processes': ids, 'screen_power': start_power}), flush=True)
    time.sleep(duration)
    elapsed = time.monotonic() - start
    final = {name: proc(pid) for name, pid in ids.items()}
    result = {'duration_seconds': elapsed, 'ticks_per_second': ticks_per_second, 'screen_power_start': start_power,
              'screen_power_end': screen_power(), 'processes': {}}
    for name, end in final.items():
        before = initial[name]
        own = (end['ticks'] - before['ticks']) / ticks_per_second
        child = (end['child_ticks'] - before['child_ticks']) / ticks_per_second
        result['processes'][name] = {
            'pid': ids[name], 'own_cpu_percent_one_core': own / elapsed * 100,
            'children_cpu_percent_one_core': child / elapsed * 100,
            'cpu_seconds_including_children': own + child, 'rss_kib': end['rss_kib'],
            'context_switches': end['context_switches'] - before['context_switches']
        }
    print(json.dumps(result), flush=True)


if __name__ == '__main__':
    main()
