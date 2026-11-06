"""
Linux: let the user talk to the K40's USB board without root, with one
click. Kerfly writes a udev rule (the same as packaging/linux/99-kerfly-k40.rules)
through pkexec, which asks for the password in a system window; then the
laser is unplugged and plugged in again. Without pkexec, the commands to type
are shown instead.

Copyright (C) 2026 Kerfly contributors
Licensed under the GNU General Public License v3 or later. See LICENSE.
"""
import glob
import os
import shutil
import subprocess
import sys

RULE_FILE = "/etc/udev/rules.d/99-kerfly-k40.rules"
RULE = 'SUBSYSTEM=="usb", ATTRS{idVendor}=="1a86", ATTRS{idProduct}=="5512", MODE="0666", TAG+="uaccess"'
RULE_DIRS = ("/etc/udev/rules.d", "/lib/udev/rules.d", "/usr/lib/udev/rules.d")
# writes the rule given as $1, then makes udev use it at once
SCRIPT = ('printf "%s\\n" "$1" > ' + RULE_FILE + ' && udevadm control --reload-rules'
          ' && udevadm trigger --subsystem-match=usb --attr-match=idVendor=1a86')


def applies():
    return sys.platform.startswith("linux")


def permission_problem(text):
    """Is this USB error the missing permission (the board is there, but not ours)?"""
    t = (text or "").lower()
    return "errno 13" in t or "access denied" in t or "insufficient permissions" in t or "permission denied" in t


def installed(dirs=RULE_DIRS):
    """A rule for the K40 board (vendor 1a86, product 5512) is already there."""
    for folder in dirs:
        for path in glob.glob(os.path.join(folder, "*.rules")):
            try:
                text = open(path, encoding="utf-8", errors="replace").read().lower()
            except OSError:
                continue
            if "1a86" in text and "5512" in text:
                return True
    return False


def manual_commands():
    """What to type in a terminal when pkexec is not there."""
    return ["echo '%s' | sudo tee %s" % (RULE, RULE_FILE),
            "sudo udevadm control --reload-rules",
            "sudo udevadm trigger --subsystem-match=usb --attr-match=idVendor=1a86"]


def _clean_env():
    """The environment for system programs: without the libraries of a packaged Kerfly
    (PyInstaller / AppImage put theirs first)."""
    env = dict(os.environ)
    for key in ("LD_LIBRARY_PATH", "LD_PRELOAD"):
        original = env.pop(key + "_ORIG", None)
        if original:
            env[key] = original
        else:
            env.pop(key, None)
    return env


def install(run=subprocess.run, which=shutil.which):
    """Write the rule as root through pkexec. Returns (ok, text): text says what
    went wrong ("no pkexec", "cancelled", or the error)."""
    pkexec = which("pkexec")
    if not pkexec:
        return False, "no pkexec"
    try:
        done = run([pkexec, "sh", "-c", SCRIPT, "sh", RULE], env=_clean_env(), timeout=300,
                   capture_output=True, text=True)
    except (OSError, subprocess.SubprocessError) as e:
        return False, str(e)
    if done.returncode == 0:
        return True, ""
    if done.returncode in (126, 127):              # pkexec: the password window was closed
        return False, "cancelled"
    return False, (done.stderr or done.stdout or "exit code %d" % done.returncode).strip()
