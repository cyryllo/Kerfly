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
        # slow: True for about a second per send, or a number of 20 ms steps (a long job to pause or
        # stop); read at every step, so a test can let a long send finish quickly
        n = 0
        while n < (self.slow if not isinstance(self.slow, bool) and self.slow else (50 if self.slow else 1)):
            update_gui("Sending")
            if stop_calc[0]:
                self.calls.append("e_stop")
                raise Exception("Action Stopped by User.")
            if self.slow:
                time.sleep(0.02)
            n += 1
        self.sent.append((self.power, bytes(data)))
        self.passes.append(passes)
        self.power = None

    def rapid_move(self, dx, dy):
        self.moves.append((dx, dy))

    def pause_un_pause(self):
        self.calls.append("pause")

    def __getattr__(self, name):
        return lambda *a, **k: self.calls.append(name)


class FakeGrbl:
    """A GRBL 1.1 board on a serial port (kerfly.core.grbl's opener): greets after a reset, answers every line
    "ok" (an "error:20" for an unknown command), keeps the receive buffer to 128 bytes (more is a failure),
    reports its state to "?", holds on "!", resumes on "~", resets on Ctrl-X. Moves are done at once
    (Idle), or after `busy_reports` status reports (Run) when set."""

    def __init__(self, homing=True, busy_reports=0):
        self.settings = {"$22": "1" if homing else "0", "$30": "1000", "$32": "1", "$130": "400", "$131": "300"}
        self.out = b""
        self.lines = []             # every line taken in
        self.jogs = []              # (dx, dy) mm
        self.realtime = []          # "!", "~", "reset"
        self.state = "Idle"
        self.overflow = False
        self.closed = False
        self.busy_reports = busy_reports
        self._busy = 0
        self._rx = 0                # bytes in the receive buffer (answered with "ok" when taken)
        self._partial = b""
        self.pos = [0.0, 0.0]
        self._greet()

    def _greet(self):
        self.out += b"\r\nGrbl 1.1h ['$' for help]\r\n"

    # pyserial's methods kerfly.core.grbl uses
    def write(self, data):
        for byte in data:
            c = bytes([byte])
            if c == b"?":
                state = self.state
                if self._busy > 0:
                    self._busy -= 1
                    state = "Run"
                    if self._busy == 0:
                        self.state = "Idle"
                self.out += ("<%s|MPos:%.3f,%.3f,0.000|FS:0,0>\r\n" % (state, *self.pos)).encode()
            elif c == b"!":
                self.realtime.append("!")
                self.state = "Hold:0"
            elif c == b"~":
                self.realtime.append("~")
                self.state = "Idle"
            elif c == b"\x18":
                self.realtime.append("reset")
                self.state = "Idle"
                self._partial = b""
                self._rx = 0
                self._greet()
            else:
                self._partial += c
                self._rx += 1
                if self._rx > 128:
                    self.overflow = True
                if c == b"\n":
                    line = self._partial.decode().strip()
                    self._partial = b""
                    self._rx -= len(line) + 1
                    self._line(line)
        return len(data)

    def _line(self, line):
        self.lines.append(line)
        if line == "$$":
            for k, v in self.settings.items():
                self.out += ("%s=%s\r\n" % (k, v)).encode()
        elif line.startswith("$J="):
            words = dict((w[0], float(w[1:])) for w in line[3:].split() if w[0] in "XY")
            self.jogs.append((words.get("X", 0.0), words.get("Y", 0.0)))
            self.pos[0] += words.get("X", 0.0)
            self.pos[1] += words.get("Y", 0.0)
            self._move()
        elif line == "$H":
            self.pos = [0.0, 0.0]
            self._move()
        elif line.startswith("G") or line.startswith("M") or line in ("$X",):
            if line[0] == "G":
                self._move()
        else:
            self.out += b"error:20\r\n"
            return
        self.out += b"ok\r\n"

    def _move(self):
        if self.busy_reports:
            self._busy = self.busy_reports
            self.state = "Run"

    def read(self, n=1):
        data, self.out = self.out[:n], self.out[n:]
        return data

    def close(self):
        self.closed = True


def run_until_idle(app, window, timeout=120):
    t0 = time.time()
    while window.worker is not None and time.time() - t0 < timeout:
        app.processEvents()
        time.sleep(0.01)
    return window.worker is None
