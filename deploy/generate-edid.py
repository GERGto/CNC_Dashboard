#!/usr/bin/env python3
"""Create a KMS-safe copy of the machine display EDID.

The MPI7002 advertises its native 1024x600 timing with sync intervals that the
Raspberry Pi vc4 KMS driver rejects.  Keep all identification/CEA data from the
real display, but replace the preferred detailed timing with a timing that vc4
accepts.

The pixel clock is deliberately 51.20 MHz: at the previous 49.00 MHz the TMDS
data rate was 490 Mbit/s per lane, whose 5th harmonic (2.45 GHz) sits in the
middle of the 2.4 GHz band. Every Wi-Fi scan or transmit burst visibly sheared
the panel image for seconds. At 51.20 MHz the harmonic lands at 2.56 GHz,
outside the Wi-Fi band.
"""

from __future__ import annotations

import argparse
from pathlib import Path


HEADER = bytes.fromhex("00ffffffffffff00")

# 51.20 MHz, 1024 1072 1168 1344, 600 611 621 635, -HSync +VSync (60.02 Hz)
DTD_1024X600 = bytes.fromhex(
    "0014"  # pixel clock in 10 kHz units (5120)
    "004041"  # horizontal active/blanking: 1024/320
    "582320"  # vertical active/blanking: 600/35
    "3060ba00"  # sync offsets and widths: 48/96, 11/10
    "ff9600"  # physical image size: 255 x 150 mm
    "0000"  # borders
    "1c"  # digital separate sync, -HSync +VSync
)


def fallback_edid() -> bytearray:
    edid = bytearray(128)
    edid[:8] = HEADER
    edid[8:18] = bytes.fromhex("0d0e0100000000000124")  # CNC, product 1, 2026
    edid[18:25] = bytes((1, 3, 0x80, 26, 15, 120, 0x02))
    edid[38:54] = bytes((0x01, 0x01)) * 8
    edid[54:72] = DTD_1024X600
    edid[72:90] = bytes.fromhex("000000fc00434e432044415348424f41520a")
    edid[90:108] = bytes.fromhex("000000fd00323e1e510e000a202020202020")
    edid[108:126] = bytes.fromhex("000000ff00434e4331303234583630300a20")
    edid[126] = 0
    return edid


def load_source(path: Path | None) -> bytearray:
    if path is None or not path.exists():
        return fallback_edid()
    data = bytearray(path.read_bytes())
    if len(data) < 128 or data[:8] != HEADER or len(data) % 128:
        raise ValueError(f"{path} enthält keine gültige EDID-Blockstruktur")
    return data


def patch_edid(data: bytearray) -> bytearray:
    data[54:72] = DTD_1024X600
    # Preserve extension blocks and their checksums. Only the base block changed.
    data[127] = (-sum(data[:127])) & 0xFF
    expected_size = (data[126] + 1) * 128
    if len(data) != expected_size:
        raise ValueError(
            f"EDID hat {len(data)} Byte, deklariert aber {expected_size} Byte"
        )
    if any(sum(data[offset : offset + 128]) & 0xFF for offset in range(0, len(data), 128)):
        raise ValueError("Mindestens ein EDID-Block hat eine ungültige Prüfsumme")
    return data


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    parser.add_argument("source", nargs="?", type=Path)
    args = parser.parse_args()
    result = patch_edid(load_source(args.source))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(result)


if __name__ == "__main__":
    main()
