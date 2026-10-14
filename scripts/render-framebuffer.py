#!/usr/bin/env python3
"""Render the Mudi 7's 240x320 little-endian RGB565 framebuffer using stdlib."""
import struct
import sys
import zlib


with open(sys.argv[1], 'rb') as source:
    raw = source.read()
width, height = 240, 320
if len(raw) != width * height * 2:
    raise SystemExit('Expected exactly 153600 bytes')
rows = []
for y in range(height):
    row = bytearray([0])
    for x in range(width):
        value = struct.unpack_from('<H', raw, 2 * (y * width + x))[0]
        row.extend((((value >> 11) & 31) * 255 // 31,
                    ((value >> 5) & 63) * 255 // 63, (value & 31) * 255 // 31))
    rows.append(row)


def chunk(tag, value):
    return (struct.pack('!I', len(value)) + tag + value
            + struct.pack('!I', zlib.crc32(tag + value) & 0xffffffff))


png = (b'\x89PNG\r\n\x1a\n'
       + chunk(b'IHDR', struct.pack('!2I5B', width, height, 8, 2, 0, 0, 0))
       + chunk(b'IDAT', zlib.compress(b''.join(rows))) + chunk(b'IEND', b''))
with open(sys.argv[2], 'wb') as output:
    output.write(png)
