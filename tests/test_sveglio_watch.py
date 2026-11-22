# SPDX-License-Identifier: MIT
from pathlib import Path

import pytest

import sveglio_watch as sw

# A wireless mouse's battery, as exposed by e.g. the hid-logitech-hidpp driver.
MOUSE = {"type": "Battery", "scope": "Device", "status": "Discharging", "capacity": 5}


def supply(root: Path, name: str, **attributes: object) -> None:
    """Create a fake /sys/class/power_supply/<name> directory."""
    directory = root / name
    directory.mkdir()
    for attribute, value in attributes.items():
        (directory / attribute).write_text(f"{value}\n")


def test_on_battery(tmp_path: Path) -> None:
    supply(tmp_path, "AC0", type="Mains", online=0)
    supply(tmp_path, "BAT0", type="Battery", status="Discharging", capacity=42)
    assert sw.battery_state(str(tmp_path)) == (42.0, True)


def test_plugged_in(tmp_path: Path) -> None:
    supply(tmp_path, "AC0", type="Mains", online=1)
    supply(tmp_path, "BAT0", type="Battery", status="Charging", capacity=80)
    assert sw.battery_state(str(tmp_path)) == (80.0, False)


def test_plugged_in_but_draining(tmp_path: Path) -> None:
    # a weak charger can leave the battery "Discharging": still plugged in, not on battery
    supply(tmp_path, "AC0", type="Mains", online=1)
    supply(tmp_path, "BAT0", type="Battery", status="Discharging", capacity=30)
    assert sw.battery_state(str(tmp_path)) == (30.0, False)


def test_peripheral_batteries_are_ignored(tmp_path: Path) -> None:
    supply(tmp_path, "BAT0", type="Battery", status="Full", capacity=100)
    supply(tmp_path, "hidpp_battery_0", **MOUSE)
    assert sw.battery_state(str(tmp_path)) == (100.0, False)


def test_no_laptop_battery(tmp_path: Path) -> None:
    supply(tmp_path, "hidpp_battery_0", **MOUSE)
    assert sw.battery_state(str(tmp_path)) is None


def test_two_batteries_are_combined_by_energy(tmp_path: Path) -> None:
    supply(tmp_path, "BAT0", type="Battery", status="Discharging", energy_now=10, energy_full=50)
    supply(tmp_path, "BAT1", type="Battery", status="Unknown", energy_now=40, energy_full=50)
    assert sw.battery_state(str(tmp_path)) == (50.0, True)


def test_missing_power_supply_directory(tmp_path: Path) -> None:
    assert sw.battery_state(str(tmp_path / "missing")) is None


@pytest.mark.parametrize(
    ("raw", "expected"),
    [(None, 15), ("20", 20), ("0", 0), ("150", 100), ("-5", 0), ("abc", 15)],
)
def test_threshold(monkeypatch: pytest.MonkeyPatch, raw: str | None, expected: int) -> None:
    if raw is None:
        monkeypatch.delenv("SVEGLIO_BATTERY_THRESHOLD", raising=False)
    else:
        monkeypatch.setenv("SVEGLIO_BATTERY_THRESHOLD", raw)
    assert sw.threshold() == expected
