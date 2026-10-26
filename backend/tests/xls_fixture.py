"""Minimal BIFF8/CFB fixture writer, independent of the production decoder."""

import struct


def record(code, data=b""):
    return struct.pack("<HH", code, len(data)) + data


def workbook(rows, extra=b"", ole=False, hidden=False):
    def bof(kind):
        return record(
            0x0809, struct.pack("<HHHHII", 0x0600, kind, 0x0DBB, 1997, 0x41, 6)
        )

    strings = list(dict.fromkeys(v for row in rows for v in row if isinstance(v, str)))
    sst = struct.pack(
        "<II", sum(isinstance(v, str) for row in rows for v in row), len(strings)
    )
    for v in strings:
        sst += struct.pack("<HB", len(v), 1) + v.encode("utf-16-le")
    sheet = bof(0x10) + record(
        0x0200, struct.pack("<IIHHH", 0, len(rows), 0, max(map(len, rows)), 0)
    )
    for ri, row in enumerate(rows):
        for ci, v in enumerate(row):
            loc = struct.pack("<HHH", ri, ci, 0)
            if isinstance(v, str):
                sheet += record(0x00FD, loc + struct.pack("<I", strings.index(v)))
            elif isinstance(v, bool):
                sheet += record(0x0205, loc + bytes([int(v), 0]))
            elif v is not None:
                sheet += record(0x0203, loc + struct.pack("<d", v))
    sheet += extra + record(0x000A)
    bounds = lambda offset: record(
        0x0085, struct.pack("<IBBB", offset, int(hidden), 0, 7) + b"\x00Catalog"
    )
    before = bof(5) + record(0x0042, struct.pack("<H", 1200)) + record(0x00FC, sst)
    offset = len(before) + len(bounds(0)) + 4
    stream = before + bounds(offset) + record(0x000A) + sheet
    return compound(stream) if ole else stream


def compound(stream, extra_name=None):
    stream = stream.ljust(max(4096, (len(stream) + 511) // 512 * 512), b"\0")
    sectors = len(stream) // 512
    header = bytearray(512)
    header[:8] = bytes.fromhex("D0CF11E0A1B11AE1")
    struct.pack_into("<HHHHH", header, 24, 0x3E, 3, 0xFFFE, 9, 6)
    struct.pack_into(
        "<IIIIIIIII", header, 40, 0, 1, 0, 0, 4096, 0xFFFFFFFE, 0, 0xFFFFFFFE, 0
    )
    struct.pack_into("<109I", header, 76, sectors + 1, *([0xFFFFFFFF] * 108))

    def entry(name, kind, start, size, child=0xFFFFFFFF, right=0xFFFFFFFF):
        e = bytearray(128)
        text = (name + "\0").encode("utf-16-le")
        e[: len(text)] = text
        struct.pack_into("<HBBIII", e, 64, len(text), kind, 1, 0xFFFFFFFF, right, child)
        struct.pack_into("<IQ", e, 116, start, size)
        return e

    directory = entry("Root Entry", 5, 0xFFFFFFFE, 0, child=1) + entry(
        "Workbook", 2, 1, len(stream), right=2 if extra_name else 0xFFFFFFFF
    )
    if extra_name:
        directory += entry(extra_name, 2, 0xFFFFFFFE, 0)
    directory = directory.ljust(512, b"\0")
    fat = [0xFFFFFFFE] + list(range(2, sectors + 1)) + [0xFFFFFFFE, 0xFFFFFFFD]
    fat += (128 - len(fat)) * [0xFFFFFFFF]
    return bytes(header) + directory + stream + struct.pack("<128I", *fat)
