#!/usr/bin/python3 -I
# SPDX-License-Identifier: MIT
"""sveglio-watch: the battery guard of sveglio.

It runs inside `systemd-inhibit` (see sveglio.service): as long as this process is alive,
logind ignores the lid switch. Every 30 seconds it checks the battery. When the laptop runs
on battery and the charge drops to the threshold, it exits, so the inhibitor lock goes away
and the laptop behaves normally again. If the lid is closed it also suspends right away, so
running work is not lost to an empty battery.

The threshold is SVEGLIO_BATTERY_THRESHOLD (percent, default 15; 0 disables the guard).
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from typing import NoReturn

POWER_SUPPLY = "/sys/class/power_supply"
CHECK_SECONDS = 30
DEFAULT_THRESHOLD = 15


def log(message: str) -> None:
    print(message, flush=True)  # stdout goes to the journal


def _read(directory: str, name: str) -> str | None:
    try:
        with open(os.path.join(directory, name)) as f:
            return f.read().strip()
    except OSError:
        return None


def _read_int(directory: str, name: str) -> int | None:
    try:
        return int(_read(directory, name) or "")
    except ValueError:
        return None


def _charge(batteries: list[str]) -> float | None:
    if len(batteries) == 1:
        capacity = _read_int(batteries[0], "capacity")
        if capacity is not None:
            return float(capacity)
    for now_name, full_name in (("energy_now", "energy_full"), ("charge_now", "charge_full")):
        pairs = [(_read_int(b, now_name), _read_int(b, full_name)) for b in batteries]
        if all(now is not None and full for now, full in pairs):
            return 100 * sum(now for now, _ in pairs) / sum(full for _, full in pairs)
    capacities = [c for c in (_read_int(b, "capacity") for b in batteries) if c is not None]
    return sum(capacities) / len(capacities) if capacities else None


def battery_state(root: str = POWER_SUPPLY) -> tuple[float, bool] | None:
    """Return (charge in percent, running on battery) for the laptop's own batteries, or
    None if it has none. Batteries of peripherals such as mice and headphones (scope
    "Device") are ignored; several laptop batteries are combined."""
    try:
        entries = sorted(os.listdir(root))
    except OSError:
        return None
    batteries, mains_online = [], False
    for entry in entries:
        path = os.path.join(root, entry)
        kind = _read(path, "type")
        if kind == "Mains" and _read(path, "online") == "1":
            mains_online = True
        elif (
            kind == "Battery" and _read(path, "scope") != "Device" and _read(path, "present") != "0"
        ):
            batteries.append(path)
    charge = _charge(batteries) if batteries else None
    if charge is None:
        return None
    discharging = any(_read(b, "status") == "Discharging" for b in batteries)
    return charge, discharging and not mains_online


def lid_closed() -> bool:
    """Ask logind whether the lid is closed."""
    command = [
        "busctl",
        "get-property",
        "org.freedesktop.login1",
        "/org/freedesktop/login1",
        "org.freedesktop.login1.Manager",
        "LidClosed",
    ]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=10, check=False)
    except (OSError, subprocess.SubprocessError):
        return False
    return result.stdout.strip() == "b true"


def threshold() -> int:
    raw = os.environ.get("SVEGLIO_BATTERY_THRESHOLD", str(DEFAULT_THRESHOLD))
    try:
        value = int(raw)
    except ValueError:
        log(f"invalid SVEGLIO_BATTERY_THRESHOLD={raw!r}, using {DEFAULT_THRESHOLD}")
        return DEFAULT_THRESHOLD
    return max(0, min(100, value))


def wait_forever() -> NoReturn:
    while True:
        signal.pause()  # until systemd stops the service


def main() -> int:
    limit = threshold()
    if limit == 0:
        log("on, battery guard disabled")
        wait_forever()
    log(f"on: at {limit}% on battery sveglio turns itself off and the laptop suspends")
    while True:
        state = battery_state()
        if state is None:
            log("no laptop battery found, battery guard disabled")
            wait_forever()
        charge, on_battery = state
        if on_battery and charge <= limit:
            log(f"battery at {charge:.0f}%: turning sveglio off")
            if lid_closed():
                log("the lid is closed: suspending")
                subprocess.run(["systemctl", "suspend"], check=False)
            return 0
        time.sleep(CHECK_SECONDS)


if __name__ == "__main__":
    sys.exit(main())
