#!/bin/sh
# Run on the router, or stream with: ssh root@ROUTER 'sh -s' < scripts/probe-router.sh
# No installs, settings changes, service stops, or Speedify connect/disconnect.
set -u

section() { printf '\n--- %s ---\n' "$1"; }
section 'Model and firmware'
for f in /tmp/sysinfo/model /tmp/sysinfo/board_name /etc/glversion /etc/openwrt_release; do
    if [ -r "$f" ]; then printf '%s\n' "$f"; cat "$f"; fi
done

section 'Available runtime tools'
for tool in ubus uci jsonfilter timeout lua python3 strings; do
    command -v "$tool" 2>/dev/null || :
done

section 'Installed screen and Speedify packages'
if command -v opkg >/dev/null 2>&1; then
    opkg list-installed | awk 'tolower($0) ~ /speedify|gl-screen|gl_screen|screen|lvgl/ {print}'
fi

section 'Speedify state only (no account or adapter data)'
if [ -x /usr/share/speedify/speedify_cli ] && command -v timeout >/dev/null 2>&1; then
    timeout 8 /usr/share/speedify/speedify_cli state 2>/dev/null || printf 'State query failed\n'
else
    printf 'CLI or timeout unavailable\n'
fi

section 'Screen devices (metadata only)'
for f in /dev/fb0 /dev/input/event* /sys/class/graphics/fb0/virtual_size /sys/class/graphics/fb0/bits_per_pixel; do
    [ -e "$f" ] || continue
    ls -l "$f"
    case "$f" in /sys/*) cat "$f" ;; esac
done

section 'Screen API schemas (no method invocation)'
if command -v ubus >/dev/null 2>&1; then
    ubus -v list '*screen*' 2>/dev/null || :
fi

section 'Screen and VPN integration paths (names only)'
for f in /etc/init.d/gl_screen /usr/bin/gl_screen /usr/bin/screen_disp_switch /usr/bin/switchaction /usr/lib/oui-httpd/rpc/vpn-client /usr/lib/oui-httpd/rpc/vpn-client.lua; do
    [ ! -e "$f" ] || ls -l "$f"
done
for d in /etc/gl_screen /etc/gl-switch.d; do
    [ ! -d "$d" ] || ls -la "$d"
done

section 'Screen configuration keys (values omitted)'
if command -v uci >/dev/null 2>&1; then
    uci -q show gl_screen | sed 's/=.*$/=<omitted>/'
fi
