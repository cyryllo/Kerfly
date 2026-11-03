#!/usr/bin/env python3
"""
Tests the PySide6 GUI end to end (offscreen): jobs started from the new
window must produce the same laser data as the upstream baseline, and
pause/stop must work while a job is being sent.

Usage:
    .venv/bin/python tests/test_gui.py
"""
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(TESTS_DIR)
sys.path.insert(0, ROOT_DIR)

from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from kerfly.core import config  # noqa: E402
from kerfly.gui.main_window import MainWindow  # noqa: E402

FIX = os.path.join(TESTS_DIR, "fixtures")
BASE = os.path.join(TESTS_DIR, "baseline")


class FakeK40:
    """Records what would be sent; send_data calls update_gui like nano_library."""

    def __init__(self, slow=False):
        self.timeout = 200
        self.n_timeouts = 30
        self.sent = []          # (power, bytes)
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
        self.power = None

    def pause_un_pause(self):
        self.calls.append("pause")

    def __getattr__(self, name):
        return lambda *a, **k: self.calls.append(name)


def read_usb_baseline(path):
    """[(power, bytes)] from a regression .usb capture."""
    blob = open(path, "rb").read()
    out, power, pos = [], None, 0
    while pos < len(blob):
        end = blob.index(b"\n", pos)
        line = blob[pos:end].decode()
        pos = end + 1
        m = re.match(r"#set_PWM_register (.*)", line)
        if m:
            power = float(m.group(1))
            continue
        m = re.match(r"#send_data .* len=(\d+)", line)
        if m:
            n = int(m.group(1))
            out.append((power, blob[pos:pos + n]))
            pos += n + 1
            power = None
    return out


def run_until_idle(app, window, timeout=120):
    t0 = time.time()
    while window.worker is not None and time.time() - t0 < timeout:
        app.processEvents()
        time.sleep(0.01)
    return window.worker is None


def make_window(**overrides):
    values = dict(config.DEFAULT_VALUES)
    values["inkscape_path"] = shutil.which("inkscape") or ""
    values.update(overrides)
    return MainWindow(values)


def main():
    app = QApplication([])
    manifest = json.load(open(os.path.join(BASE, "manifest.json")))["cases"]
    failures = 0

    def check(name, ok, detail=""):
        nonlocal failures
        print("%-5s %s %s" % ("OK" if ok else "FAIL", name, detail))
        failures += 0 if ok else 1

    # 1. EGV file from the GUI == baseline (raster + vector engrave + vector cut)
    w = make_window()
    w.load_design(os.path.join(FIX, "shapes.svg"))
    out = tempfile.mktemp(suffix=".egv")
    w.start_job(output_file=out)
    run_until_idle(app, w)
    digest = hashlib.sha256(open(out, "rb").read()).hexdigest() if os.path.exists(out) else None
    check("gui_save_egv == svg_raster_vector_cut", digest == manifest["svg_raster_vector_cut"]["sha256"])

    # 2. only vector cut selected, DXF
    w = make_window(include_Reng="0", include_Veng="0")
    w.load_design(os.path.join(FIX, "shapes.dxf"))
    w.start_job(output_file=out)
    run_until_idle(app, w)
    digest = hashlib.sha256(open(out, "rb").read()).hexdigest()
    check("gui_save_egv dxf == dxf_vcut", digest == manifest["dxf_vcut"]["sha256"])
    os.remove(out)

    # 3. M3 power per stage through the laser path
    w = make_window(board_name="LASER-M3", Reng_power="0.3", Veng_power="0.6", Vcut_power="0.9")
    w.load_design(os.path.join(FIX, "shapes.svg"))
    fake = FakeK40()
    w.laser.k40 = fake
    w.start_job()
    run_until_idle(app, w)
    expected = read_usb_baseline(os.path.join(BASE, "usb_m3_power_levels.usb"))
    check("gui_laser_job m3 == usb_m3_power_levels", fake.sent == expected,
          "(%d stages, powers %s)" % (len(fake.sent), [p for p, _ in fake.sent]))

    # 4. pause then terminate while sending
    w = make_window()
    w.load_design(os.path.join(FIX, "shapes.svg"))
    fake = FakeK40(slow=True)
    w.laser.k40 = fake
    answers = []
    QMessageBox.question = staticmethod(lambda *a, **k: (answers.append(1), QMessageBox.No)[1])
    w.start_job()
    t0 = time.time()
    while "Sending" not in w.statusBar().currentMessage() and time.time() - t0 < 60:
        app.processEvents()
        time.sleep(0.01)
    w.stop_job()
    run_until_idle(app, w)
    check("gui pause -> terminate", answers == [1] and fake.calls.count("pause") == 1
          and "e_stop" in fake.calls and fake.sent == [],
          "(calls %s, status %r)" % (fake.calls, w.statusBar().currentMessage()))

    # 5. pause then resume
    w = make_window(include_Reng="0")
    w.load_design(os.path.join(FIX, "shapes.svg"))
    fake = FakeK40(slow=True)
    w.laser.k40 = fake
    QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Yes)
    w.start_job()
    t0 = time.time()
    while "Sending" not in w.statusBar().currentMessage() and time.time() - t0 < 60:
        app.processEvents()
        time.sleep(0.01)
    w.stop_job()
    run_until_idle(app, w)
    check("gui pause -> resume", fake.calls.count("pause") == 2 and len(fake.sent) == 1,
          "(calls %s)" % fake.calls)

    print("\n%d check(s) failed." % failures if failures else "\nAll checks passed.")
    return 1 if failures else 0


if __name__ == "__main__":
    rc = main()
    sys.stdout.flush()
    os._exit(rc)
