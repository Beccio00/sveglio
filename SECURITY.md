# Security policy

lid-guard runs as root and has access to your input devices, so security problems are taken
seriously.

## Supported versions

Only the latest release receives security fixes.

## Reporting a vulnerability

**Please do not open a public issue.** Report it privately through GitHub instead: on the
repository page, open the **Security** tab and click **Report a vulnerability**
([direct link](https://github.com/Beccio00/sveglio/security/advisories/new)).

Please include what an attacker could do, the steps to reproduce it, and the versions of
sveglio, your distribution and systemd. You will get an answer as soon as possible. Once a
fix is ready, the advisory is published together with it, crediting you if you wish.

## Scope

In scope, for example:

- ways to gain privileges through lid-guard, its configuration or its systemd units;
- ways to read keystrokes through sveglio or lid-guard;
- ways in which sveglio or lid-guard leave the session unlocked, or input devices blocked,
  when they shouldn't.

Out of scope: bugs in your screen locker, your desktop or systemd itself. Please report
those to their own projects.

## How lid-guard limits the damage

- It never inspects input events: the events of grabbed devices are read only to be
  discarded.
- Its systemd unit has no network access (`PrivateNetwork=yes`), sees a read-only file
  system apart from `/dev`, `/proc` and `/sys` (`ProtectSystem=strict`), cannot access home
  directories (`ProtectHome=yes`) and cannot gain new privileges (`NoNewPrivileges=yes`).
- It is installed as root-owned files outside home directories, so an unprivileged process
  cannot modify the code that runs as root.
