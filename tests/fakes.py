"""
Stand-ins for the hardware in the GUI tests: a K40 board that records what it
gets, and waiting for a job to finish.

Copyright (C) 2026 Kerfly contributors
Licensed under the GNU General Public License v3 or later. See LICENSE.
"""
import time


class FakeK40:
    """Records what would be sent; send_data calls update_gui like nano_library."""

    def __init__(self, slow=False):
        self.timeout = 200
        self.n_timeouts = 30
        self.sent = []          # (power, bytes)
        self.passes = []
        self.moves = []         # rapid moves (dx, dy) in mils
        self.power = None
        self.calls = []
        self.slow = slow

    def set_PWM_register(self, p):
        self.power = p

    def send_data(self, data, update_gui=None, stop_calc=None, passes=1, preprocess_crc=True,
                  wait_for_laser=False):
        for _ in range(50 if self.slow else 1):
            update_gui("Sending")
            if stop_calc[0]:
                self.calls.append("e_stop")
                raise Exception("Action Stopped by User.")
            if self.slow:
                time.sleep(0.02)
        self.sent.append((self.power, bytes(data)))
        self.passes.append(passes)
        self.power = None

    def rapid_move(self, dx, dy):
        self.moves.append((dx, dy))

    def pause_un_pause(self):
        self.calls.append("pause")

    def __getattr__(self, name):
        return lambda *a, **k: self.calls.append(name)


def run_until_idle(app, window, timeout=120):
    t0 = time.time()
    while window.worker is not None and time.time() - t0 < timeout:
        app.processEvents()
        time.sleep(0.01)
    return window.worker is None
