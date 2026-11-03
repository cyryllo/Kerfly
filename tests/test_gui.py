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
    w.add_layer("cut")                                                 # selected element moves to it
    extra = [l for l in w.layers if l.kind == "cut"][1]
    assigned = second.layers.get("cut") == extra.id
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
    w.add_layer("cut")
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

    print("\n%d check(s) failed." % failures if failures else "\nAll checks passed.")
    return 1 if failures else 0


if __name__ == "__main__":
    rc = main()
    sys.stdout.flush()
    os._exit(rc)
