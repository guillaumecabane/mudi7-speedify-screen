# Code review

Review scope: controller, Lua RPC wrapper and virtual-card adapter, Python worker,
installer, rollback, boot service, tests, diagnostics scripts, and publication
contents. Reviewed on 2026-10-14.

| Dimension | Assessment |
|---|---|
| Security | Pass within the pinned firmware and existing authenticated RPC boundary |
| Performance | Pass for screen-off overhead; active polling is bounded |
| Correctness | Pass for tested state transitions, queue handling, and failure cases |
| Maintainability | Acceptable for a small firmware-specific integration |

## Findings addressed

- **P2 — Repeated CLI work while asleep.** The monitor previously queried every
  second. `router/monitor.py` now waits on a private datagram socket and reads
  backlight blanking state. The measured screen-off overhead dropped from 3.04%
  to 0.022% of one core, including child processes.
- **P1 — A deliberately stale idle cache could prevent control.** The RPC queue
  no longer requires a fresh status snapshot. It sends a nonblocking wake-up
  and rejects/cleans the request if the worker is unavailable. Pending display
  state survives a stale snapshot. Host and actual-router checks cover these
  paths.
- **P2 — Worker shutdown could leave a detached controller running.** SIGTERM
  now unwinds the worker and terminates its child process group, with a bounded
  wait before SIGKILL. Normal shell traps release the action lock.
- **P2 — Session notes overstated readiness and contained obsolete behavior.**
  Public documentation now describes measured behavior, pinned compatibility,
  rollback/update procedures, and the limits of the performance comparison.

## Positive observations

Only validated on/off choices reach the CLI; RPC values are not interpolated
into shell commands. Action execution and worker ownership have separate locks.
Private files are written atomically. No account credentials or firmware binaries
are distributed, and no new network port is opened. Native VPN changes pass
through to the original module. Installation and rollback verify the stock
handler and refuse unknown replacements.

The automated tests use a fake CLI and exercise adverse cases rather than
requiring a live VPN or credentials. Hardware checks separately verify the
physical screen and actual daemon state.

## Remaining limits

Firmware 4.10.0 only. A firmware upgrade requires fresh inspection. A SIGKILL can
leave the controller's fail-closed lock until reboot. Runtime virtual-ID collision
avoidance relies on the installation check and reserving ID 919001. The native
screen protocol remains a vendor implementation detail. Multi-participant Zoom
quality and uplink failover have not been demonstrated by this validation.

No remaining release-blocking code findings were identified for the tested
configuration. This is a source review plus tests, not an independent security
audit or a broad hardware compatibility claim.
