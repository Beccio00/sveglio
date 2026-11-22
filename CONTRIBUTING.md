# Contributing to sveglio

Thanks for your interest! sveglio is a small project, and every kind of help counts.

## Ways to help

- **Compatibility reports.** The most useful contribution of all: tell us whether sveglio
  works on your laptop, distribution and desktop with the
  [compatibility report](https://github.com/Beccio00/sveglio/issues/new?template=compatibility_report.yml)
  form. A report that something does *not* work is just as valuable.
- **Bug reports and ideas**, through the issue forms.
- **Code and documentation**, through pull requests. For larger changes, please open an
  issue first, so we can agree on the approach before you spend time on it.

## Project layout

| Path | What it is |
|---|---|
| `src/sveglio` | the `sveglio` command (Bash) |
| `src/sveglio_watch.py` | the battery guard, runs inside the inhibitor lock (installed as `sveglio-watch`) |
| `src/lid_guard.py` | the root daemon: lid switch, input grabs, backlight, session lock (installed as `lid-guard`) |
| `systemd/` | unit files; `install.sh` fills in `@SBINDIR@` and `@LIBEXECDIR@` |
| `config/lid-guard.conf` | default configuration, installed to `/etc/sveglio/` |
| `tests/` | unit tests; `tests/fixtures/` holds real `/proc/bus/input/devices` dumps |

## Development setup

You need Python 3.10 or newer and, to test on real hardware, a laptop with systemd.

```sh
git clone https://github.com/<your-username>/sveglio.git
cd sveglio
python3 -m venv .venv
. .venv/bin/activate
pip install pytest ruff shellcheck-py
```

Before opening a pull request, run the same checks as CI:

```sh
pytest
ruff check .
ruff format --check .        # `ruff format .` fixes the formatting
shellcheck src/sveglio install.sh uninstall.sh
```

## Testing on real hardware

`lid-guard --list` checks device detection without root and without installing anything.
With `--devices` it reads any saved device list:

```sh
python3 src/lid_guard.py --list
python3 src/lid_guard.py --list --devices tests/fixtures/asus-expertbook-ultra-b9406caa.txt
```

To try a change for real, install it with `./install.sh` and follow the logs:

```sh
journalctl -u lid-guard -f           # lid-guard
journalctl --user -u sveglio -f      # sveglio and its battery guard
```

Keep a way back in while you experiment: a USB keyboard (never blocked by default) or an
SSH session. `sudo systemctl stop lid-guard` releases every device immediately.

## Adding your laptop as a test fixture

Real device lists make the best tests for device detection. To add yours:

1. Save it: `cat /proc/bus/input/devices > tests/fixtures/<vendor>-<model>.txt`
2. **Remove personal data:** Bluetooth device names (they often contain your name), MAC
   addresses in `P: Phys=` and anything after `U: Uniq=`.
3. Add a test to `tests/test_lid_guard.py` that lists the devices that must be blocked, like
   `test_real_laptop_blocks_only_builtin_input`.

## Design principles

1. **Never leave the user without input.** When the lid is open, nothing may stay blocked.
   When in doubt, don't block a device.
2. **lid-guard runs as root, so keep it small.** No dependencies beyond the Python standard
   library and systemd's own tools. Never read, log or store what is typed.
3. **Fail safe.** If something breaks, the laptop falls back to its normal behaviour: it
   suspends when the lid closes, and input works.
4. **No surprises.** Behaviour changes are documented in the README and in CHANGELOG.md.

## Style

- Python: formatted with `ruff format` and checked with `ruff check` (settings in
  `pyproject.toml`).
- Shell: `set -euo pipefail`, ShellCheck clean, two-space indentation.
- Messages, comments and documentation in English.
- Commit messages: a short subject in the imperative ("Add support for X"), and the *why*
  in the body when it isn't obvious.

## Pull requests

- Keep each pull request focused on one change.
- Say how you tested it: laptop, distribution and desktop, or "unit tests only".
- CI must pass.

## License

By contributing, you agree that your contributions are licensed under the
[MIT License](LICENSE), like the rest of the project.
