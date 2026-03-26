#!/usr/bin/env python3
"""
Small development helper to list I2C bus addresses on a Raspberry Pi.

The script prefers the system tool `i2cdetect` because it is the most reliable
way to probe addresses on a Linux target that exposes `/dev/i2c-*`.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import re
import shutil
import subprocess
import sys


COMMON_I2CDETECT_PATHS = (
    "i2cdetect",
    "/usr/sbin/i2cdetect",
    "/usr/bin/i2cdetect",
)
BUS_PATTERN = re.compile(r"i2c-(\d+)$")
ROW_PATTERN = re.compile(r"^([0-7][0-9A-Fa-f]):(.*)$")


def resolve_i2cdetect():
    for candidate in COMMON_I2CDETECT_PATHS:
        if "/" in candidate:
            if os.path.exists(candidate):
                return candidate
            continue

        resolved = shutil.which(candidate)
        if resolved:
            return resolved
    return None


def discover_buses(explicit_buses):
    if explicit_buses:
        return sorted(set(int(bus) for bus in explicit_buses))

    discovered = []
    for path in glob.glob("/dev/i2c-*"):
        match = BUS_PATTERN.search(path)
        if match:
            discovered.append(int(match.group(1)))
    return sorted(set(discovered))


def get_bus_metadata(i2cdetect_command):
    completed = subprocess.run(
        [i2cdetect_command, "-l"],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        return {}

    metadata = {}
    for line in completed.stdout.splitlines():
        columns = [column.strip() for column in line.split("\t") if column.strip()]
        if len(columns) < 3:
            continue

        match = BUS_PATTERN.search(columns[0])
        if not match:
            continue

        metadata[int(match.group(1))] = {
            "kind": columns[1],
            "adapter": columns[2],
        }

    return metadata


def parse_i2cdetect_output(output):
    devices = []

    for line in output.splitlines():
        match = ROW_PATTERN.match(line)
        if not match:
            continue

        row_prefix, cells = match.groups()
        base_address = int(row_prefix, 16)
        padded_cells = cells[:48].ljust(48)

        for offset in range(16):
            token = padded_cells[offset * 3:(offset + 1) * 3].strip()
            if not token or token == "--":
                continue

            address = base_address + offset
            status = "claimed" if token == "UU" else "present"
            devices.append(
                {
                    "address": address,
                    "address_hex": f"0x{address:02x}",
                    "status": status,
                }
            )

    return devices


def scan_bus(i2cdetect_command, bus_number, metadata):
    command = [i2cdetect_command, "-y", str(bus_number)]
    completed = subprocess.run(command, capture_output=True, text=True, check=False)

    if completed.returncode != 0:
        return {
            "bus": bus_number,
            "path": f"/dev/i2c-{bus_number}",
            "kind": metadata.get("kind", "i2c"),
            "adapter": metadata.get("adapter", ""),
            "addresses": [],
            "error": (completed.stderr or completed.stdout).strip() or "i2cdetect failed",
            "raw_output": completed.stdout,
        }

    return {
        "bus": bus_number,
        "path": f"/dev/i2c-{bus_number}",
        "kind": metadata.get("kind", "i2c"),
        "adapter": metadata.get("adapter", ""),
        "addresses": parse_i2cdetect_output(completed.stdout),
        "raw_output": completed.stdout,
    }


def print_human_readable(results, show_raw):
    if not results:
        print("Keine I2C-Busse unter /dev/i2c-* gefunden.")
        return

    print(f"Gefundene I2C-Busse: {len(results)}")
    print("")

    for index, result in enumerate(results):
        print(f"Bus {result['bus']} ({result['path']})")
        if result.get("adapter"):
            print(f"  Adapter: {result['adapter']}")

        if result.get("error"):
            print(f"  Fehler: {result['error']}")
        else:
            addresses = result["addresses"]
            if addresses:
                labels = []
                for entry in addresses:
                    suffix = " (vom Kernel-Treiber belegt)" if entry["status"] == "claimed" else ""
                    labels.append(f"{entry['address_hex']}{suffix}")
                joined = ", ".join(labels)
                print(f"  Adresse(n) ({len(addresses)}): {joined}")
            else:
                print("  Keine Adresse erkannt.")

        if show_raw:
            print("  Rohdaten:")
            for raw_line in result.get("raw_output", "").splitlines():
                print(f"    {raw_line}")

        if index != len(results) - 1:
            print("")


def build_parser():
    parser = argparse.ArgumentParser(
        description="Scannt Raspberry-Pi-I2C-Busse und listet erkannte Adressen auf."
    )
    parser.add_argument(
        "--bus",
        dest="buses",
        action="append",
        type=int,
        help="Nur den angegebenen I2C-Bus scannen. Kann mehrfach verwendet werden.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Ergebnis als JSON ausgeben.",
    )
    parser.add_argument(
        "--show-raw",
        action="store_true",
        help="Zusatzlich die rohe i2cdetect-Ausgabe anzeigen.",
    )
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)

    buses = discover_buses(args.buses)
    if not buses:
        payload = {"buses": [], "message": "Keine I2C-Busse unter /dev/i2c-* gefunden."}
        if args.json:
            print(json.dumps(payload, indent=2))
        else:
            print(payload["message"])
        return 0

    i2cdetect_command = resolve_i2cdetect()
    if not i2cdetect_command:
        print(
            "i2cdetect wurde nicht gefunden. Bitte `i2c-tools` installieren oder den Pfad pruefen.",
            file=sys.stderr,
        )
        return 2

    bus_metadata = get_bus_metadata(i2cdetect_command)
    results = [
        scan_bus(i2cdetect_command, bus_number, bus_metadata.get(bus_number, {}))
        for bus_number in buses
    ]

    if args.json:
        print(json.dumps({"buses": results}, indent=2))
    else:
        print_human_readable(results, args.show_raw)

    return 1 if any(result.get("error") for result in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
