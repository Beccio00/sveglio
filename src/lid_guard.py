#!/usr/bin/python3 -I
# SPDX-License-Identifier: MIT
"""lid-guard: turn off a laptop's built-in screen and input devices while the lid is closed.

While the lid is closed, lid-guard:

* turns off the backlight of the built-in screen;
* grabs the built-in keyboard, touchpad, touchscreen and hotkeys, so keys pressed by
  accident (in a bag, say) never reach the system;
* locks all sessions, if sveglio is keeping the laptop awake.

When the lid opens, everything is released (the session stays locked).

How the grab works: the EVIOCGRAB ioctl makes this process the *only* receiver of the
events of a /dev/input/eventN device, so the compositor, the console and the kernel's own
handlers (e.g. rfkill for the airplane-mode key) see nothing. The grab belongs to the file
descriptor: if lid-guard dies, the kernel drops it, so a crash can never leave the keyboard
dead.

lid-guard never grabs the lid switch (logind and the desktop need it) and never looks at
what is typed: the events of grabbed devices are discarded without being inspected.

Run `lid-guard --list` (no root needed) to see which devices would be blocked.
"""

from __future__ import annotations

import argparse
import configparser
import contextlib
import fcntl
import glob
import os
import select
import signal
import struct
import subprocess
import sys
from dataclasses import dataclass, field

__version__ = "0.1.0"

DEVICES_FILE = "/proc/bus/input/devices"
CONFIG_FILE = "/etc/sveglio/lid-guard.conf"
RECHECK_SECONDS = 5  # safety net: re-check the lid even if no event arrives
INHIBITOR_WHO = "sveglio"  # the --who= of the inhibitor lock taken by sveglio.service

# <linux/input-event-codes.h>
SW_LID = 0x00
SW_TABLET_MODE = 0x01
POWER_KEYS = frozenset({116, 142, 143, 205, 356})  # POWER, SLEEP, WAKEUP, SUSPEND, POWER2

# <linux/input.h>
BUS_NAMES = {
    0x00: "none",
    0x03: "usb",
    0x05: "bluetooth",
    0x06: "virtual",
    0x11: "i8042",
    0x18: "i2c",
    0x19: "host",
    0x1C: "spi",
    0x1D: "rmi",
}
BUILTIN_BUSES = frozenset({0x11, 0x18, 0x19, 0x1C, 0x1D})  # i8042, I2C, platform, SPI, RMI
EVIOCGRAB = 0x40044590  # _IOW('E', 0x90, int): take or drop an exclusive grab
EVIOCGSW = 0x8008451B  # _IOC(_IOC_READ, 'E', 0x1b, 8): read the current switch states

LONG_BITS = struct.calcsize("l") * 8  # /proc prints capability bitmaps as C longs
OPEN_FLAGS = os.O_RDONLY | os.O_NONBLOCK | os.O_CLOEXEC


def log(message: str) -> None:
    print(message, flush=True)  # stdout goes to the journal


# --- Input devices -----------------------------------------------------------------------


@dataclass
class Device:
    """One entry of /proc/bus/input/devices."""

    name: str = ""
    bus: int = 0
    sysfs: str = ""
    nodes: list[str] = field(default_factory=list)  # /dev/input/eventN
    caps: dict[str, set[int]] = field(default_factory=dict)  # e.g. "KEY" -> key codes

    def has(self, kind: str, code: int | None = None) -> bool:
        codes = self.caps.get(kind, set())
        return bool(codes) if code is None else code in codes

    @property
    def bus_name(self) -> str:
        return BUS_NAMES.get(self.bus, f"bus 0x{self.bus:02x}")


def parse_bitmap(text: str, long_bits: int = LONG_BITS) -> set[int]:
    """Decode a capability bitmap such as the "8000 10000000000000 0" of "B: KEY=...".

    The kernel prints one hex word per C long, most significant word first.
    """
    codes = set()
    for index, word in enumerate(reversed(text.split())):
        value = int(word, 16)
        codes.update(index * long_bits + bit for bit in range(long_bits) if (value >> bit) & 1)
    return codes


def parse_devices(text: str, long_bits: int = LONG_BITS) -> list[Device]:
    """Parse the contents of /proc/bus/input/devices."""
    devices = []
    for block in text.strip().split("\n\n"):
        dev = Device()
        for line in block.splitlines():
            tag, _, value = line.partition(": ")
            if tag == "I":
                ids = dict(item.split("=", 1) for item in value.split() if "=" in item)
                dev.bus = int(ids.get("Bus", "0"), 16)
            elif tag == "N":
                dev.name = value.removeprefix("Name=").strip('"')
            elif tag == "S":
                dev.sysfs = value.removeprefix("Sysfs=")
            elif tag == "H":
                handlers = value.removeprefix("Handlers=").split()
                dev.nodes = ["/dev/input/" + h for h in handlers if h.startswith("event")]
            elif tag == "B":
                kind, _, bitmap = value.partition("=")
                dev.caps[kind] = parse_bitmap(bitmap, long_bits)
        if dev.nodes:
            devices.append(dev)
    return devices


