# sveglio

[![CI](https://github.com/Beccio00/sveglio/actions/workflows/ci.yml/badge.svg)](https://github.com/Beccio00/sveglio/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

**Close the lid, keep working.** sveglio keeps a Linux laptop running with the lid closed,
and makes it safe to carry around while it does.

*sveglio* is Italian for "awake" (say *ZVEL-yo*).

Long builds, big downloads, a fleet of AI coding agents: close the lid, put the laptop in
your bag, and they keep going. While the lid is closed and sveglio is on:

- the laptop **does not suspend**;
- the session is **locked** and the built-in **screen is off**;
- the built-in **keyboard, touchpad and touchscreen are disabled**, so nothing gets pressed
  by accident in your bag;
- if the battery runs low, it **suspends anyway**, before your work is lost.

Turn it off and the lid works as usual again.

## Usage

```console
$ sveglio on
sveglio: ON since Fri 2026-11-20 18:04:12 CET
  lid closed -> the laptop stays awake and the session is locked
  on battery at 15% -> sveglio turns itself off and the laptop suspends
lid-guard: running (built-in screen and input devices are off while the lid is closed)

$ sveglio off
sveglio: off (closing the lid suspends the laptop as usual)
lid-guard: running (built-in screen and input devices are off while the lid is closed)
```

`sveglio` or `sveglio status` shows the current state. After a reboot sveglio is always off.

## How it works

sveglio has two parts:

| Part | Runs as | What it does |
|---|---|---|
| `sveglio` and `sveglio.service` | your user | `sveglio on` starts a user service that takes a systemd [inhibitor lock](https://systemd.io/INHIBITOR_LOCKS/) on `handle-lid-switch`: while the lock is held, logind ignores the lid. Inside the lock runs `sveglio-watch`, the battery guard. `sveglio off` stops the service, and the lock goes away with it. |
| `lid-guard` | root, always running | Watches the lid switch. When the lid closes, it turns off the backlight of the built-in screen, takes an exclusive grab (`EVIOCGRAB`) of the built-in input devices and, if sveglio is on, locks the session. When the lid opens, it releases everything. |

**Why not `HandleLidSwitch=ignore` in `logind.conf`?** That setting is permanent, needs
root, and applying it means restarting logind. An inhibitor lock is per user, instant, and
cannot be left behind by mistake: it disappears with the process that holds it.

**Why does lid-guard need root?** Only root can open `/dev/input/event*` (your desktop gets
its devices from logind). That is also why lid-guard is small, sandboxed by systemd, and
never looks at what is typed: the events of grabbed devices are discarded unread.

Only the lid is inhibited: suspending from the menu, and the critical-battery action of your
desktop, keep working.

## Compatibility

sveglio needs **systemd** (logind, user services, `systemd-inhibit`) and **Python 3.10+**,
and works where **logind handles the lid**.

| Setup | Status |
|---|---|
| Pop!_OS 24.04, COSMIC, ASUS ExpertBook Ultra (B9406CAA) | ✅ tested |
| GNOME, sway, Hyprland, i3 and other desktops that leave the lid to logind | should work: [tell us](https://github.com/Beccio00/sveglio/issues/new?template=compatibility_report.yml)! |
| KDE Plasma | ❌ not yet: Plasma's power management (PowerDevil) handles the lid itself |
| XFCE | ❓ untested: xfce4-power-manager can handle the lid itself |
| Distributions without systemd | ❌ not supported |

The session lock needs a screen locker that listens to logind's `Lock` signal. GNOME, KDE
and COSMIC do; on sway or Hyprland, set one up (e.g. `swayidle lock swaylock`, or
`lock_cmd` in hypridle).

Every laptop is a little different. If you try sveglio, a
[compatibility report](https://github.com/Beccio00/sveglio/issues/new?template=compatibility_report.yml)
helps a lot, whether it works or not.

## Install

```sh
git clone https://github.com/Beccio00/sveglio.git
cd sveglio
./install.sh
```

The script asks for `sudo`, installs under `/usr/local` (`PREFIX=/usr ./install.sh` for
`/usr`), enables `lid-guard` and prints the status:

| File | Installed to |
|---|---|
| `sveglio` | `/usr/local/bin/` |
| `sveglio-watch` | `/usr/local/libexec/sveglio/` |
| `lid-guard` | `/usr/local/sbin/` |
| `sveglio.service` (user unit) | `/usr/local/lib/systemd/user/` |
| `lid-guard.service` | `/usr/local/lib/systemd/system/` |
| configuration | `/etc/sveglio/lid-guard.conf` |

To upgrade, pull and run `./install.sh` again: your configuration is kept.

### Try it

1. Run `sveglio on`, then `systemd-inhibit --list`: there should be a `sveglio` line with
   `handle-lid-switch`.
2. In another terminal, follow lid-guard's log: `journalctl -u lid-guard -f`.
3. Close the lid for a minute, then open it. The log lists the devices that were blocked,
   and the lock screen greets you with everything still running.
4. Run `sveglio off` and close the lid: the laptop suspends as usual.

## What gets blocked

`lid-guard --list` (no root needed) shows what happens on your laptop. On the tested ASUS:

```console
$ lid-guard --list
Lid switch: Lid Switch (/dev/input/event0)

  -    Lid Switch                            lid switch                /dev/input/event0
  -    Power Button                          power/sleep button        /dev/input/event1
BLOCK  AT Translated Set 2 keyboard          built-in (i8042)          /dev/input/event2
BLOCK  ILIT2901:00 222A:5584                 built-in (i2c)            /dev/input/event3
BLOCK  ASCP1D80:00 093A:4F05 Mouse           built-in (i2c)            /dev/input/event4
BLOCK  ASCP1D80:00 093A:4F05 Touchpad        built-in (i2c)            /dev/input/event5
BLOCK  Video Bus                             built-in (host)           /dev/input/event10
BLOCK  Intel HID events                      built-in (host)           /dev/input/event11
BLOCK  Intel HID 5 button array              built-in (host)           /dev/input/event12
BLOCK  Asus WMI hotkeys                      built-in (host)           /dev/input/event13
  -    sof-soundwire Jack                    not built-in (none)       /dev/input/event14
  -    sof-soundwire HDMI/DP,pcm=5           no keys or pointer        /dev/input/event15
```

The rules, checked in this order:

1. The **lid switch** is never blocked.
2. Devices matching `exclude` in the configuration are not blocked; devices matching
   `include` are.
3. Devices with no keys and no pointer (audio jacks, HDMI) are not blocked.
4. Dedicated **power and sleep buttons** are not blocked.
5. **Virtual** devices (key remappers, Bluetooth media controls) are not blocked.
6. Devices on a **built-in bus** (PS/2, I2C, SPI, RMI, platform) are blocked: keyboard,
   touchpad, touchscreen, pointing stick, Fn keys and hotkeys. USB and Bluetooth devices are
   not, so an external keyboard and mouse keep working with the lid closed.

Nothing is blocked in tablet mode, because some convertibles report the lid as closed when
folded.

## Configuration

**Battery threshold** (default 15%, `0` turns the battery guard off):

```sh
systemctl --user edit sveglio
```

```ini
[Service]
Environment=SVEGLIO_BATTERY_THRESHOLD=25
```

**Devices and screen:** edit `/etc/sveglio/lid-guard.conf`, check the result with
`lid-guard --list`, then apply it with `sudo systemctl restart lid-guard`.

```ini
[devices]
# Built-in keyboards that show up as USB devices, as on some ASUS ROG laptops
include =
    ASUSTeK Computer Inc. N-KEY Device
exclude =

[screen]
# Turn off the backlight of the built-in screen while the lid is closed
backlight = yes
```

## Good to know

- **Heat.** A laptop working inside a closed bag gets hot. Light work is fine; for heavy
  builds, leave it some air. The CPU slows down when it is too hot and, at worst, the
  firmware shuts the laptop down.
- **Network.** Your jobs keep running, but if you leave your Wi-Fi they lose the connection.
  Use a hotspot if they need the internet.
- **Power button.** Dedicated power buttons always work. On some laptops, though, the power
  button shares a device with other hotkeys (e.g. *Intel HID events*) and is blocked while
  the lid is closed. Holding it down for a few seconds forces a power-off on almost every
  laptop, at firmware level.
- **Escape hatch.** `sudo systemctl stop lid-guard` releases every device at once. A crash
  releases them too, because the grab belongs to the process.
- **Remote control.** `sveglio on` also works over SSH, as long as you are logged in on the
  laptop. Tools that run commands in a sandbox may not reach the systemd user bus
  (`Failed to connect to bus`): run `sveglio` outside the sandbox.

## Uninstall

```sh
./uninstall.sh            # keeps your configuration in /etc/sveglio
./uninstall.sh --purge    # removes it too
```

## Contributing

Bug reports, compatibility reports and pull requests are welcome: see
[CONTRIBUTING.md](CONTRIBUTING.md). Please follow the [Code of Conduct](CODE_OF_CONDUCT.md),
and report security problems privately as described in [SECURITY.md](SECURITY.md).

## License

[MIT](LICENSE) © 2026 Riccardo Becciolini
