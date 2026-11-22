# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this
project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- `sveglio on | off | status`: keep the laptop awake with the lid closed, through a systemd
  inhibitor lock on `handle-lid-switch`.
- Battery guard: on battery at 15% (configurable), sveglio turns itself off and, if the lid
  is closed, suspends the laptop.
- `lid-guard` daemon: while the lid is closed, it turns off the backlight of the built-in
  screen, blocks the built-in keyboard, touchpad, touchscreen and hotkeys, and locks the
  session if sveglio is on.
- Automatic detection of built-in input devices, with `include` and `exclude` overrides in
  `/etc/sveglio/lid-guard.conf`.
- `lid-guard --list` shows which devices are blocked.

[Unreleased]: https://github.com/Beccio00/sveglio/commits/main
