"""
Finding the USB library on Windows.

The K40 board is driven through pyusb with the libusb-win32 back end, which
needs libusb0.dll. The driver installers (Zadig, Scorch's K40 driver
installer) put it into C:\\Windows\\System32; K40 Whisperer also ships one next
to its program. A program packed with PyInstaller did not always find it
(Kerfly 0.18.0 on Windows 10: "No backend available" while the same PC worked
from source), so Kerfly looks in each place itself, loads the first one that
works, and says in the log where it looked.

Once loaded, pyusb keeps the library for the whole run, so nano_library's own
lookup (unchanged K40 Whisperer code) then finds it too.

Copyright (C) 2026 Kerfly contributors
Licensed under the GNU General Public License v3 or later. See LICENSE.
"""
import os
import sys

from kerfly.core.diag import log

_result = None          # (found, text) after the first search


def candidates():
    """Places to look for libusb0.dll, in order (Windows)."""
    places = []
    windir = os.environ.get("SystemRoot") or os.environ.get("WINDIR") or r"C:\Windows"
    places.append(os.path.join(windir, "System32", "libusb0.dll"))
    places.append(os.path.join(os.path.dirname(sys.executable), "libusb0.dll"))   # next to Kerfly.exe / python.exe
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        places.append(os.path.join(meipass, "libusb0.dll"))
    return places


def ensure_libusb():
    """Make sure pyusb has a USB back end. Returns (found, text for the log /
    self-test). Does nothing outside Windows, where pyusb finds libusb itself."""
    global _result
    if _result is not None and _result[0]:
        return _result
    if os.name != "nt":
        _result = (True, "system libusb")
        return _result
    try:
        import usb.backend.libusb0 as libusb0
    except Exception as e:                      # pyusb missing
        _result = (False, "pyusb not available: %s" % e)
        return _result
    if libusb0.get_backend() is not None:
        _result = (True, "libusb0.dll found by pyusb")
        log.info("usb: %s", _result[1])
        return _result
    looked = []
    for path in candidates():
        exists = os.path.isfile(path)
        looked.append("%s (%s)" % (path, "found" if exists else "missing"))
        if not exists:
            continue
        try:
            backend = libusb0.get_backend(find_library=lambda _name, p=path: p)
        except Exception as e:
            looked[-1] = "%s (could not load: %s)" % (path, e)
            continue
        if backend is not None:
            _result = (True, "libusb0.dll loaded from %s" % path)
            log.info("usb: %s", _result[1])
            return _result
        looked[-1] = "%s (could not load)" % path
    _result = (False, "libusb0.dll not found; looked in: " + "; ".join(looked))
    log.warning("usb: %s", _result[1])
    return _result
