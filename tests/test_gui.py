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

from PySide6.QtWidgets import QApplication, QFileDialog, QInputDialog, QMessageBox  # noqa: E402

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

    # 6. move head to a design corner, then a job first brings it back
    w = make_window(include_Reng="0")
    w.load_design(os.path.join(FIX, "shapes.svg"))      # 100 x 80 mm
    fake = FakeK40()
    w.laser.k40 = fake
    w.move_to_corner("LR")
    lr = list(fake.moves)
    w.start_job()
    run_until_idle(app, w)
    check("move to corner LR and back before job",
          lr == [(3937, -3150)] and fake.moves == [(3937, -3150), (-3937, 3150)]
          and w.head_offset == (0, 0) and len(fake.sent) == 1, "(moves %s)" % fake.moves)

    # 7. go to position: home, then move to X 20 mm, Y 10 mm down
    w = make_window()
    fake = FakeK40()
    w.laser.k40 = fake
    w.goto_x.setValue(20.0)
    w.goto_y.setValue(10.0)
    w.goto_position()
    check("go to position", "home_position" in fake.calls and fake.moves == [(787, -394)]
          and w.head == (0.787, -0.394) and w.values["gotoY"] == "-10",
          "(moves %s, head %s)" % (fake.moves, w.head))

    # 7b. unit change converts the go-to fields
    from kerfly.core import config as cfg
    new = cfg.convert_units(w.values, "in")
    w.values.clear()
    w.values.update(new)
    w._reload_spin_values()
    check("go-to fields follow unit change", abs(w.goto_x.value() - 0.79) < 0.01
          and abs(w.goto_y.value() - 0.39) < 0.01, "(%s, %s)" % (w.goto_x.value(), w.goto_y.value()))

    # 8. time estimate: raster unknown until calculated
    w = make_window()
    w.load_design(os.path.join(FIX, "shapes.svg"))
    before = w.time_labels["Raster_Eng"].text()
    vcut = w.time_labels["Vector_Cut"].text()
    w.calculate_raster_time()
    run_until_idle(app, w)
    after = w.time_labels["Raster_Eng"].text()
    check("time estimate", before == "?" and after not in ("", "?") and vcut.endswith("s")
          and not w.btn_calc_time.isVisible(), "(raster %r -> %r, cut %r, total %r)"
          % (before, after, vcut, w.total_time_label.text()))

    # 9. send an EGV file (3 passes)
    egv_path = os.path.join(BASE, "svg_vcut.egv")
    w = make_window()
    fake = FakeK40()
    w.laser.k40 = fake
    QFileDialog.getOpenFileName = staticmethod(lambda *a, **k: (egv_path, ""))
    QInputDialog.getInt = staticmethod(lambda *a, **k: (3, True))
    w.send_egv_file()
    run_until_idle(app, w)
    raw = open(egv_path, "rb").read()
    payload = raw[raw.index(b"%0%0%0%0%") + 9:]
    check("send EGV file", fake.sent == [(None, payload)] and fake.passes == [3] and fake.moves == [],
          "(sent %d bytes, passes %s)" % (len(fake.sent[0][1]) if fake.sent else 0, fake.passes))

    # 10. open a PNG through the window (size dialog accepted) and save EGV
    from kerfly.gui import image_dialog
    sys.path.insert(0, TESTS_DIR)
    from regression import synthetic_image
    png = tempfile.mktemp(suffix=".png")
    synthetic_image().save(png, dpi=(1000, 1000))
    image_dialog.ImageSizeDialog.exec = lambda self: True
    w = make_window()
    w.load_design(png)
    out = tempfile.mktemp(suffix=".egv")
    w.start_job(output_file=out)
    run_until_idle(app, w)
    digest = hashlib.sha256(open(out, "rb").read()).hexdigest() if os.path.exists(out) else None
    check("open PNG in window, save EGV == png_reng_halftone",
          digest == manifest["png_reng_halftone"]["sha256"], "(%s)" % w.design_label.text())
    os.remove(png)

    print("\n%d check(s) failed." % failures if failures else "\nAll checks passed.")
    return 1 if failures else 0


if __name__ == "__main__":
    rc = main()
    sys.stdout.flush()
    os._exit(rc)
