# SPDX-License-Identifier: MIT
from pathlib import Path

import pytest

import lid_guard as lg

FIXTURES = Path(__file__).parent / "fixtures"
LAPTOP = FIXTURES / "asus-expertbook-ultra-b9406caa.txt"
EXTRA = FIXTURES / "external-and-virtual.txt"


def devices(path: Path) -> dict[str, lg.Device]:
    return {dev.name: dev for dev in lg.parse_devices(path.read_text(), long_bits=64)}


def test_parse_bitmap() -> None:
    assert lg.parse_bitmap("8000 10000000000000 0", long_bits=64) == {116, 143}
    assert lg.parse_bitmap("1 0", long_bits=32) == {32}
    assert lg.parse_bitmap("0") == set()


def test_parse_devices() -> None:
    keyboard = devices(LAPTOP)["AT Translated Set 2 keyboard"]
    assert keyboard.bus == 0x11
    assert keyboard.nodes == ["/dev/input/event2"]
    assert keyboard.sysfs == "/devices/platform/i8042/serio0/input/input2"
    assert 30 in keyboard.caps["KEY"]  # KEY_A


def test_find_lid() -> None:
    lid = lg.find_lid(list(devices(LAPTOP).values()))
    assert lid is not None
    assert (lid.name, lid.nodes) == ("Lid Switch", ["/dev/input/event0"])


def test_real_laptop_blocks_only_builtin_input() -> None:
    blocked = {name for name, dev in devices(LAPTOP).items() if lg.classify(dev, lg.Config())[0]}
    assert blocked == {
        "AT Translated Set 2 keyboard",
        "ILIT2901:00 222A:5584",  # touchscreen
        "ASCP1D80:00 093A:4F05 Mouse",  # touchpad, mouse node
        "ASCP1D80:00 093A:4F05 Touchpad",
        "Video Bus",  # brightness keys
        "Intel HID events",
        "Intel HID 5 button array",
        "Asus WMI hotkeys",  # Fn keys, including airplane mode
    }


@pytest.mark.parametrize(
    ("fixture", "name", "expected"),
    [
        (LAPTOP, "Lid Switch", (False, "lid switch")),
        (LAPTOP, "Power Button", (False, "power/sleep button")),
        (LAPTOP, "sof-soundwire Jack", (False, "not built-in (none)")),
        (LAPTOP, "sof-soundwire HDMI/DP,pcm=5", (False, "no keys or pointer")),
        (LAPTOP, "Example Headphones (AVRCP)", (False, "virtual device")),
        (LAPTOP, "AT Translated Set 2 keyboard", (True, "built-in (i8042)")),
        (LAPTOP, "ASCP1D80:00 093A:4F05 Touchpad", (True, "built-in (i2c)")),
        (EXTRA, "Logitech USB Keyboard", (False, "not built-in (usb)")),
        (EXTRA, "TPPS/2 Elan TrackPoint", (True, "built-in (i8042)")),
        (EXTRA, "Sleep Button", (False, "power/sleep button")),
        (EXTRA, "Intel HID switches", (False, "no keys or pointer")),
        (EXTRA, "Example uinput virtual keyboard", (False, "virtual device")),
    ],
)
def test_classify(fixture: Path, name: str, expected: tuple[bool, str]) -> None:
    assert lg.classify(devices(fixture)[name], lg.Config()) == expected


def test_include_and_exclude() -> None:
    extra = devices(EXTRA)
    cfg = lg.Config(include=["Logitech"], exclude=["TrackPoint"])
    assert lg.classify(extra["Logitech USB Keyboard"], cfg) == (True, "included in config")
    assert lg.classify(extra["TPPS/2 Elan TrackPoint"], cfg) == (False, "excluded in config")


def test_exclude_wins_over_include() -> None:
    cfg = lg.Config(include=["Logitech"], exclude=["Logitech"])
    assert not lg.classify(devices(EXTRA)["Logitech USB Keyboard"], cfg)[0]


def test_lid_switch_is_never_blocked() -> None:
    cfg = lg.Config(include=["Lid"])
    assert lg.classify(devices(LAPTOP)["Lid Switch"], cfg) == (False, "lid switch")


def test_load_config(tmp_path: Path) -> None:
    path = tmp_path / "lid-guard.conf"
    path.write_text(
        "[devices]\n"
        "include =\n"
        "    Foo Keyboard\n"
        "    # a comment\n"
        "    Bar\n"
        "exclude = Baz\n"
        "[screen]\n"
        "backlight = no\n"
    )
    assert lg.load_config(str(path)) == lg.Config(
        include=["Foo Keyboard", "Bar"], exclude=["Baz"], backlight=False
    )


def test_missing_config_means_defaults(tmp_path: Path) -> None:
    assert lg.load_config(str(tmp_path / "missing.conf")) == lg.Config()


def test_shipped_config_is_the_default() -> None:
    shipped = Path(__file__).parent.parent / "config" / "lid-guard.conf"
    assert lg.load_config(str(shipped)) == lg.Config()


def test_list(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    args = ["--list", "--devices", str(LAPTOP), "--config", str(tmp_path / "none.conf")]
    assert lg.main(args) == 0
    out = capsys.readouterr().out
    assert "Lid switch: Lid Switch (/dev/input/event0)" in out
    assert "BLOCK  AT Translated Set 2 keyboard" in out


def test_list_without_devices_file(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    args = ["--list", "--devices", str(tmp_path / "missing"), "--config", "/nonexistent"]
    assert lg.main(args) == 1
    assert "cannot read" in capsys.readouterr().err


def test_invalid_config(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    path = tmp_path / "broken.conf"
    path.write_text("this is not an ini file\n")
    assert lg.main(["--list", "--config", str(path)]) == 2
    assert "invalid configuration" in capsys.readouterr().err
