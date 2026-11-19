"""
GRBL lasers over the serial port: connect, home ($H), unlock ($X),
jog ($J=), stream G-code, pause (!) / resume (~), stop (soft reset).

The controller has the methods of the K40 one (kerfly.core.laser.
LaserController) the window and the job threads use, so the buttons work for
both machines.

Streaming: the "character counting" way of GRBL's docs: as many lines are
sent as fit in GRBL's 128-byte receive buffer, each "ok" frees its line's
bytes. "ok" means a line was taken in, not that it was done: at the end the
controller waits until GRBL reports Idle.

Copyright (C) 2026 Kerfly contributors
Licensed under the GNU General Public License v3 or later. See LICENSE.
"""
import logging
import time

from kerfly.core.laser import LaserError
from kerfly.i18n import _

log = logging.getLogger("kerfly")

RX_BUFFER = 127                   # GRBL's receive buffer is 128 bytes
BAUD = 115200
# serial chips of the usual GRBL boards (CH340, CP210x, FTDI, Arduino)
KNOWN_USB = {(0x1A86, 0x7523), (0x1A86, 0x55D4), (0x10C4, 0xEA60), (0x0403, 0x6001), (0x2341, 0x0043),
             (0x2341, 0x0001), (0x2A03, 0x0043)}
ERRORS = {
    "1": "G-code words consist of a letter and a value", "2": "numeric value format is not valid",
    "3": "'$' command not recognized", "8": "not idle (a '$' command only when idle)",
    "9": "G-code locked out during alarm or jog state: unlock ($X) or home ($H)",
    "15": "jog target exceeds machine travel", "20": "unsupported or invalid G-code command",
    "22": "feed rate has not yet been set", "33": "the motion target is invalid",
}
ALARMS = {
    "1": "hard limit triggered: position lost, home again",
    "2": "the move goes beyond the machine's travel (soft limits)",
    "3": "reset while moving: position lost, home again",
    "8": "homing failed: the limit switch was not found",
    "9": "homing failed: the limit switch was not found",
}


def serial_ports():
    """[(device, description)] of the serial ports, GRBL-like boards first."""
    try:
        from serial.tools import list_ports
    except ImportError:
        return []
    ports = list(list_ports.comports())
    known = [p for p in ports if (p.vid, p.pid) in KNOWN_USB]
    rest = [p for p in ports if p not in known and (p.vid is not None or "USB" in (p.device or "").upper()
                                                     or "ACM" in (p.device or ""))]
    return [(p.device, p.description or p.device) for p in known + rest]


def open_serial(port, baud):
    """The serial port (pyserial); replaced by a fake board in the tests."""
    try:
        import serial
    except ImportError:
        raise LaserError(_("The pyserial library is missing (needed for GRBL boards)."))
    try:
        return serial.Serial(port, int(baud), timeout=0.05, write_timeout=2)
    except Exception as e:                           # serial.SerialException, OSError
        text = str(e)
        if "ermission" in text or "Errno 13" in text:
            raise LaserError(_("No access to the serial port %s. On Linux add your user to the dialout group: "
                               "sudo usermod -aG dialout $USER, then log out and in again.") % port)
        raise LaserError(_("The serial port %(port)s could not be opened: %(error)s") % {"port": port, "error": text})


