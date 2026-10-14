# Mudi 7 Speedify touchscreen control

Adds a **Speedify on/off card to the physical VPN Dashboard** on a GL.iNet
Mudi 7 (GL-E5800). The original touchscreen application, lock screen, and native
VPN cards remain in use.

Tested hardware: GL-E5800, GL firmware **4.10.0**, OpenWrt **23.05.4**, Speedify
**17.1.0.12947**. This is an unofficial, firmware-specific integration.
Speedify must already be installed, signed in, and working on the router.

## Behavior

- ON requests a connection using the existing Speedify configuration.
- OFF disconnects the tunnel while retaining the account and service.
- Connecting is shown as a transition, never as an established connection.
- Native VPN operations pass through to the backed-up firmware handler.
- The worker starts at boot. Speedify's own startup connection setting is separate.

This integration does not change routing, firewall rules, the kill switch,
bonding mode, server selection, or Speedify autoconnect settings. Ordinary
internet access after disconnect depends on the existing router configuration.
It does not claim that Speedify improves every connection or Zoom call.

## How it works

A Lua wrapper around the existing authenticated `vpn-client` RPC module adds
virtual tunnel ID `919001`. It uses the touchscreen's WireGuard display schema,
but creates no WireGuard peers or network interfaces. Only on/off is supported
for this virtual ID; configuration and deletion requests are rejected.

RPC requests enqueue a private action file and wake a Python worker through a
root-local Unix datagram socket. Nothing listens on a new TCP or UDP port.
The worker serializes actions and writes observed CLI state to an atomic cache.
CLI calls have timeouts, and duplicate on/off requests are idempotent.

While the screen is awake, state is refreshed every two seconds. While asleep,
the worker blocks on its local socket and performs only a 30-second housekeeping
check, without querying Speedify. Opening the physical dashboard wakes a stale
cache through its regular RPC reads. Stale cached state displays as unavailable
until refreshed; a control request does not require a fresh cache.

Blanking is detected using `bl_power`, because brightness stays nonzero when
this device's screen sleeps. Unknown backlight hardware defaults to active
polling. The worker briefly follows transitions after an action, even if the
screen sleeps during that action.

## Install

Requires root SSH access, Python 3 (`fcntl`, `socket`, `subprocess`), Lua 5.1 with
`cjson` and `nixio`, `jsonfilter`, `timeout`, and nginx. The installer refuses a
model, firmware, or stock RPC handler that differs from the inspected build.
It does not download dependencies or ship vendor binaries.

From this repository, substitute your router address:

```sh
tar -czf /tmp/speedify-screen.tgz router
ssh root@ROUTER 'mkdir -p /tmp/speedify-screen; tar -xzf - -C /tmp/speedify-screen' < /tmp/speedify-screen.tgz
ssh root@ROUTER 'sh /tmp/speedify-screen/router/install.sh'
```

Open **VPN Dashboard** on the touchscreen. The new Speedify card appears after
the native screen refreshes the list.

Installation backs up the original module, starts and validates the worker,
atomically replaces the RPC handler, reloads nginx, and enables the boot service.
It does not request a Speedify connection change or restart the stock screen.
A failed activation restores the stock handler and disables the worker.

Expected stock RPC SHA-256:

```text
35d3538e296b76cc5a5c576bd818a2f0ad01d53c870c7bc693c4e5aa84b1e8c1
```

## Rollback and updates

```sh
ssh root@ROUTER 'sh /usr/lib/speedify-screen/rollback.sh'
```

Rollback verifies the backup and active handler hashes, restores the original
RPC handler, reloads nginx, and disables the worker. Backup and integration files
are retained. Speedify connection state is unchanged.

For an update, stage the new `router/` directory, run rollback, then run the new
installer. The installer supports a verified inactive installation; it refuses
to overwrite an active or unknown handler. Keep the existing backup intact.

A firmware upgrade may remove or overwrite the customization. **Reboot
persistence does not imply firmware-upgrade persistence.** Reinspect any new
firmware before adapting the pinned checks.

## Validation and diagnostics

```sh
python3 -m unittest discover -s tests -v
lua5.1 tests/test_screen_adapter.lua
sh -n router/install.sh router/rollback.sh router/speedify-control
```

Tests use a fake CLI and do not change a real VPN. The Unix-socket integration
test requires permission to bind a local socket; a restrictive sandbox may deny
that operation. See [hardware validation](docs/validation.md) and
[code review](docs/review.md) for the measured results and limits.

Read-only router probes:

```sh
ssh root@ROUTER 'sh -s' < scripts/probe-router.sh
ssh root@ROUTER 'python3 - 45' < scripts/sample-router-cpu.py
```

`scripts/compare-latency.py` is an **optional macOS client benchmark that changes
the router's Speedify state**. It runs ON/OFF/OFF/ON, sends ICMP probes, downloads
about 32 MB, and attempts to leave Speedify connected. Run only when a temporary
VPN interruption and cellular data use are acceptable:

```sh
mkdir -p diagnostics
python3 scripts/compare-latency.py --router ROUTER --key /path/to/ssh-key --output diagnostics/latency.json
```

These are round-trip probes with a bounded download load, not a Zoom media test
or an estimate of one-way media jitter. Wi-Fi variation, cellular conditions,
ICMP handling, and server routing affect the result. The script does not measure
upload capacity or independently test link failure recovery.

Local `diagnostics/` contents are ignored by Git. Do not publish raw router
captures, vendor binaries, credentials, account data, or network logs.

## Known limits

One tested hardware/firmware combination; no portable package or automatic
upgrade migration. No account login, Speedify configuration editor, per-link
traffic view, or remote access endpoint is added.

A forcibly killed controller can leave its action lock until reboot. Status
continues to work. Remove `/var/run/speedify-screen-control.lock` only after
confirming no controller is running. The virtual tunnel ID must remain unused
by native VPN configuration.

Speedify CLI command semantics follow its
[official reference](https://support.speedify.com/article/285-speedify-cli).
