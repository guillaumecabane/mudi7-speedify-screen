#!/bin/sh
# Run on the target from a staged copy of this repository. Activates the card,
# but never requests a Speedify connection change.
set -eu
umask 077
expected=35d3538e296b76cc5a5c576bd818a2f0ad01d53c870c7bc693c4e5aa84b1e8c1
rpc=/usr/lib/oui-httpd/rpc/vpn-client
lib=/usr/lib/speedify-screen
bin=/usr/libexec/speedify-screen
src=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)

die() { printf '%s\n' "$1" >&2; exit 1; }
[ "$(id -u)" = 0 ] || die 'Run as root on the router'
[ "$(cat /etc/glversion)" = 4.10.0 ] || die 'This build is pinned to GL firmware 4.10.0'
grep -q 'E5800' /tmp/sysinfo/model || die 'This build is pinned to the Mudi 7'
[ "$(sha256sum "$rpc" | awk '{print $1}')" = "$expected" ] || die 'Stock VPN handler differs from the inspected build'
if [ -e "$lib" ] || [ -e "$bin" ] || [ -e /etc/init.d/speedify-screen ]; then
    [ ! -L "$lib" ] && [ ! -L "$bin" ] && [ ! -L /etc/init.d/speedify-screen ] || die 'Unexpected symlink in installation paths'
    [ -d "$lib" ] && [ -d "$bin" ] && [ -f "$lib/original.sha256" ] && [ -f "$lib/vpn-client.original" ] || die 'Unknown existing installation paths'
    [ "$(cat "$lib/original.sha256")" = "$expected" ] || die 'Unknown backup manifest'
    [ "$(sha256sum "$lib/vpn-client.original" | awk '{print $1}')" = "$expected" ] || die 'Backup differs from inspected stock handler'
    printf 'Resuming an inactive installation with a verified stock backup.\n'
fi
for command in python3 lua jsonfilter timeout nginx sha256sum; do
    command -v "$command" >/dev/null || die "Missing runtime: $command"
done
python3 -c 'import fcntl,json,os,signal,socket,subprocess,time,sys; compile(open(sys.argv[1]).read(), "monitor.py", "exec")' "$src/monitor.py"
sh "$src/speedify-control" status >/dev/null
lua - "$rpc" <<'LUA'
assert(require('nixio').socket)
local native = assert(loadfile(arg[1]))()
local list = native.get_tunnel({})
assert(type(list) == 'table' and type(list.tunnels) == 'table', 'Unexpected VPN schema')
for _,t in ipairs(list.tunnels) do
    assert(tonumber(t.tunnel_id) ~= 919001 and t.id ~= 'speedify-screen', 'Virtual ID collision')
end
LUA
for file in screen-adapter.lua vpn-client-wrapper.lua; do
    lua - "$src/$file" <<'LUA'
assert(loadfile(arg[1]))
LUA
done
nginx -t

mkdir -p "$lib" "$bin"
cp -p "$rpc" "$lib/vpn-client.original"
cp "$src/screen-adapter.lua" "$lib/screen-adapter.lua"
cp "$src/vpn-client-wrapper.lua" "$lib/vpn-client-wrapper.lua"
cp "$src/rollback.sh" "$lib/rollback.sh"
cp "$src/speedify-control" "$bin/control"
cp "$src/monitor.py" "$bin/monitor.py"
cp "$src/speedify-screen.init" /etc/init.d/speedify-screen
chmod 755 "$bin/control" "$bin/monitor.py" "$lib/rollback.sh" /etc/init.d/speedify-screen
sha256sum "$lib/vpn-client-wrapper.lua" | awk '{print $1}' > "$lib/wrapper.sha256"
printf '%s\n' "$expected" > "$lib/original.sha256"

activated=0
complete=0
cleanup() {
    if [ "$complete" != 1 ]; then
        if [ "$activated" = 1 ]; then
            cp -p "$lib/vpn-client.original" "$rpc.restore"
            mv "$rpc.restore" "$rpc"
            nginx -s reload || :
        fi
        /etc/init.d/speedify-screen stop || :
        /etc/init.d/speedify-screen disable || :
        printf 'Activation did not complete; stock handler restored. Staged installation files retained for inspection.\n' >&2
    fi
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
/etc/init.d/speedify-screen stop
rm -f /var/run/speedify-screen/state.json
/etc/init.d/speedify-screen start
ready=0
for i in 1 2 3 4 5 6 7 8 9 10; do
    if [ -s /var/run/speedify-screen/state.json ]; then ready=1; break; fi
    sleep 1
done
[ "$ready" = 1 ] || die 'State monitor did not initialize'
# Validate the complete wrapper by loading it directly before changing RPC.
lua - "$lib/vpn-client-wrapper.lua" <<'LUA'
local module = assert(loadfile(arg[1]))()
local n = 0
for _,row in ipairs(module.get_status({}).status_list) do
    if row.tunnel_id == 919001 then n = n + 1 end
end
assert(n == 1, 'Virtual status card missing')
LUA
cp "$lib/vpn-client-wrapper.lua" "$rpc.new"
chmod 644 "$rpc.new"
mv "$rpc.new" "$rpc"
activated=1
nginx -s reload
/etc/init.d/speedify-screen enable
complete=1
printf 'Speedify virtual card activated. Speedify connection state was not changed.\n'