class GrblController:
    kind = "grbl"

    def __init__(self, opener=None):
        self.opener = opener or open_serial
        self.ser = None
        self.port_key = ""
        self.version = ""
        self.settings = {}               # GRBL's $$ settings: {"$30": "1000", ...}
        self._held = False
        self._buffer = b""
        self.jog_feed = 3000.0           # mm/min
        self.log = []                    # the last lines exchanged (diagnostics)

    # ---- connection -------------------------------------------------------
    @property
    def connected(self):
        return self.ser is not None

    def connect(self, init_home=False, port="", choose=None, baud=BAUD):
        """Open the serial port (port "" = the first GRBL board that answers), wait for GRBL's greeting, read
        its settings ($$); home when init_home and homing is on ($22=1)."""
        self.release()
        candidates = [port] if port else [p for p, _d in serial_ports()]
        if not candidates:
            raise LaserError(_("No serial port found: is the GRBL laser plugged in and switched on?"))
        last = None
        for device in candidates:
            try:
                self._open(device, baud)
                break
            except LaserError as e:
                last = e
                self.release()
        else:
            raise last or LaserError(_("No GRBL board answered."))
        log.info("grbl: connected on %s (%s), settings %s", self.port_key, self.version,
                 {k: self.settings.get(k) for k in ("$22", "$30", "$32", "$130", "$131")})
        if init_home and self.settings.get("$22", "0") not in ("0", ""):
            self.home()

    def _open(self, device, baud):
        self.ser = self.opener(device, baud)
        self.port_key = device
        self._buffer = b""
        # opening the port resets an Arduino-based board: it greets with "Grbl 1.1h ['$' for help]"
        greeting = self._wait_for(lambda line: line.startswith("Grbl"), 2.5)
        if greeting is None:
            self._write(b"\x18")                       # a board that did not reset: ask for the greeting
            greeting = self._wait_for(lambda line: line.startswith("Grbl"), 2.5)
        if greeting is None:
            raise LaserError(_("No GRBL board answered on %s.") % device)
        self.version = greeting.split("[")[0].strip()
        self.settings = {}
        for line in self.command("$$", timeout=3.0):
            if line.startswith("$") and "=" in line:
                key, value = line.split("=", 1)
                self.settings[key] = value.split()[0]

    def release(self):
        if self.ser is not None:
            log.info("grbl: release %s", self.port_key)
            try:
                self.ser.close()
            finally:
                self.ser = None
                self._held = False

    def _require(self):
        if self.ser is None:
            raise LaserError(_("Laser is not initialized."))
        return self.ser

    # ---- lines ------------------------------------------------------------
    def _write(self, data):
        self._require().write(data)
        if data not in (b"?",):
            self.log = (self.log + [">" + data.decode("ascii", "replace").strip()])[-60:]

    def _read_line(self, timeout):
        """The next line from GRBL, or None after timeout seconds."""
        end = time.monotonic() + timeout
        while True:
            if b"\n" in self._buffer:
                line, self._buffer = self._buffer.split(b"\n", 1)
                text = line.decode("ascii", "replace").strip()
                if text:
                    if not text.startswith("<"):
                        self.log = (self.log + ["<" + text])[-60:]
                    return text
                continue
            chunk = self._require().read(256)
            if chunk:
                self._buffer += chunk
            elif time.monotonic() > end:
                return None

    def _wait_for(self, wanted, timeout):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            line = self._read_line(max(0.0, end - time.monotonic()))
            if line is None:
                return None
            if wanted(line):
                return line
        return None

    def _problem(self, line):
        if line.startswith("error:"):
            code = line[6:].strip()
            return _("GRBL error %(code)s: %(text)s") % {"code": code, "text": ERRORS.get(code, line)}
        if line.startswith("ALARM:"):
            code = line[6:].strip()
            return _("GRBL alarm %(code)s: %(text)s. Unlock or home the machine.") % {
                "code": code, "text": ALARMS.get(code, line)}
        return None

    def command(self, text, timeout=5.0):
        """Send one line and wait for its "ok": the lines GRBL answered before it. Raises on error / alarm."""
        self._write(text.encode("ascii") + b"\n")
        answer = []
        end = time.monotonic() + timeout
        while True:
            line = self._read_line(max(0.05, end - time.monotonic()))
            if line is None:
                raise LaserError(_("GRBL did not answer \"%s\".") % text)
            if line == "ok":
                return answer
            problem = self._problem(line)
            if problem:
                raise LaserError(problem)
            answer.append(line)

    def status(self, timeout=1.0):
        """GRBL's status report: (state, {"MPos": (x, y, z), ...}) or None."""
        self._write(b"?")
        line = self._wait_for(lambda l: l.startswith("<"), timeout)
        if line is None:
            return None
        parts = line.strip("<>").split("|")
        fields = {}
        for p in parts[1:]:
            if ":" in p:
                k, v = p.split(":", 1)
                fields[k] = v
        return parts[0], fields

    def wait_idle(self, timeout=600.0, stop=None, update_gui=None):
        """Until GRBL reports Idle (the moves it took in are done)."""
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            if stop is not None and stop[0]:
                self._abort()
            if update_gui is not None:
                update_gui()
            st = self.status()
            if st is not None:
                if st[0].startswith("Idle"):
                    return
                if st[0].startswith("Alarm"):
                    raise LaserError(_("GRBL is in alarm: unlock or home the machine."))
            time.sleep(0.1)
        raise LaserError(_("GRBL did not finish in time."))

    # ---- the laser's buttons ----------------------------------------------
    def home(self):
        log.info("grbl: home")
        if self.settings.get("$22", "1") in ("0",):
            raise LaserError(_("Homing is switched off on this GRBL board ($22=0). Put the head in the home "
                               "corner (Settings → Machine) by hand before connecting."))
        self.command("$H", timeout=90.0)

    def unlock(self):
        log.info("grbl: unlock")
        self.command("$X")

    def unfreeze(self):
        """Soft reset (Ctrl-X): GRBL stops, forgets the job and greets again."""
        log.info("grbl: soft reset")
        self._write(b"\x18")
        self._held = False
        self._wait_for(lambda line: line.startswith("Grbl"), 3.0)

    def reset_usb(self):
        self.unfreeze()

    def pause_toggle(self):
        """Feed hold (!) or resume (~)."""
        self._write(b"~" if self._held else b"!")
        self._held = not self._held
        log.info("grbl: %s", "hold" if self._held else "resume")

    def rapid_move(self, dxmils, dymils, settings=None, send_options=None):
        """Move the head by (dx, dy) thousandths of an inch (+y up), as a jog; waits until it is there."""
        dx, dy = dxmils * 0.0254, dymils * 0.0254
        if abs(dx) < 1e-4 and abs(dy) < 1e-4:
            return
        log.info("grbl: jog %.3f, %.3f mm", dx, dy)
        self.command("$J=G91 G21 X%.3f Y%.3f F%.0f" % (dx, dy, self.jog_feed))
        self.wait_idle(timeout=120.0)

    def test_fire(self, power, ms):
        raise LaserError(_("Test fire is not available on GRBL boards yet."))

    def identify(self, port, mils=400):
        raise LaserError(_("Not available on GRBL boards."))

    # ---- jobs ---------------------------------------------------------------
    def _abort(self):
        """Stop at once: feed hold, then a soft reset (the laser goes off)."""
        log.warning("grbl: stopped by the user")
        try:
            self._write(b"!")
            time.sleep(0.2)
            self._write(b"\x18")
            self._held = False
            self._wait_for(lambda line: line.startswith("Grbl"), 2.0)
        finally:
            raise LaserError(_("Stopped by user. GRBL was reset: unlock or home the machine before the next job."))

    def stream(self, lines, update_gui=None, stop=None):
        """Send G-code lines as fast as GRBL takes them; returns the elapsed seconds. update_gui(message) is
        called with the progress (and handles pausing); stop[0] = True stops the machine."""
        self._require()
        lines = [l.split(";")[0].strip() for l in lines]
        lines = [l for l in lines if l]
        start = time.monotonic()
        pending = []                                  # bytes of the lines GRBL has not answered yet
        sent = done = 0
        total = len(lines)
        last_report = 0.0
        while done < total:
            if stop is not None and stop[0]:
                self._abort()
            while sent < total and sum(pending) + len(lines[sent]) + 1 <= RX_BUFFER:
                data = lines[sent].encode("ascii") + b"\n"
                self._write(data)
                pending.append(len(data))
                sent += 1
            line = self._read_line(0.2)
            if line is not None:
                if line == "ok":
                    if pending:
                        pending.pop(0)
                    done += 1
                else:
                    problem = self._problem(line)
                    if problem:
                        log.error("grbl: %s (line %d: %s)", problem, done + 1, lines[done] if done < total else "")
                        raise LaserError(problem)
            now = time.monotonic()
            if update_gui is not None and now - last_report > 0.3:
                last_report = now
                update_gui(_("Sending to GRBL: %d %%") % (100 * done // max(1, total)))
        self.wait_idle(stop=stop, update_gui=(lambda: update_gui(_("GRBL is finishing the job…")))
                       if update_gui else None)
        return time.monotonic() - start
