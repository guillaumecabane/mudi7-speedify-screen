# Hardware validation

Validated on 2026-10-14 with one Mudi 7 (GL-E5800), firmware 4.10.0,
OpenWrt 23.05.4, Speedify 17.1.0.12947. Results apply to this setup.

## Touchscreen and control

The physical VPN Dashboard displayed the added Speedify card. A physical OFF tap
changed the actual CLI state to `LOGGED_IN`; a physical ON tap returned it to
`CONNECTED`. The account remained signed in. Requests through the installed Lua
wrapper also exercised the queue and local Unix socket on the router.

With the worker stopped, an on request returned busy/unavailable and its queued
file was removed. Restarting the worker restored control. The stock screen
process did not need restarting during installation or the sleep optimization.

## Reboot persistence

An actual router reboot changed its boot ID. The boot service remained enabled,
the Python worker started automatically, the wrapper and original-handler
checksums matched their pre-reboot values, and the virtual card was present.
An on request reconnected the real tunnel. The physical card was then confirmed
present and ON after reopening VPN Dashboard. Awake `bl_power` was verified as 0.

Speedify itself initially reported `LOGGED_IN` after reboot, consistent with its
existing startup connection setting. The integration persisted; it does not
override that independent Speedify setting.

## Screen-off CPU

Read `/proc` twice over a 45-second interval, including the monitor's own CPU
and waited-for child CPU. The screen's `bl_power` was 1 at both ends of each
sample. These are percentages of **one CPU core**, not total device load.

| Measurement | Before | After |
|---|---:|---:|
| Monitor plus children CPU | 3.04% | 0.022% |
| Child-process CPU time | 1.20 s | 0 s |
| Monitor context switches | 136 | 1 |
| Stock screen CPU | 0.62% | 0.62% |
| Monitor resident memory | 9.05 MiB | 9.41 MiB |

The after sample measured 0.01 seconds of monitor CPU in 45 seconds: close to the
measurement resolution, not a claim of zero consumption. The integration does
not suspend the stock screen process or alter platform power settings.

## Connection comparison

A Mac connected through the router ran four phases: ON, OFF, OFF, ON. The Mac's
own VPN was disconnected. Each phase sent 120 ICMP probes per target at 250 ms
intervals and included an 8 MB HTTPS download capped at approximately 4.1 Mb/s.
Speedify was in its existing Streaming mode; configuration was unchanged.

| Phase | Speedify | Zoom endpoint median RTT | p95 RTT | Probe loss | Gateway p95 RTT |
|---|---|---:|---:|---:|---:|
| 1 | ON | 66.4 ms | 196.7 ms | 0/120 | 89.4 ms |
| 2 | OFF | 41.9 ms | 113.2 ms | 0/120 | 45.4 ms |
| 3 | OFF | 49.6 ms | 265.1 ms | 0/120 | 80.3 ms |
| 4 | ON | 65.4 ms | 178.0 ms | 2/120 | 91.0 ms |

The on phases had higher median RTT; tail delay was inconsistent in both modes.
The gateway also showed delay spikes, so local Wi-Fi variation contributed.
The fixed download cap was reached in every phase; this was not a maximum
throughput test. ICMP response loss is not proof of Zoom media loss.

Zoom's native network diagnostics passed its meeting/chat service checks.
Its native test meeting was opened with microphone/camera permission, without
inviting anyone, then ended. With one participant, its audio quality statistics
were blank and overall media bandwidth was zero. No usable Zoom media loss or
jitter comparison resulted.

**Conclusion:** this run does not establish better Zoom call quality with
Speedify. It measures additional median delay on these probes. It does not test
upload saturation, multi-participant audio/video, or interruption of one uplink.
Those require a separate controlled media/failover test. Speedify was restored
to `CONNECTED` after the comparison.

## Automated checks

24 Python tests passed, including fake-CLI action timeouts, serialization,
idempotency, invalid requests, cache privacy, error recovery, idle wake-up, and
dashboard refresh. Lua 5.1 adapter assertions passed locally and on the router;
shell syntax checks passed. Fake-CLI tests do not alter an actual VPN.

Raw captures, network logs, account details, and firmware binaries are excluded
from this repository.
