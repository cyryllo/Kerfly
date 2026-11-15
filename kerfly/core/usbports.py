"""
Which K40 board: with two lasers plugged into one computer, each laser profile
can remember the USB port of its machine (Settings → Machine → USB port).

K40 boards (CH341, 1a86:5512) have no serial number, so two of them look the
same; they are told apart by where they are plugged in. Where the USB library
reports the physical port (Linux: the socket path, e.g. "1-2.3") the key stays
the same after unplugging and plugging back into the same socket; elsewhere
(libusb-win32) only the bus and the device number are known, and the number
can change after a replug or a restart, so Kerfly then asks again.

Copyright (C) 2026 Kerfly contributors
Licensed under the GNU General Public License v3 or later. See LICENSE.
"""
from dataclasses import dataclass

VENDOR, PRODUCT = 0x1a86, 0x5512


@dataclass
class Port:
    key: str            # what a profile remembers
    bus: int
    address: int
    stable: bool        # True: the physical socket (stays the same after a replug)

    @property
    def label(self):
        return ("USB %s" % self.key) if self.stable else ("USB %d:%d" % (self.bus, self.address))


def _port_of(device):
    ports = None
    try:
        ports = device.port_numbers
    except Exception:                    # libusb-win32: not known
        ports = None
    if ports:
        return Port("%d-%s" % (device.bus, ".".join(str(p) for p in ports)), int(device.bus), int(device.address),
                    True)
    return Port("%d:%d" % (device.bus, device.address), int(device.bus), int(device.address), False)


def list_lasers():
    """The K40 boards plugged in now ([] when none, or when USB cannot be read)."""
    try:
        import usb.core
        return [_port_of(d) for d in usb.core.find(idVendor=VENDOR, idProduct=PRODUCT, find_all=True)]
    except Exception:
        return []


def find(ports, key):
    return next((p for p in ports if p.key == key), None) if key else None


def key_of(ports, location):
    """The key of the port at (bus, address), or ''."""
    if not location:
        return ""
    return next((p.key for p in ports if (p.bus, p.address) == tuple(location)), "")