def read_devices(path: str = DEVICES_FILE) -> list[Device]:
    with open(path) as f:
        return parse_devices(f.read())


def find_lid(devices: list[Device]) -> Device | None:
    return next((dev for dev in devices if dev.has("SW", SW_LID)), None)


# --- Policy ------------------------------------------------------------------------------


@dataclass
class Config:
    include: list[str] = field(default_factory=list)
    exclude: list[str] = field(default_factory=list)
    backlight: bool = True


def load_config(path: str = CONFIG_FILE) -> Config:
    """Read the configuration file. A missing file means the defaults."""
    parser = configparser.ConfigParser()
    if not parser.read(path):
        return Config()

    def names(option: str) -> list[str]:
        value = parser.get("devices", option, fallback="")
        return [line.strip() for line in value.splitlines() if line.strip()]

    return Config(
        include=names("include"),
        exclude=names("exclude"),
        backlight=parser.getboolean("screen", "backlight", fallback=True),
    )


def classify(dev: Device, cfg: Config) -> tuple[bool, str]:
    """Return whether `dev` is blocked while the lid is closed, and why.

    When in doubt, a device is *not* blocked: a working keyboard is always better than a
    dead one.
    """
    if dev.has("SW", SW_LID):
        return False, "lid switch"
    if any(text in dev.name for text in cfg.exclude):
        return False, "excluded in config"
    if any(text in dev.name for text in cfg.include):
        return True, "included in config"
    pointer = dev.has("REL") or dev.has("ABS")
    if not (dev.has("KEY") or pointer):
        return False, "no keys or pointer"
    if not pointer and dev.caps["KEY"] <= POWER_KEYS:
        return False, "power/sleep button"
    if dev.sysfs.startswith("/devices/virtual/"):
        return False, "virtual device"
    if dev.bus not in BUILTIN_BUSES:
        return False, f"not built-in ({dev.bus_name})"
    return True, f"built-in ({dev.bus_name})"


# --- Hardware ----------------------------------------------------------------------------


