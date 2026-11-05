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
# never touch the user's real settings folder (material library) from tests
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp(prefix="kerfly_test_cfg_")
os.environ["APPDATA"] = os.environ["XDG_CONFIG_HOME"]
TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(TESTS_DIR)
sys.path.insert(0, ROOT_DIR)

from PySide6.QtWidgets import QApplication, QComboBox, QFileDialog, QInputDialog, QLabel, QMessageBox, QToolButton  # noqa: E402

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


def find_inkscape():
    """Inkscape the way Kerfly finds it (PATH or the usual install folders)."""
    import svg_reader
    reader = svg_reader.SVG_READER()
    reader.set_inkscape_path(shutil.which("inkscape"))
    return reader.inkscape_exe or ""


INKSCAPE = find_inkscape()


def make_window(**overrides):
    values = dict(config.DEFAULT_VALUES)
    values["inkscape_path"] = INKSCAPE
    values.update(overrides)
    return MainWindow(values)


def main():
    app = QApplication([])
    # "save changes first?" when replacing a design: discard in tests
    QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Discard)
    manifest = json.load(open(os.path.join(BASE, "manifest.json")))["cases"]
    failures = 0

    def check(name, ok, detail=""):
        nonlocal failures
        print("%-5s %s %s" % ("OK" if ok else "FAIL", name, detail))
        if not ok and os.environ.get("GITHUB_ACTIONS"):
            print("::error title=test_gui::%s %s" % (name, detail))     # shown as a CI annotation
        failures += 0 if ok else 1

    def skip(name):
        print("SKIP  %s (Inkscape not installed; the baseline raster was made with Inkscape)" % name)

    # 1. EGV file from the GUI == baseline (raster + vector engrave + vector cut)
    out = tempfile.mktemp(suffix=".egv")
    if INKSCAPE:
        w = make_window()
        w.load_design(os.path.join(FIX, "shapes.svg"))
        w.start_job(output_file=out)
        run_until_idle(app, w)
        digest = hashlib.sha256(open(out, "rb").read()).hexdigest() if os.path.exists(out) else None
        check("gui_save_egv == svg_raster_vector_cut", digest == manifest["svg_raster_vector_cut"]["sha256"])
    else:
        skip("gui_save_egv == svg_raster_vector_cut")

    # 2. only vector cut selected, DXF
    w = make_window(include_Reng="0", include_Veng="0")
    w.load_design(os.path.join(FIX, "shapes.dxf"))
    w.start_job(output_file=out)
    run_until_idle(app, w)
    digest = hashlib.sha256(open(out, "rb").read()).hexdigest()
    check("gui_save_egv dxf == dxf_vcut", digest == manifest["dxf_vcut"]["sha256"])
    os.remove(out)

    # 3. M3 power per stage through the laser path
    if INKSCAPE:
        w = make_window(board_name="LASER-M3", Reng_power="0.3", Veng_power="0.6", Vcut_power="0.9")
        w.load_design(os.path.join(FIX, "shapes.svg"))
        fake = FakeK40()
        w.laser.k40 = fake
        w.start_job()
        run_until_idle(app, w)
        expected = read_usb_baseline(os.path.join(BASE, "usb_m3_power_levels.usb"))
        check("gui_laser_job m3 == usb_m3_power_levels", fake.sent == expected,
              "(%d stages, powers %s)" % (len(fake.sent), [p for p, _ in fake.sent]))
    else:
        skip("gui_laser_job m3 == usb_m3_power_levels")

    # 4. Stop while sending: immediate e-stop, no pause, no question
    w = make_window()
    w.load_design(os.path.join(FIX, "shapes.svg"))
    fake = FakeK40(slow=True)
    w.laser.k40 = fake
    asked = []
    QMessageBox.question = staticmethod(lambda *a, **k: (asked.append(1), QMessageBox.No)[1])

    def wait_for_sending(w):
        t0 = time.time()
        while "Sending" not in w.statusBar().currentMessage() and time.time() - t0 < 60:
            app.processEvents()
            time.sleep(0.01)

    w.start_job()
    wait_for_sending(w)
    w.stop_job()
    run_until_idle(app, w)
    check("Stop: immediate e-stop", not asked and "pause" not in fake.calls and "e_stop" in fake.calls
          and fake.sent == [], "(calls %s, status %r)" % (fake.calls, w.statusBar().currentMessage()))

    # 5. Pause, then the same button resumes; the job finishes
    w = make_window(include_Reng="0")
    w.load_design(os.path.join(FIX, "shapes.svg"))
    fake = FakeK40(slow=True)
    w.laser.k40 = fake
    w.start_job()
    wait_for_sending(w)
    w.pause_job()
    t0 = time.time()
    while not w._paused and time.time() - t0 < 30:
        app.processEvents()
        time.sleep(0.01)
    paused_state = w._paused and w.btn_pause.isEnabled()
    w.pause_job()                                   # resume
    run_until_idle(app, w)
    check("Pause -> resume", paused_state and fake.calls.count("pause") == 2 and len(fake.sent) == 1
          and not asked, "(calls %s)" % fake.calls)

    # 5b. Pause, then Stop ends the job
    w = make_window(include_Reng="0")
    w.load_design(os.path.join(FIX, "shapes.svg"))
    fake = FakeK40(slow=True)
    w.laser.k40 = fake
    w.start_job()
    wait_for_sending(w)
    w.pause_job()
    t0 = time.time()
    while not w._paused and time.time() - t0 < 30:
        app.processEvents()
        time.sleep(0.01)
    w.stop_job()
    run_until_idle(app, w)
    check("Pause -> Stop", fake.calls.count("pause") == 1 and "e_stop" in fake.calls and fake.sent == []
          and not w._paused, "(calls %s)" % fake.calls)

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
          and w.head == (0.0, 0.0) and len(fake.sent) == 1, "(moves %s)" % fake.moves)

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
    raster_row = w.layers_panel.rows[w._default_layer["raster"].id]
    cut_row = w.layers_panel.rows[w._default_layer["cut"].id]
    before = raster_row["time"].text()
    calc_shown = not raster_row["calc"].isHidden()
    vcut = cut_row["time"].text()
    w.calculate_raster_time()
    run_until_idle(app, w)
    raster_row = w.layers_panel.rows[w._default_layer["raster"].id]
    after = raster_row["time"].text()
    check("time estimate", before == "" and calc_shown and after not in ("", "?") and vcut.endswith("s")
          and raster_row["calc"].isHidden(), "(raster %r -> %r, cut %r, total %r)"
          % (before, after, vcut, w.layers_panel.total_label.text()))

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

    # 11. editor: two elements, drag one, the job first moves the head to the design
    w = make_window(include_Reng="0")
    w.load_design(os.path.join(FIX, "shapes.dxf"))                  # 60 x 40 mm at home
    w.load_design(os.path.join(FIX, "sample.ngc"), add=True)        # G-code replaces, never combines
    only_gcode = len(w.elements) == 1 and w.elements[0].name == "sample.ngc"
    w.load_design(os.path.join(FIX, "shapes.dxf"))
    w.head = (2.0, -1.0)
    w.load_design(os.path.join(FIX, "shapes.dxf"), add=True)        # second copy placed at the head
    a, b = w.elements
    w._preview_moved(a, 1.0, -0.5)                                  # drag the first one
    fake = FakeK40()
    w.laser.k40 = fake
    w.head = (0.0, 0.0)
    w.start_job()
    run_until_idle(app, w)
    check("editor: G-code is not combined", only_gcode)
    check("editor: two elements, head moves to the design first",
          (a.x, a.y) == (1.0, -0.5) and (b.x, b.y) == (2.0, -1.0) and w.origin == (1.0, -0.5)
          and fake.moves[:1] == [(1000, -500)] and len(fake.sent) == 1,
          "(origin %s, moves %s)" % (w.origin, fake.moves))

    # 12. place at head, rotate 90, delete
    w.laser.k40 = None
    w.head = (3.0, -2.0)
    w.place_at_head()
    placed = w.origin == (3.0, -2.0)
    w.selected = b
    size_before = b.size
    w.rotate_selected(90)
    rotated = abs(b.size[0] - size_before[1]) < 1e-9 and abs(b.size[1] - size_before[0]) < 1e-9
    w.delete_selected()
    check("editor: place at head, rotate 90, delete", placed and rotated and w.elements == [a]
          and w.selected is None)

    # 13. undo / redo, duplicate, hide, centre, snap to grid, arrow-key nudge
    w = make_window(include_Reng="0")
    w.load_design(os.path.join(FIX, "shapes.dxf"))                  # 60 x 40 mm
    e = w.elements[0]
    w._preview_moved(e, 1.0, -1.0)
    w.undo()
    undo_ok = (e.x, e.y) == (0.0, 0.0)
    w.redo()
    redo_ok = (e.x, e.y) == (1.0, -1.0)
    w.duplicate_selected()
    dup = w.selected
    dup_ok = len(w.elements) == 2 and dup is not e and dup.design is e.design
    w.undo()
    undo_dup_ok = len(w.elements) == 1
    w.redo()
    w.elements[1].visible = False
    w._compiled = None
    hidden_ok = w.design is e.design or w.design.bounds == e.design.bounds   # only e compiled
    w.selected = e
    w.center_on_bed()
    bed_w, bed_h = 325 / 25.4, 220 / 25.4
    cx, cy = e.centre
    centre_ok = abs(cx - bed_w / 2) < 1e-9 and abs(cy + bed_h / 2) < 1e-9
    w.set_grid(5)
    w._preview_moved(e, 0.123, -0.077)
    g = 5 / 25.4
    snap_ok = abs(e.x / g - round(e.x / g)) < 1e-9 and abs(e.y / g - round(e.y / g)) < 1e-9
    x0 = e.x
    w.preview.select_element(e)
    from PySide6.QtCore import Qt as _Qt
    from PySide6.QtTest import QTest
    QTest.keyClick(w.preview, _Qt.Key_Right)
    nudge_ok = abs((e.x - x0) - g) < 1e-9
    QTest.keyClick(w.preview, _Qt.Key_Right, _Qt.ShiftModifier)
    nudge10_ok = abs((e.x - x0) - 11 * g) < 1e-9
    check("editor: undo/redo", undo_ok and redo_ok and undo_dup_ok)
    check("editor: duplicate, hidden element left out of the job", dup_ok and hidden_ok)
    check("editor: centre on bed, snap to grid, arrow keys", centre_ok and snap_ok and nudge_ok and nudge10_ok,
          "(centre %s, snap %s, nudge %s/%s)" % (centre_ok, snap_ok, nudge_ok, nudge10_ok))

    # 14. drawing tools: shapes drawn in the bed view, edited from the options bar
    from PySide6.QtCore import QPointF
    w = make_window()
    w._preview_drawn("rectangle", QPointF(10, 10), QPointF(50, 30), False)
    rect = w.selected
    w._preview_drawn("ellipse", QPointF(60, 10), QPointF(80, 40), True)      # Shift: circle
    circle = w.selected
    w._preview_drawn("line", QPointF(10, 50), QPointF(60, 52), True)         # Shift: horizontal
    line = w.selected
    w._preview_drawn("text", QPointF(10, 70), QPointF(10, 70), False)
    text = w.selected
    sizes = [tuple(round(v * 25.4, 1) for v in e.size) for e in (rect, circle, line)]
    drawn_ok = (sizes[0] == (40.0, 20.0) and sizes[1] == (30.0, 30.0) and sizes[2][1] == 0.0
                and abs(rect.x * 25.4 - 10) < 1e-6 and abs(rect.y * 25.4 + 10) < 1e-6
                and text.design.raster.image is not None and w.preview.tool == "select")
    check("draw: rectangle, Shift-circle, Shift-line, text", drawn_ok, "(%s)" % sizes)
    w.selected = rect
    w._update_tool_options(force=True)
    spec = rect.shape.copy()
    spec.operation = "engrave"
    spec.corner_radius = 4
    w._tool_options_changed(spec)
    engraved = bool(rect.design.vector_engrave.ecoords) and not rect.design.vector_cut.ecoords
    w.selected = text
    w._update_tool_options(force=True)
    spec = text.shape.copy()
    spec.text = "Kerfly"
    w._tool_options_changed(spec)
    wider = text.size[0] > 0 and text.shape.text == "Kerfly"
    w.undo()
    undone = text.shape.text != "Kerfly"
    out = tempfile.mktemp(suffix=".egv")
    w.start_job(output_file=out)
    run_until_idle(app, w)
    check("draw: options bar edits (operation, radius, text) and undo",
          engraved and wider and undone and os.path.exists(out) and os.path.getsize(out) > 1000)

    # 15. layers: an extra cut layer for a second element, materials, undo
    w = make_window(include_Reng="0", include_Veng="0")
    w.load_design(os.path.join(FIX, "shapes.dxf"))
    w.head = (3.0, 0.0)
    w.load_design(os.path.join(FIX, "shapes.dxf"), add=True)          # selected
    second = w.selected
    n_rows = len(w.layers_panel.rows)
    extra = w.add_layer("cut")                                         # appended, nothing moved yet
    appended = len(w.layers_panel.rows) == n_rows + 1 and "cut" not in second.layers
    w._assign_layer("cut", extra.id)                                   # Layer choice above the bed
    assigned = appended and second.layers.get("cut") == extra.id
    extra.speed = 3.0
    extra.passes = 2
    w._layer_changed(extra)
    rows_ok = extra.id in w.layers_panel.rows and w._default_layer["cut"].id in w.layers_panel.rows
    out = tempfile.mktemp(suffix=".egv")
    w.start_job(output_file=out)
    run_until_idle(app, w)
    two_layers = os.path.getsize(out)
    w._assign_layer("cut", w._default_layer["cut"].id)                 # back via the bar above the bed
    back = "cut" not in second.layers
    w.undo()
    undone = second.layers.get("cut") == extra.id
    w.remove_layer(extra)
    removed = extra not in w.layers and "cut" not in second.layers
    check("layers: extra cut layer, assignment, undo, delete", assigned and rows_ok and back and undone
          and removed and two_layers > 1000, "(egv %d bytes)" % two_layers)
    plywood = [i for i, m in enumerate(w.materials) if m.name.startswith("Plywood 3")][0]
    w.apply_material(plywood)
    cut = w._default_layer["cut"]
    check("materials: applying a material sets the layers", cut.speed == 8.0 and cut.passes == 1
          and w.values["Vcut_feed"] == "8" and abs(cut.power - 0.6) < 1e-9,
          "(cut speed %s, Vcut_feed %s)" % (cut.speed, w.values["Vcut_feed"]))

    # 16. project file: save a layout and open it again in a new window
    from kerfly.gui import image_dialog as _imgdlg
    png2 = tempfile.mktemp(suffix=".png")
    synthetic_image().save(png2, dpi=(300, 300))
    w = make_window()
    w.load_design(os.path.join(FIX, "shapes.svg"))
    _imgdlg.ImageSizeDialog.exec = lambda self: True
    w.head = (4.2, -0.2)
    w.load_design(png2, add=True)
    w._rotate(w.selected, 30)
    w._preview_drawn("rectangle", QPointF(120, 100), QPointF(170, 130), False)
    w._assign_layer("cut", w.add_layer("cut").id)
    extra_id = w.selected.layers["cut"]
    w._preview_drawn("text", QPointF(20, 150), QPointF(20, 150), False)
    spec = w.selected.shape.copy()
    spec.text = "Kerfly"
    w._tool_options_changed(spec)
    title_dirty = w.windowTitle().startswith("*")
    egv1 = tempfile.mktemp(suffix=".egv")
    w.start_job(output_file=egv1)
    run_until_idle(app, w)
    proj = tempfile.mktemp(suffix=".kerfly")
    saved = w._write_project(proj)
    title_clean = not w.windowTitle().startswith("*")
    asked = []
    _imgdlg.ImageSizeDialog.exec = lambda self: (asked.append("image"), True)[1]
    w2 = make_window()
    w2.open_project(proj)
    egv2 = tempfile.mktemp(suffix=".egv")
    w2.start_job(output_file=egv2)
    run_until_idle(app, w2)
    same = open(egv1, "rb").read() == open(egv2, "rb").read()
    layout_same = [(e.name, round(e.x, 9), round(e.y, 9), e.rotation) for e in w.elements] == \
        [(e.name, round(e.x, 9), round(e.y, 9), e.rotation) for e in w2.elements]
    extra2 = [l for l in w2.layers if l.kind == "cut"]
    check("project: save and reopen gives the same layout and laser data",
          saved and title_dirty and title_clean and same and layout_same and not asked
          and len(extra2) == 2 and w2.elements[2].layers.get("cut") == extra2[1].id,
          "(egv %d bytes, same %s, asked %s)" % (os.path.getsize(egv1), same, asked))
    os.remove(png2)

    # 17. SVG without Inkscape: built-in renderer
    w = make_window(use_inkscape="0")
    w.load_design(os.path.join(FIX, "shapes.svg"))
    out = tempfile.mktemp(suffix=".egv")
    w.start_job(output_file=out)
    run_until_idle(app, w)
    # The built-in renderer anti-aliases edges slightly differently from Inkscape,
    # so after halftoning a few dots move: compare closely, not byte for byte.
    size = os.path.getsize(out) if os.path.exists(out) else 0
    ref_size = manifest["svg_raster_vector_cut"]["size"]
    if INKSCAPE:
        from PIL import ImageChops
        from kerfly.core import loaders as _loaders
        from kerfly.core.design import Design as _Design
        ref = _Design()
        _loaders.load_svg(os.path.join(FIX, "shapes.svg"), ref, inkscape_path=INKSCAPE)
        from kerfly.gui.svg_render import render_svg as _render_svg
        built = _Design()                       # freshly loaded: a job reorders the cut paths in place
        _loaders.load_svg(os.path.join(FIX, "shapes.svg"), built, svg_renderer=_render_svg, use_inkscape=False)
        diff = ImageChops.difference(ref.raster.image, built.raster.image)
        hist = diff.histogram()
        changed = sum(hist[1:])
        worst = max((v for v in range(256) if hist[v]), default=0)
        vectors_same = (ref.vector_cut.ecoords == built.vector_cut.ecoords
                        and ref.vector_engrave.ecoords == built.vector_engrave.ecoords)
        check("SVG without Inkscape: same vectors, raster within anti-aliasing tolerance",
              vectors_same and worst <= 32 and changed < 0.001 * ref.raster.image.width * ref.raster.image.height
              and abs(size - ref_size) < 0.01 * ref_size,
              "(%d edge pixels differ, max %d/255; EGV %d vs %d bytes)" % (changed, worst, size, ref_size))
    else:
        check("SVG without Inkscape: job size close to the Inkscape baseline", abs(size - ref_size) < 0.01 * ref_size,
              "(EGV %d vs %d bytes)" % (size, ref_size))
    errors = []
    QMessageBox.critical = staticmethod(lambda *a, **k: errors.append(a[2] if len(a) > 2 else ""))
    red_text = tempfile.mktemp(suffix=".svg")
    open(red_text, "w").write('<svg xmlns="http://www.w3.org/2000/svg" width="50mm" height="20mm" '
                              'viewBox="0 0 50 20"><text x="2" y="15" fill="none" stroke="#ff0000">Hi</text></svg>')
    w.load_design(red_text)
    check("SVG without Inkscape: cut text gives a clear message",
          len(errors) == 1 and "paths" in errors[0], "(%s)" % errors)
    os.remove(red_text)

    # 18. material library import through the Settings menu
    from kerfly.core import materials as _ml
    lib_file = tempfile.mktemp(suffix=".json")
    _ml.export_library([_ml.Material("Test board 2 mm", 2.0, "", {"cut": _ml.OperationSettings(7.0, 2, 0.5)})],
                       lib_file)
    w = make_window()
    n_before = len(w.materials)
    QFileDialog.getOpenFileName = staticmethod(lambda *a, **k: (lib_file, ""))
    QMessageBox.information = staticmethod(lambda *a, **k: None)
    w.import_materials()
    names = [m.name for m in w.materials]
    saved = os.path.isfile(_ml.library_path())
    check("materials: import adds to the library and saves it", len(w.materials) == n_before + 1
          and "Test board 2 mm" in names and saved, "(%d materials)" % len(w.materials))
    os.remove(lib_file)

    # 19. element outside the work area: drawn red, Start and Trace locked
    w = make_window()
    w.load_design(os.path.join(FIX, "shapes.dxf"))
    ok_before = w.btn_start.isEnabled() and not w.bed_warning.isVisibleTo(w)
    e = w.elements[0]
    e.x = 100.0                                                        # far right of any bed
    w._layout_changed()
    item = w.preview._items[0]
    locked = (not w.btn_start.isEnabled() and not w.btn_trace.isEnabled() and not w.act_start.isEnabled()
              and w.bed_warning.isVisibleTo(w) and item.off_bed())
    w.start_job(output_file=tempfile.mktemp(suffix=".egv"))
    not_started = w.worker is None
    e.x = 0.0
    w._layout_changed()
    unlocked = w.btn_start.isEnabled() and not w.bed_warning.isVisibleTo(w) and not w.preview._items[0].off_bed()
    check("outside the work area: red, Start/Trace locked, unlocked when back",
          ok_before and locked and not_started and unlocked)

    # 21. mirror, align, distribute from the window (several selected elements)
    w = make_window()
    w.load_design(os.path.join(FIX, "shapes.dxf"))
    for x0, y0 in ((120, 20), (170, 60), (250, 100)):
        w._preview_drawn("rectangle", QPointF(x0, y0), QPointF(x0 + 20, y0 + 15), False)
    shapes = w.elements[1:]
    w.preview.select_element(shapes)
    w.align_selected("top")
    tops = [round(e.bounds[3], 6) for e in shapes]
    still_selected = len(w._selection()) == 3
    w.distribute_selected(True)
    gaps = [round(shapes[i + 1].bounds[0] - shapes[i].bounds[1], 6) for i in range(2)]
    w.undo()
    undone = [round(e.bounds[0] - shapes[0].bounds[1], 6) for e in shapes[1:2]] != gaps[:1]
    w.preview.select_element(w.elements[0])
    before = w.elements[0].scale_x
    w.mirror_selected(True)
    mirrored = w.elements[0].scale_x == -before
    check("arrange: align top, distribute, undo, mirror", len(set(tops)) == 1 and still_selected
          and gaps[0] == gaps[1] and undone and mirrored, "(tops %s, gaps %s)" % (tops, gaps))

    # 22. polyline tool: clicks in the bed view, close on the first point; open with Enter; saved in projects
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    w = make_window()
    w.resize(1200, 800)
    w.show()
    app.processEvents()
    w.preview.fit_all()                  # the whole bed in view, also on small test screens
    app.processEvents()
    view = w.preview
    w.set_tool("polyline")

    def click(x, y, mods=Qt.NoModifier):
        pos = view.mapFromScene(QPointF(x, y))
        QTest.mouseMove(view.viewport(), pos)
        QTest.mouseClick(view.viewport(), Qt.LeftButton, mods, pos)
        app.processEvents()

    for x, y in ((50, 50), (110, 50), (80, 100)):
        click(x, y)
    click(50, 50)                                                      # first point again: closes
    closed_el = w.elements[-1] if w.elements else None
    closed_ok = (closed_el is not None and closed_el.shape.kind == "polyline" and closed_el.shape.closed_path
                 and len(closed_el.shape.points) == 3 and abs(closed_el.size[0] * 25.4 - 60) < 0.5)
    w.set_tool("polyline")
    for x, y in ((150, 40), (190, 40), (190, 90)):
        click(x, y)
    QTest.keyClick(view.viewport(), Qt.Key_Return)
    app.processEvents()
    open_el = w.elements[-1]
    open_ok = (open_el is not closed_el and not open_el.shape.closed_path and len(open_el.shape.points) == 3
               and open_el.design.vector_cut.ecoords)
    proj = tempfile.mktemp(suffix=".kerfly")
    from kerfly.core import project as _project
    _project.save_project(proj, w.elements, w.layers)
    data, _folder = _project.read_project(proj)
    reread = _project.shape_from_item(data["elements"][0])
    check("polyline: click corners, close on the first point, Enter for open, saved in project",
          closed_ok and open_ok and reread.points == closed_el.shape.points and reread.closed_path,
          "(%d elements, closed %s, open %s, viewport %s)" % (len(w.elements), closed_ok, open_ok,
                                                             view.viewport().size().toTuple()))
    w.close()

    # 23. object snapping: drawing starts on another shape's corner; dragging snaps an element to it
    w = make_window(grid_mm="0")
    w.resize(1200, 800)
    w.show()
    app.processEvents()
    w.preview.fit_all()                  # the whole bed in view, also on small test screens
    app.processEvents()
    w._preview_drawn("rectangle", QPointF(20, 20), QPointF(60, 50), False)
    view = w.preview
    p = view.snap_point(QPointF(60.4, 49.7))
    corner = abs(p.x() - 60) < 1e-6 and abs(p.y() - 50) < 1e-6 and view._snap_marker is not None
    w.toggle_snap_objects(False)
    free = view.snap_point(QPointF(60.4, 49.7))
    off = abs(free.x() - 60.4) < 1e-6
    w.toggle_snap_objects(True)
    w._preview_drawn("rectangle", QPointF(100, 100), QPointF(120, 120), False)
    second = view._items[-1]
    view.scene().clearSelection()
    second.setSelected(True)
    second._dragging = True
    r = second.sceneBoundingRect()                                     # top-left near the first one's corner
    second.setPos(second.pos() + QPointF(60.5 - r.left(), 50.4 - r.top()))
    second._dragging = False
    r = second.sceneBoundingRect()
    dragged = abs(r.left() - 60) < 1e-6 and abs(r.top() - 50) < 1e-6 and view.last_move_snapped
    check("snapping: draw from a corner, off switch, drag onto another element",
          corner and off and dragged, "(left %.3f)" % second.sceneBoundingRect().left())
    view.last_move_snapped = False
    w.close()

    # 24. node tool: move a node of a rotated rectangle, insert, curve, smooth, delete, close, undo, snap
    from kerfly.core import curves as _curves
    w = make_window(grid_mm="0")
    w.resize(1200, 800)
    w.show()
    app.processEvents()
    w.preview.fit_all()                  # the whole bed in view, also on small test screens
    app.processEvents()
    w._preview_drawn("rectangle", QPointF(40, 40), QPointF(80, 70), False)    # 40 x 30 mm
    rect = w.elements[-1]
    w._rotate(rect, 90)
    w.set_tool("nodes")
    view = w.preview
    ed = view.node_editor
    view.select_element(rect)
    app.processEvents()
    four = len(view.node_scene_points()) == 4
    before = view.node_scene_points()
    _curves.move_node(ed.path, 0, 0, before[0].x() - 10, before[0].y() - 5)
    ed.commit()
    after = view.node_scene_points()
    moved_ok = (rect.shape.kind == "path" and rect.rotation == 90 and abs(after[0].x() - before[0].x() + 10) < 1e-6
                and abs(after[0].y() - before[0].y() + 5) < 1e-6
                and all(abs(a.x() - b.x()) < 1e-6 and abs(a.y() - b.y()) < 1e-6 for a, b in zip(after[1:], before[1:])))
    mid = (after[1] + after[2]) / 2.0
    inserted = ed.insert_at(mid) and len(view.node_scene_points()) == 5 and w.tool_options.spec.kind == "path"
    ed.select({(0, 1)})
    curved = ed.action("curve") and any(n[4] is not None for n in rect.shape.subpaths[0]["nodes"])
    ed.select({(0, 1)})
    smoothed = ed.action("smooth") and _curves._is_smooth(rect.shape.subpaths[0]["nodes"][1])
    ed.select({(0, 2)})
    deleted = ed.action("delete") and len(view.node_scene_points()) == 4
    ed.select({(0, 0)})
    opened = ed.action("close") and not rect.shape.subpaths[0]["closed"]
    w.undo(); w.undo(); w.undo(); w.undo(); w.undo(); w.undo()
    undone = (rect.shape.kind == "rectangle") if rect in w.elements else w.elements[-1].shape.kind == "rectangle"
    # snapping while dragging a node: onto its own corner, and in line with another one
    view.select_element(w.elements[-1])
    pts = view.node_scene_points()
    own = ed._snap(pts[2] + QPointF(0.3, 0.3), (0, 0))
    own_ok = abs(own.x() - pts[2].x()) < 1e-6 and abs(own.y() - pts[2].y()) < 1e-6
    far = pts[1] + QPointF(15, 0.4)
    lined = ed._snap(far, (0, 0))
    in_line = abs(lined.y() - pts[1].y()) < 1e-6 and abs(lined.x() - far.x()) < 1e-6
    view._remove_guides()
    view.hide_snap_marker()
    w._preview_drawn("text", QPointF(20, 120), QPointF(20, 120), False)
    w.set_tool("nodes")
    view.select_element(w.elements[-1])
    no_text_nodes = not view._node_handles
    results = [four, moved_ok, inserted, curved, smoothed, deleted, opened, undone, own_ok, in_line, no_text_nodes]
    check("node tool: move, insert, curve, smooth, delete, open, undo, snap; text has no nodes",
          all(results), "(%s)" % results)
    w.close()

    # 27. pen: click a corner, press and drag a smooth node, close on the first point; node buttons
    from PySide6.QtCore import QEvent, Qt
    from PySide6.QtGui import QMouseEvent
    from PySide6.QtTest import QTest
    w = make_window(grid_mm="0")
    w.resize(1200, 800)
    w.show()
    app.processEvents()
    w.preview.fit_all()                  # the whole bed in view, also on small test screens
    app.processEvents()
    view = w.preview
    w.set_tool("pen")
    vp = view.viewport()

    def at(x, y):
        return view.mapFromScene(QPointF(x, y))

    def drag(x0, y0, x1, y1):
        QTest.mousePress(vp, Qt.LeftButton, Qt.NoModifier, at(x0, y0))
        ev = QMouseEvent(QEvent.MouseMove, QPointF(at(x1, y1)), QPointF(vp.mapToGlobal(at(x1, y1))),
                         Qt.NoButton, Qt.LeftButton, Qt.NoModifier)
        QApplication.sendEvent(vp, ev)
        QTest.mouseRelease(vp, Qt.LeftButton, Qt.NoModifier, at(x1, y1))
        app.processEvents()

    QTest.mouseClick(vp, Qt.LeftButton, Qt.NoModifier, at(60, 60))       # corner
    drag(100, 40, 120, 40)                                                 # smooth node, handles 20 mm
    QTest.mouseClick(vp, Qt.LeftButton, Qt.NoModifier, at(100, 90))      # corner
    QTest.mouseClick(vp, Qt.LeftButton, Qt.NoModifier, at(60, 60))       # first point: close
    app.processEvents()
    pe = w.elements[-1] if w.elements else None
    pen_ok = (pe is not None and pe.shape.kind == "path" and pe.shape.subpaths[0]["closed"]
              and len(pe.shape.subpaths[0]["nodes"]) == 3
              and pe.shape.subpaths[0]["nodes"][1][4] is not None and pe.shape.subpaths[0]["nodes"][0][4] is None)
    w.set_tool("nodes")
    view.select_element(pe)
    view.node_editor.select({(0, 0)})
    w.tool_options.node_action.emit("smooth")
    buttons_ok = pe.shape.subpaths[0]["nodes"][0][4] is not None
    w._update_tool_options(force=True)                                 # rebuild the bar, then select nodes
    try:
        w._node_selection_changed(1)
    except RuntimeError:
        buttons_ok = False
    names = [b.text() for b in w.tool_options.findChildren(QToolButton)]
    proj = tempfile.mktemp(suffix=".kerfly")
    from kerfly.core import project as _project
    _project.save_project(proj, [pe], w.layers)
    data, _folder = _project.read_project(proj)
    back = _project.shape_from_item(data["elements"][0])
    saved_ok = back.kind == "path" and back.subpaths == pe.shape.subpaths
    check("pen: corner, smooth curve by dragging, close; node buttons; saved in projects",
          pen_ok and buttons_ok and len(names) >= 8 and saved_ok, "(%s)" % [pen_ok, buttons_ok, len(names), saved_ok])
    w.close()

    # 28. combine shapes: union, difference (hole), intersection, exclusion
    def two_squares(w):
        for e in list(w.elements):
            w.elements.remove(e)
        w._preview_drawn("rectangle", QPointF(20, 20), QPointF(60, 60), False)    # 40 x 40
        w._preview_drawn("rectangle", QPointF(40, 40), QPointF(80, 80), False)    # overlaps 20 x 20
        w.preview.select_element(w.elements[-2:])
    w = make_window(grid_mm="0")
    w.resize(1200, 800)
    w.show()
    app.processEvents()
    w.preview.fit_all()                  # the whole bed in view, also on small test screens
    app.processEvents()
    sizes = {}
    for op in ("union", "difference", "intersection", "exclusion"):
        two_squares(w)
        w.boolean_selected(op)
        e = w.elements[-1]
        sizes[op] = (len(w.elements), round(e.size[0] * 25.4, 3), round(e.size[1] * 25.4, 3),
                     len(e.shape.subpaths), e.shape.kind)
    ok = (sizes["union"][:4] == (1, 60.0, 60.0, 1) and sizes["difference"][:3] == (1, 40.0, 40.0)
          and sizes["intersection"][:4] == (1, 20.0, 20.0, 1) and sizes["exclusion"][1:3] == (60.0, 60.0)
          and all(v[4] == "path" for v in sizes.values()))
    w.undo()
    check("combine shapes: union, difference, intersection, exclusion", ok and len(w.elements) == 2, str(sizes))
    w.close()

    # 29. freehand: a circle drawn with the mouse becomes a closed smooth path with few nodes
    import math as _m
    w = make_window(grid_mm="0")
    w.resize(1200, 800)
    w.show()
    app.processEvents()
    w.preview.fit_all()                  # the whole bed in view, also on small test screens
    app.processEvents()
    view = w.preview
    vp = view.viewport()
    w.set_tool("freehand")
    pts = [(100 + 30 * _m.cos(a / 60.0 * 2 * _m.pi), 100 + 30 * _m.sin(a / 60.0 * 2 * _m.pi)) for a in range(61)]
    QTest.mousePress(vp, Qt.LeftButton, Qt.NoModifier, view.mapFromScene(QPointF(*pts[0])))
    for x, y in pts[1:]:
        q = view.mapFromScene(QPointF(x, y))
        QApplication.sendEvent(vp, QMouseEvent(QEvent.MouseMove, QPointF(q), QPointF(vp.mapToGlobal(q)),
                                               Qt.NoButton, Qt.LeftButton, Qt.NoModifier))
    QTest.mouseRelease(vp, Qt.LeftButton, Qt.NoModifier, view.mapFromScene(QPointF(*pts[-1])))
    app.processEvents()
    fe = w.elements[-1] if w.elements else None
    fh_ok = (fe is not None and fe.shape.kind == "path" and fe.shape.subpaths[0]["closed"]
             and 6 <= len(fe.shape.subpaths[0]["nodes"]) <= 40 and abs(fe.size[0] * 25.4 - 60) < 2.0)
    check("freehand: drawn circle -> closed smooth path", fh_ok,
          "(%s nodes, %.1f mm wide)" % (len(fe.shape.subpaths[0]["nodes"]) if fe else 0, fe.size[0] * 25.4 if fe else 0))
    w.close()

    # 30. ruler: drag between two snapped corners, distance in the status bar
    w = make_window(grid_mm="0")
    w.resize(1200, 800)
    w.show()
    app.processEvents()
    w.preview.fit_all()
    app.processEvents()
    w._preview_drawn("rectangle", QPointF(40, 40), QPointF(70, 80), False)    # 30 x 40: diagonal 50
    w.set_tool("measure")
    view = w.preview
    vp = view.viewport()
    QTest.mousePress(vp, Qt.LeftButton, Qt.NoModifier, view.mapFromScene(QPointF(40.3, 40.2)))
    q = view.mapFromScene(QPointF(69.8, 79.7))
    QApplication.sendEvent(vp, QMouseEvent(QEvent.MouseMove, QPointF(q), QPointF(vp.mapToGlobal(q)),
                                           Qt.NoButton, Qt.LeftButton, Qt.NoModifier))
    QTest.mouseRelease(vp, Qt.LeftButton, Qt.NoModifier, q)
    msg = w.statusBar().currentMessage()
    check("ruler: snapped corners, 50 mm diagonal", "50.00" in msg or "50,00" in msg, "(%s)" % msg)
    w.close()

    # 31. hatch operation from the options bar
    w = make_window(grid_mm="0")
    w._preview_drawn("rectangle", QPointF(20, 20), QPointF(60, 50), False)
    spec = w.selected.shape.copy()
    spec.operation = "hatch"
    w._tool_options_changed(spec)
    for _i in range(5):
        app.processEvents()
    labels = [l.text() for l in w.tool_options.findChildren(QLabel)]
    e = w.selected
    from kerfly.gui.layers_panel import KIND_NAMES as _KN
    hatch_ok = e.design.vector_engrave.ecoords and not e.design.vector_cut.ecoords and e.shape.operation == "hatch"
    check("hatch: from the options bar, its settings appear, lines go to the engrave layer",
          hatch_ok and any(t in ("Hatch", "Kreskowanie") for t in labels), "(%s)" % labels)
    spec = w.selected.shape.copy()
    spec.operation = "cut"
    w._tool_options_changed(spec)
    for _i in range(5):
        app.processEvents()
    spec = w.tool_options.spec.copy()
    spec.tabs = 2
    w._tool_options_changed(spec)
    labels = [l.text() for l in w.tool_options.findChildren(QLabel)]
    loops = {r[2] for r in w.selected.design.vector_cut.ecoords}
    check("bridges: set in the options bar, the cut has gaps", len(loops) == 2 and "Bridges" in labels,
          "(%d pieces, %s)" % (len(loops), labels))
    w.close()

    # 32. job simulation: dialog plays, draws on the bed view, seek to the end, closes cleanly
    w = make_window(grid_mm="0")
    w._preview_drawn("rectangle", QPointF(20, 20), QPointF(60, 50), False)
    w.simulate_job()
    dlg = getattr(w, "_simulation", None)
    played = dlg is not None and dlg.total > 0 and dlg.timer.isActive()
    auto_speed = dlg.speed.currentData() >= 1
    dlg.skip_layer()
    skipped = dlg.time > 0
    dlg.seek(dlg.total)
    drawn = len(dlg.items) >= 2 and auto_speed and skipped
    dlg.close()
    app.processEvents()
    check("simulation: plays, draws the path, closes", played and drawn, "(%.1f s)" % (dlg.total if dlg else 0))
    w.close()

    # 33. opened DXF: double-click only explains; Ungroup splits it; a part can be dragged and node-edited
    w = make_window(grid_mm="0")
    w.load_design(os.path.join(FIX, "shapes.dxf"))
    src = w.elements[0]
    w._edit_nodes_of(src)
    explained = len(w.elements) == 1 and w.preview.tool == "select" and "Ungroup" in w.statusBar().currentMessage()
    w.preview.scene().clearSelection()
    w.ungroup_selected()                                                # nothing selected, one file: that one
    parts = list(w.elements)
    split = len(parts) > 1 and all(e.shape.kind == "path" and not e.group for e in parts)
    w.preview.select_element(parts[0])
    single = w._selection() == [parts[0]]
    x1 = parts[1].x
    w._preview_moved(parts[0], 0.3, 0.0)
    moved_alone = abs(parts[1].x - x1) < 1e-12
    w._edit_nodes_of(parts[0])
    app.processEvents()
    nodes_ok = w.preview.tool == "nodes" and bool(w.preview._node_handles)
    check("opened DXF: Ungroup splits it, a part moves alone, double-click edits its nodes",
          explained and split and single and moved_alone and nodes_ok,
          "(%s)" % [explained, split, single, moved_alone, nodes_ok])
    w.close()

    # 35. element list and bed selection follow each other (one, several, a group)
    w = make_window(grid_mm="0")
    for x0 in (20, 70, 120):
        w._preview_drawn("rectangle", QPointF(x0, 20), QPointF(x0 + 30, 50), False)
    e1, e2, e3 = w.elements
    lst = w.element_list

    def rows():
        return sorted(lst.row(i) for i in lst.selectedItems())
    w.preview.select_element(e2)
    one = rows() == [1]
    w.preview.select_element([e1, e3])
    several = rows() == [0, 2]
    lst.clearSelection()
    lst.item(2).setSelected(True)
    from_list = w.preview.selected_elements() == [e3] and w.selected is e3
    w.preview.select_element([e1, e2])
    w.group_selected()
    lst.clearSelection()
    lst.item(0).setSelected(True)                                       # a group member: the whole group
    group_rows = rows() == [0, 1] and len(w.preview.selected_elements()) == 2
    check("element list <-> bed selection: one, several, from the list, a group",
          one and several and from_list and group_rows, "(%s)" % [one, several, from_list, group_rows])
    w.close()

    # 36. zoom: the wheel cannot zoom out past the whole bed; zooming in works; the bed stays in view
    from PySide6.QtCore import QPoint as _QP
    from PySide6.QtGui import QWheelEvent
    w = make_window(grid_mm="0")
    w.resize(1200, 800)
    w.show()
    app.processEvents()
    v = w.preview
    v.fit_all()
    fit = v.transform().m11()

    def wheel(n):
        for _i in range(abs(n)):
            pos = QPointF(v.viewport().rect().center())
            ev = QWheelEvent(pos, QPointF(v.viewport().mapToGlobal(pos.toPoint())), _QP(0, 0),
                             _QP(0, 120 if n > 0 else -120), Qt.NoButton, Qt.NoModifier, Qt.NoScrollPhase, False)
            QApplication.sendEvent(v.viewport(), ev)
    wheel(-10)
    out_limit = abs(v.transform().m11() - fit) < 1e-6
    anchor = v.mapFromScene(QPointF(60, 40))
    under = v.mapToScene(anchor)
    for _i in range(3):
        ev = QWheelEvent(QPointF(anchor), QPointF(v.viewport().mapToGlobal(anchor)), _QP(0, 0), _QP(0, 120),
                         Qt.NoButton, Qt.NoModifier, Qt.NoScrollPhase, False)
        QApplication.sendEvent(v.viewport(), ev)
    after = v.mapToScene(anchor)
    zoomed_in = v.transform().m11() > fit * 1.9 and abs(after.x() - under.x()) < 1 and abs(after.y() - under.y()) < 1
    ev = QWheelEvent(QPointF(anchor), QPointF(v.viewport().mapToGlobal(anchor)), _QP(0, 0), _QP(0, -120),
                     Qt.NoButton, Qt.NoModifier, Qt.NoScrollPhase, False)
    QApplication.sendEvent(v.viewport(), ev)                            # one step out: still about the cursor
    out_pt = v.mapToScene(anchor)
    zoomed_in = zoomed_in and abs(out_pt.x() - under.x()) < 1 and abs(out_pt.y() - under.y()) < 1
    wheel(-10)
    back = abs(v.transform().m11() - fit) < 1e-6 and v._bed_visible()
    check("zoom: not further out than the whole bed, zooms in and out about the cursor", out_limit and zoomed_in and back,
          "(%s)" % [out_limit, zoomed_in, back])
    w.close()

    # 37. a drawn shape can go on any layer of the left panel; its operation follows the layer's kind
    w = make_window(grid_mm="0")
    w._preview_drawn("rectangle", QPointF(20, 20), QPointF(60, 50), False)
    e = w.selected
    extra = w.add_layer("cut")
    combo = w.layer_assign_box.findChildren(QComboBox)[0]
    names = [combo.itemText(i) for i in range(combo.count())]
    eng = [l for l in w.layers if l.kind == "engrave"][0]
    w._assign_shape_layer(eng.id)
    to_outline = e.shape.operation == "engrave" and bool(e.design.vector_engrave.ecoords) and not e.design.vector_cut.ecoords
    w._assign_shape_layer(extra.id)
    to_extra_cut = e.shape.operation == "cut" and e.layers.get("cut") == extra.id
    w.undo()
    undone = e.shape.operation == "engrave" if e in w.elements else w.elements[-1].shape.operation == "engrave"
    check("shape layer: all layers listed, outline layer makes it an outline, extra cut layer, undo",
          len(names) >= 4 and to_outline and to_extra_cut and undone, "(%s, %s)" % (names, [to_outline, to_extra_cut, undone]))
    w.close()

    # 38. Ungroup an SVG: lines become shapes, the picture splits into its separate parts, same place
    w = make_window(grid_mm="0", use_inkscape="0")
    w.load_design(os.path.join(FIX, "shapes.svg"))
    src = w.elements[0]
    src.rotation = 0.0
    from kerfly.core.layout import compile_layout as _cl2

    def dark_box(elements):
        d, o = _cl2(elements, passthrough=False)
        im = d.raster.image.convert("L").point(lambda v: 255 if v < 128 else 0)
        l, t, r, b = im.getbbox()
        dpi = d.input_dpi
        return (o[0] + l / dpi, o[1] - t / dpi, o[0] + r / dpi, o[1] - b / dpi)
    before = dark_box([src])
    w.preview.select_element(src)
    w.ungroup_selected()
    pics = [e for e in w.elements if e.shape is None]
    shapes = [e for e in w.elements if e.shape is not None]
    after = dark_box(pics)
    same = max(abs(a - b) for a, b in zip(before, after)) < 0.012          # inches (0.3 mm)
    proj = tempfile.mktemp(suffix=".kerfly")
    w._write_project(proj) if hasattr(w, "_write_project") else None
    check("ungroup SVG: picture split into its parts in the same place, lines into shapes",
          len(pics) == 3 and len(shapes) >= 4 and same, "(%d pictures, %d shapes, %s / %s)"
          % (len(pics), len(shapes), [round(v, 3) for v in before], [round(v, 3) for v in after]))
    w.undo()
    check("ungroup SVG: undo gives the file back", w.elements == [src])
    w.close()

    # 25. groups: select one selects all, move, rotate and duplicate together, saved, ungroup, undo
    w = make_window(grid_mm="0")
    w.resize(1200, 800)
    w.show()
    app.processEvents()
    w.preview.fit_all()                  # the whole bed in view, also on small test screens
    app.processEvents()
    for x0 in (20, 60, 100):
        w._preview_drawn("rectangle", QPointF(x0, 20), QPointF(x0 + 20, 40), False)
    a, b, c = w.elements[-3:]
    w.preview.select_element([a, b])
    w.group_selected()
    grouped = a.group and a.group == b.group and not c.group
    w.preview.select_element(a)                                         # one click selects the group
    whole = set(map(id, w.preview.selected_elements())) == {id(a), id(b)}
    bx, by = b.x, b.y
    w._preview_moved(a, 0.5, -0.25)
    moved = abs(b.x - bx - 0.5) < 1e-9 and abs(b.y - by + 0.25) < 1e-9
    w.preview.select_element(a)
    w.rotate_selected(90)
    turned = a.rotation == 90 and b.rotation == 90 and abs(a.centre[0] - b.centre[0]) < 1e-9
    w.preview.select_element(a)
    n = len(w.elements)
    w.duplicate_selected()
    copies = w.elements[n:]
    dup = len(copies) == 2 and copies[0].group == copies[1].group and copies[0].group != a.group
    proj = tempfile.mktemp(suffix=".kerfly")
    from kerfly.core import project as _project
    _project.save_project(proj, w.elements, w.layers)
    data, _folder = _project.read_project(proj)
    saved = [it.get("group") for it in data["elements"]] == [e.group for e in w.elements]
    w.preview.select_element(a)
    w.ungroup_selected()
    ungrouped = not a.group and not b.group and copies[0].group
    w.undo()
    regrouped = a.group and a.group == b.group
    check("groups: select, move, rotate, duplicate, save, ungroup, undo",
          grouped and whole and moved and turned and dup and saved and ungrouped and regrouped,
          "(%s)" % [grouped, whole, moved, turned, dup, saved, ungrouped, regrouped])
    w.close()

    # 26. break apart an opened file: one polyline per path, same place, grouped; image part stays; undo
    w = make_window(grid_mm="0")
    w.load_design(os.path.join(FIX, "shapes.dxf"))
    src = w.elements[0]
    src.rotation = 30.0
    w._layout_changed()
    before = w.preview._items[0].snap_shape()
    pts_before = sorted((round(x, 3), round(y, 3)) for x, y, k in before.points if k == "corner")[:6]
    from kerfly.core.layout import compile_layout as _cl
    def bed_points(elements):
        d, o = _cl(elements)
        return sorted({(round(r[0] + o[0], 4), round(r[1] + o[1], 4)) for r in d.vector_cut.ecoords + d.vector_engrave.ecoords})
    ref_pts = bed_points([src])                                 # rotated: coordinates on the bed
    w.preview.select_element(src)
    w.ungroup_selected()                                                # an opened file splits into shapes
    parts = list(w.elements)
    one_group = len(parts) > 1 and all(not e.group for e in parts) and all(e.shape.kind == "path" for e in parts)
    curved = any(n[4] is not None for e in parts for sp in e.shape.subpaths for n in sp["nodes"])   # real arcs
    corners = set()
    for item in w.preview._items:
        corners |= {(round(x, 3), round(y, 3)) for x, y, k in item.snap_shape().points if k == "corner"}
    new_pts = bed_points(parts)

    def box(pts):
        return (min(p[0] for p in pts), max(p[0] for p in pts), min(p[1] for p in pts), max(p[1] for p in pts))
    same_place = max(abs(a - b) for a, b in zip(box(ref_pts), box(new_pts))) < 0.003
    w.undo()
    back = len(w.elements) == 1 and w.elements[0] is src
    check("ungroup a file: separate curves in the same place, undo", one_group and curved and same_place and back,
          "(%d parts)" % len(parts))

    # 20. diagnostic log and report
    from kerfly.core import diag as _diag
    _diag.setup("test")
    _diag.log.info("laser: test entry for the report")
    report = tempfile.mktemp(suffix=".txt")
    QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: (report, ""))
    w.save_report()
    text = open(report, encoding="utf-8").read() if os.path.exists(report) else ""
    check("diagnostic report: checks, settings and log", "Kerfly diagnostic report" in text
          and "== Checks" in text and "board_name = " in text and "laser: test entry for the report" in text,
          "(%d bytes)" % len(text))

    # 39. a status message repeated by the laser library is logged once (it filled the log on the
    # first laser test); progress percentages fill the progress bar; an interrupted job warns
    before = _diag.read_log().count("Waiting for the laser to finish.")
    for _i in range(5):
        w.status("Waiting for the laser to finish.")
    after = _diag.read_log().count("Waiting for the laser to finish.")
    check("repeated status logged once", after - before == 1, "(%d new lines)" % (after - before))
    w.set_busy(True)
    w.status("Sending Data to Laser = 42.0%")
    pct = w.progress.value()
    w.status("Creating Scan Lines: 7.5 %")
    pct2 = w.progress.value()
    busy_shown = not w.progress.isHidden() and not w.busy_indicator.isHidden()
    w.set_busy(False)
    check("progress bar follows the percentages", pct == 42 and pct2 == 7 and busy_shown
          and w.busy_indicator.isHidden(), "(%s, %s)" % (pct, pct2))
    from kerfly.gui.worker import LayersJobWorker as _LJW
    for sent in (False, True):
        wk = _LJW(w.elements, w.layers, w.job_settings(), {}, laser=w.laser)
        wk.sending = sent
        w.worker = wk
        w._job_finished(False, "Action Stopped by User.")
        msg = w.statusBar().currentMessage()
        if sent:
            check("stopped job: head position unknown, press Home", "Home" in msg, "(%s)" % msg)
        else:
            check("job refused before sending: no position warning", "Home" not in msg, "(%s)" % msg)

    # 40. Help → Report a problem: saves the report, opens the laser problem form with the version filled in
    from PySide6.QtGui import QDesktopServices as _QDS
    opened = []
    _orig_open, _orig_exec = _QDS.openUrl, QMessageBox.exec
    _QDS.openUrl = staticmethod(lambda url: opened.append(url.toString()) or True)

    def _click(box, wanted=(_("The laser did something wrong"), "Close", _("Close"))):
        for b in box.buttons():
            if b.text().replace("&", "") in wanted:
                b.click()
                break
        return 0
    QMessageBox.exec = _click
    try:
        if os.path.exists(report):
            os.remove(report)
        w.report_problem()
    finally:
        _QDS.openUrl, QMessageBox.exec = _orig_open, _orig_exec
    url = opened[0] if opened else ""
    check("report a problem: report saved, laser form opened with version and board",
          os.path.exists(report) and "issues/new?template=laser_problem.yml" in url
          and "version=" + __import__("kerfly").__version__ in url and "board=" in url, "(%s)" % url[:90])
    check("report a problem: in the Help menu and the toolbar",
          w.act_report_problem in [a for m in w.menuBar().actions() for a in m.menu().actions()]
          and any(getattr(b, "defaultAction", lambda: None)() is w.act_report_problem
                  for b in w.findChildren(QToolButton)))

    # 42. program icon: the logo renders, the bitmap icons exist
    from kerfly.gui import icons as _icons
    ico = os.path.join(ROOT_DIR, "kerfly", "gui", "icons", "kerfly.ico")
    png = os.path.join(ROOT_DIR, "kerfly", "gui", "icons", "kerfly.png")
    app_icon = _icons.app_icon()
    check("program icon: logo renders, kerfly.ico and kerfly.png exist",
          not app_icon.isNull() and not app_icon.pixmap(32, 32).toImage().isNull()
          and app_icon.pixmap(32, 32).toImage().pixelColor(16, 3).alpha() > 0
          and os.path.getsize(ico) > 1000 and os.path.getsize(png) > 1000)

    # 41. "Design follows the head": arrows and Home move the design too, corners only the head,
    # one undo step for switching it on, nothing moves when it is off
    w2 = make_window(follow_head="0", jog_step="10")
    w2.load_design(os.path.join(FIX, "shapes.dxf"))
    start = (w2.elements[0].x, w2.elements[0].y)
    w2.jog(1, 0)
    stays = (w2.elements[0].x, w2.elements[0].y) == start
    undo_before = len(w2._undo)
    w2.act_follow_head.trigger()
    at_head = w2.origin == w2.head and len(w2._undo) == undo_before + 1
    w2.jog(1, 0)
    w2.jog(0, -1)
    follows = w2.origin == w2.head and abs(w2.head[0] - 20 / 25.4) < 0.002 and len(w2._undo) == undo_before + 1
    w2.move_to_corner("LR")
    corner_only = w2.origin != w2.head
    w2.home()
    homed = w2.origin == (0.0, 0.0) == w2.head
    w2.jog(-1, 0)                                         # already at the left edge: stays on the bed
    on_bed = w2.origin == (0.0, 0.0)
    w2.act_follow_head.trigger()
    saved = w2.values["follow_head"] == "0"
    check("design follows the head: arrows, corners, Home, undo, setting",
          stays and at_head and follows and corner_only and homed and on_bed and saved,
          "(%s)" % ([stays, at_head, follows, corner_only, homed, on_bed, saved],))
    w2._dirty = False
    w2.close()
    sys.stdout, sys.stderr = sys.__stdout__, sys.__stderr__

    # Let every worker thread finish: a QThread still running when the process
    # exits crashes it on Windows (access violation in exit).
    import gc
    from PySide6.QtCore import QThread
    running = [t for t in gc.get_objects() if isinstance(t, QThread) and t.isRunning()]
    for t in running:
        t.wait(10000)
    still = [type(t).__name__ for t in running if t.isRunning()]
    check("all worker threads finished", not still, "(%d were running, still: %s)" % (len(running), still))

    # close every window and let Qt delete them before the application goes away
    for top in QApplication.topLevelWidgets():
        if isinstance(top, MainWindow):
            top._dirty = False
        top.close()
        top.deleteLater()
    from PySide6.QtCore import QCoreApplication, QEvent
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    app.processEvents()

    print("\n%d check(s) failed." % failures if failures else "\nAll checks passed.")
    return 1 if failures else 0


if __name__ == "__main__":
    try:
        rc = main()
    except Exception:
        import traceback
        text = traceback.format_exc()
        print(text)
        if os.environ.get("GITHUB_ACTIONS"):
            print("::error title=test_gui crashed::" + text.replace("%", "%25").replace("\n", "%0A"))
        rc = 1
    sys.stdout.flush()
    sys.exit(rc)
