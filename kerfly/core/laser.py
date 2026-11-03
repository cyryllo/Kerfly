"""
Laser controller: connection, homing, jogging and sending jobs to a K40
(Lihuiyu M2 Nano family) board through nano_library.

Thread model: a GUI may run send() in a worker thread. All USB traffic of a
running job happens in that thread. A pause requested from another thread is
carried out by the worker between USB packets (see PauseControl), so two
threads never talk to the board at the same time.

Copyright (C) 2017-2026 Scorch (original code in K40 Whisperer)
Copyright (C) 2026 Kerfly contributors

This program is free software: you can redistribute it and/or modify it under
the terms of the GNU General Public License as published by the Free Software
Foundation, either version 3 of the License, or (at your option) any later
version. See the LICENSE file for details.
"""
import threading
from time import time

from egv import egv
from kerfly.core.diag import log
from kerfly.i18n import _


class LaserError(Exception):
    pass


class PauseControl:
    """Pause / resume / terminate protocol between a GUI thread and the job thread.

    GUI thread:  request_pause(), then later resume() or terminate().
    Job thread:  poll(laser, stop) from the progress callback; when a pause is
                 requested it pauses the board, calls on_paused() and blocks
                 until the GUI answers.
    """

    def __init__(self, on_paused=None):
        self._requested = threading.Event()
        self._answered = threading.Event()
        self._terminate = False
        self.on_paused = on_paused

    def request_pause(self):
        self._answered.clear()
        self._requested.set()

    def resume(self):
        self._terminate = False
        self._answered.set()

    def terminate(self):
        self._terminate = True
        self._answered.set()

    def poll(self, laser, stop):
        if not self._requested.is_set():
            return
        self._requested.clear()
        laser.pause_toggle()
        if self.on_paused is not None:
            self.on_paused()
        self._answered.wait()
        if self._terminate:
            stop[0] = True     # the send loop stops the board (e-stop) and raises
        else:
            laser.pause_toggle()


class LaserController:
    def __init__(self):
        self.k40 = None

    @property
    def connected(self):
        return self.k40 is not None

    def connect(self, init_home=True):
        """Open the USB device. Raises LaserError with a readable message."""
        from nano_library import K40_CLASS   # needs pyusb; imported lazily
        self.release()
        log.info("laser: connect (home after connecting: %s)", init_home)
        k40 = K40_CLASS()
        try:
            k40.initialize_device()
            k40.say_hello()
        except Exception as e:
            log.error("laser: connect failed: %r", e)
            text = "%s" % e
            if "BACKEND" in text.upper():
                text += " " + _("(libUSB driver not installed)")
            raise LaserError(_("USB error: %s") % text)
        self.k40 = k40
        log.info("laser: connected (USB location %s)", getattr(k40, "USB_Location", None))
        if init_home:
            self.home()
        else:
            self.unlock()

    def release(self):
        if self.k40 is not None:
            log.info("laser: release USB")
            try:
                self.k40.release_usb()
            finally:
                self.k40 = None

    def _require(self):
        if self.k40 is None:
            raise LaserError(_("Laser is not initialized."))
        return self.k40

    def home(self):
        log.info("laser: home")
        self._require().home_position()

    def unlock(self):
        log.info("laser: unlock rail")
        self._require().unlock_rail()

    def unfreeze(self):
        log.info("laser: unfreeze")
        self._require().unfreeze()

    def reset_usb(self):
        log.info("laser: reset USB")
        self._require().reset_usb()

    def pause_toggle(self):
        log.info("laser: pause / resume toggle")
        self._require().pause_un_pause()

    def rapid_move(self, dxmils, dymils, settings, send_options=None):
        """Move the head by (dxmils, dymils) thousandths of an inch, applying
        the calibration scale. With a rotary and a rapid feed set, the move is
        sent as a slow EGV move instead."""
        k40 = self._require()
        Xscale, Yscale = settings.xy_scale
        if Xscale != 1.0 or Yscale != 1.0:
            dxmils = int(round(dxmils * Xscale))
            dymils = int(round(dymils * Yscale))
        k40.n_timeouts = 10
        log.info("laser: rapid move dx=%d dy=%d mils (%.2f, %.2f mm)", int(dxmils), int(dymils),
                 dxmils * 0.0254, dymils * 0.0254)
        if settings.rotary and settings.rapid_feed:
            if int(dxmils) == 0 and int(dymils) == 0:
                return
            data = []
            egv(target=lambda s: data.append(s)).make_egv_rapid(
                int(dxmils), int(dymils),
                Feed=settings.rapid_feed * settings.feed_factor,
                board_name=settings.board_name)
            self.send(data, **(send_options or {}))
        else:
            k40.rapid_move(int(dxmils), int(dymils))

    def send(self, data, power=None, update_gui=None, stop=None, pre_process_crc=True,
             wait_for_laser=True, timeout_ms=200, n_timeouts=30, passes=1):
        """Send EGV data. power (percent) is set first when given (M3 boards).
        Returns the elapsed time in seconds. Raises when stopped or on USB errors."""
        k40 = self._require()
        k40.timeout = int(timeout_ms)
        k40.n_timeouts = int(n_timeouts)
        start = time()
        log.info("laser: send %s bytes, power %s, passes %s, wait for laser %s",
                 len(data) if hasattr(data, "__len__") else "?", power, passes,
                 wait_for_laser)
        try:
            if power is not None:
                k40.set_PWM_register(power)
            k40.send_data(data, update_gui, stop, passes, pre_process_crc, wait_for_laser=wait_for_laser)
        except BaseException as e:
            log.warning("laser: send ended after %.1f s: %r%s", time() - start, e,
                        " (stopped by the user)" if stop and stop[0] else "")
            raise
        log.info("laser: send finished in %.1f s", time() - start)
        return time() - start

    def test_fire(self, power, ms):
        k40 = self._require()
        log.info("laser: test fire %s%% for %s ms", power, ms)
        if ms < 1 or power == 0:
            k40.set_PWM_register(power)
        else:
            k40.pulse_laser(pct_power=power, ms=ms)