def switch_on(fd: int, code: int) -> bool:
    """Ask the kernel for the current state of switch `code` (e.g. SW_LID)."""
    state = bytearray(8)
    fcntl.ioctl(fd, EVIOCGSW, state)
    return bool((state[code // 8] >> (code % 8)) & 1)


def in_tablet_mode(devices: list[Device]) -> bool:
    """Some convertibles report the lid as closed when folded into a tablet: nothing is
    blocked in tablet mode."""
    for dev in devices:
        if not dev.has("SW", SW_TABLET_MODE):
            continue
        try:
            fd = os.open(dev.nodes[0], OPEN_FLAGS)
        except OSError:
            continue
        try:
            if switch_on(fd, SW_TABLET_MODE):
                return True
        except OSError:
            pass
        finally:
            os.close(fd)
    return False


def set_backlight(on: bool) -> None:
    """Turn the backlight of the built-in screen on or off through bl_power
    (0 = on, 4 = FB_BLANK_POWERDOWN). The brightness level is left alone."""
    for path in glob.glob("/sys/class/backlight/*/bl_power"):
        if os.path.basename(os.path.dirname(path)).startswith("ddcci"):
            continue  # an external monitor controlled over DDC/CI, not the built-in screen
        try:
            with open(path, "w") as f:
                f.write("0" if on else "4")
        except OSError as e:
            log(f"cannot write {path}: {e.strerror}")


def sveglio_active() -> bool:
    """True if sveglio holds its handle-lid-switch inhibitor lock."""
    command = ["systemd-inhibit", "--list", "--no-pager", "--no-legend"]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=5, check=False)
    except (OSError, subprocess.SubprocessError) as e:
        log(f"cannot list inhibitor locks: {e}")
        return False
    return any(
        line.split()[:1] == [INHIBITOR_WHO] and "handle-lid-switch" in line
        for line in result.stdout.splitlines()
    )


def lock_sessions() -> None:
    try:
        result = subprocess.run(
            ["loginctl", "lock-sessions"], capture_output=True, text=True, timeout=5, check=False
        )
    except (OSError, subprocess.SubprocessError) as e:
        log(f"  cannot lock sessions: {e}")
        return
    if result.returncode == 0:
        log("  sessions locked")
    else:
        log(f"  cannot lock sessions: {result.stderr.strip()}")


class Guard:
    """Holds the exclusive grabs on the blocked devices."""

    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg
        self.grabbed: dict[int, str] = {}  # fd -> /dev/input/eventN
        self.failed: set[str] = set()  # nodes that could not be grabbed (logged once)

    def grab(self, devices: list[Device]) -> None:
        """Grab every device that should be blocked. Safe to call repeatedly: it only picks
        up devices that are not grabbed yet, such as ones re-created after a suspend."""
        taken = set(self.grabbed.values()) | self.failed
        for dev in devices:
            if not classify(dev, self.cfg)[0]:
                continue
            for node in dev.nodes:
                if node not in taken:
                    self._grab(dev, node)

    def _grab(self, dev: Device, node: str) -> None:
        try:
            fd = os.open(node, OPEN_FLAGS)
        except OSError as e:
            self._failed(dev, node, e)
            return
        try:
            fcntl.ioctl(fd, EVIOCGRAB, 1)
        except OSError as e:  # EBUSY: another program (e.g. a key remapper) grabbed it first
            os.close(fd)
            self._failed(dev, node, e)
            return
        self.grabbed[fd] = node
        log(f"  blocked {dev.name} ({node})")

    def _failed(self, dev: Device, node: str, error: OSError) -> None:
        self.failed.add(node)
        log(f"  cannot block {dev.name} ({node}): {error.strerror}")

    def release(self, fd: int) -> None:
        self.grabbed.pop(fd, None)
        with contextlib.suppress(OSError):
            os.close(fd)  # closing the descriptor drops the grab

    def release_all(self) -> None:
        for fd in list(self.grabbed):
            self.release(fd)
        self.failed.clear()


# --- Main loop ---------------------------------------------------------------------------


def run(cfg: Config) -> int:
    lid = find_lid(read_devices())
    if lid is None:
        log("no lid switch found, nothing to do")
        return 0
    lid_fd = os.open(lid.nodes[0], OPEN_FLAGS)
    guard = Guard(cfg)
    was_closed: bool | None = None
    log(f"lid-guard {__version__}: watching {lid.name} ({lid.nodes[0]})")
    try:
        while True:
            closed = switch_on(lid_fd, SW_LID)
            devices = read_devices() if closed else []
            if closed and in_tablet_mode(devices):
                closed = False

            if closed and was_closed is not True:
                log("lid closed")
                if cfg.backlight:
                    set_backlight(False)
                guard.grab(devices)
                if sveglio_active():
                    lock_sessions()
            elif not closed and was_closed is not False:
                if was_closed:
                    log("lid open: built-in devices released")
                guard.release_all()
                if cfg.backlight:
                    set_backlight(True)
            was_closed = closed

            if closed:
                guard.grab(devices)  # picks up devices that (re)appeared meanwhile
            ready, _, _ = select.select([lid_fd, *guard.grabbed], [], [], RECHECK_SECONDS)
            for fd in ready:
                try:
                    os.read(fd, 4096)  # drain and discard: events are never inspected
                except BlockingIOError:
                    pass
                except OSError:
                    if fd == lid_fd:
                        raise
                    guard.release(fd)  # the device vanished; grabbed again on the next pass
    finally:
        guard.release_all()
        if cfg.backlight:
            set_backlight(True)


def list_devices(cfg: Config, devices_file: str) -> int:
    try:
        devices = read_devices(devices_file)
    except OSError as e:
        print(f"lid-guard: cannot read {devices_file}: {e.strerror}", file=sys.stderr)
        return 1
    lid = find_lid(devices)
    print(f"Lid switch: {lid.name} ({lid.nodes[0]})" if lid else "Lid switch: not found")
    print()
    for dev in devices:
        blocked, reason = classify(dev, cfg)
        mark = "BLOCK" if blocked else "  -  "
        print(f"{mark}  {dev.name:<36}  {reason:<24}  {' '.join(dev.nodes)}")
    return 0


def _terminate(signum: int, frame: object) -> None:
    raise SystemExit(0)  # unwinds through run()'s finally, which releases everything


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="lid-guard",
        description="Turn off the built-in screen and input devices while the lid is closed.",
    )
    parser.add_argument(
        "--list", action="store_true", help="show which devices are blocked, then exit"
    )
    parser.add_argument(
        "--config", default=CONFIG_FILE, help=f"configuration file (default: {CONFIG_FILE})"
    )
    parser.add_argument(
        "--devices",
        default=DEVICES_FILE,
        metavar="FILE",
        help=f"with --list: read the devices from FILE instead of {DEVICES_FILE}",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    args = parser.parse_args(argv)

    try:
        cfg = load_config(args.config)
    except configparser.Error as e:
        print(f"lid-guard: invalid configuration in {args.config}: {e}", file=sys.stderr)
        return 2
    if args.list:
        return list_devices(cfg, args.devices)
    if os.geteuid() != 0:
        print("lid-guard: the daemon must run as root (try --list)", file=sys.stderr)
        return 1
    signal.signal(signal.SIGTERM, _terminate)
    return run(cfg)


if __name__ == "__main__":
    sys.exit(main())
