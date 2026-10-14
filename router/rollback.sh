#!/bin/sh
set -eu
lib=/usr/lib/speedify-screen
rpc=/usr/lib/oui-httpd/rpc/vpn-client
current=$(sha256sum "$rpc" | awk '{print $1}')
original=$(cat "$lib/original.sha256")
wrapper=$(cat "$lib/wrapper.sha256")
[ "$(sha256sum "$lib/vpn-client.original" | awk '{print $1}')" = "$original" ] || {
    printf 'Backup checksum mismatch; refusing restoration\n' >&2; exit 1;
}
case "$current" in
    "$wrapper")
        cp -p "$lib/vpn-client.original" "$rpc.restore"
        mv "$rpc.restore" "$rpc"
        nginx -s reload
        ;;
    "$original") ;;
    *) printf 'VPN handler changed outside this installation; refusing to overwrite it\n' >&2; exit 1 ;;
esac
/etc/init.d/speedify-screen stop
/etc/init.d/speedify-screen disable
printf 'Stock VPN handler restored. Speedify connection state was not changed. Backup and adapter files retained.\n'