def clamp_head_position(x, y, dx, dy, bed_w, bed_h, design_w=0.0, design_h=0.0,
                        offset=(0.0, 0.0)):
    """New design origin after moving by (dx, dy) inches, kept on the bed so
    the design (design_w x design_h, top-left at the origin) stays inside it.
    offset is the head's temporary offset from the origin in inches; the head
    itself is kept on the bed too. The bed spans x in [0, bed_w], y in [-bed_h, 0]."""
    X = x + dx
    Y = y + dy
    if X < 0.0:
        X = 0.0
    if X + design_w > bed_w:
        X = bed_w - design_w
    if Y - design_h < -bed_h:
        Y = -bed_h + design_h
    if Y > 0.0:
        Y = 0.0
    xo, yo = offset
    if X + xo < 0.0:
        X = X + (0.0 - (X + xo))
    if X + xo > bed_w:
        X = X - ((X + xo) - bed_w)
    if Y + yo < -bed_h:
        Y = Y + (-bed_h - (Y + yo))
    if Y + yo > 0.0:
        Y = Y - (Y + yo)
    return round(X, 3), round(Y, 3)


# corner name -> (fraction of design width, fraction of design height)
CORNERS = {"UL": (0.0, 0.0), "UR": (1.0, 0.0), "LR": (1.0, 1.0), "LL": (0.0, 1.0),
           "CC": (0.5, 0.5)}


def corner_offset(corner, bounds, home_upper_right, origin, bed_w, bed_h):
    """Head offset in mils (dx, dy) from the design origin to a design corner
    ("UL", "UR", "LR", "LL" or "CC"), or None if that point is off the bed.
    bounds are the (rotated) design bounds; origin is the design origin."""
    xmin, xmax, ymin, ymax = bounds
    w, h = xmax - xmin, ymax - ymin
    fx, fy = CORNERS[corner]
    if home_upper_right and corner != "CC":
        fx = 1.0 - fx          # x runs right-to-left from an upper-right home
    if corner == "CC":
        DX = round(w / 2.0 * 1000.0)
        DY = round(h / 2.0 * 1000.0)
    else:
        DX = round(w * 1000.0) if fx else 0
        DY = round(h * 1000.0) if fy else 0
    x_new = origin[0] + fx * w
    y_new = origin[1] - fy * h
    if x_new > bed_w + .001 or y_new < -bed_h - .001:
        return None
    return DX, -DY


def temporary_offset_target(origin, new_offset_mils, bed_w, bed_h):
    """Clamp a requested head offset (mils) so the head stays on the bed;
    returns the offset actually reachable, in mils."""
    dx = round(new_offset_mils[0] / 1000.0, 3)
    dy = round(new_offset_mils[1] / 1000.0, 3)
    X, Y = clamp_head_position(origin[0], origin[1], dx, dy, bed_w, bed_h)
    return round((X - origin[0]) * 1000.0), round((Y - origin[1]) * 1000.0)
