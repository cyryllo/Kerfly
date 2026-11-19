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
import math
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

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtGui import QColor, QImage, QKeySequence, QPainter  # noqa: E402
from PySide6.QtWidgets import QApplication, QComboBox, QWidget, QFileDialog, QInputDialog, QLabel, QMessageBox, QToolButton  # noqa: E402

from kerfly.core import config  # noqa: E402
from kerfly.gui.main_window import MainWindow  # noqa: E402
from fakes import FakeGrbl, FakeK40, run_until_idle  # noqa: E402
from uidriver import bar_set, choose_layer, click_bar_button, select  # noqa: E402

FIX = os.path.join(TESTS_DIR, "fixtures")
BASE = os.path.join(TESTS_DIR, "baseline")


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


def find_inkscape():
    """Inkscape the way Kerfly finds it (PATH or the usual install folders)."""
    import svg_reader
    reader = svg_reader.SVG_READER()
    reader.set_inkscape_path(shutil.which("inkscape"))
    return reader.inkscape_exe or ""


INKSCAPE = find_inkscape()


OPEN_WINDOWS = []          # checked by kerfly.gui.truth after every check (until closed)


def make_window(**overrides):
    values = dict(config.DEFAULT_VALUES)
    values["inkscape_path"] = INKSCAPE
    values.update(overrides)
    w = MainWindow(values)
    OPEN_WINDOWS.append(w)
    close = w.close

    def closed():
        if w in OPEN_WINDOWS:
            OPEN_WINDOWS.remove(w)
        return close()
    w.close = closed
    return w


def main():
    app = QApplication([])
    # "save changes first?" when replacing a design: discard in tests
    QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Discard)
    # the window's questions (kerfly.gui.widgets.ask, with named buttons) answered like QMessageBox.question,
    # which the checks below replace with their answers
    from kerfly.gui import widgets as _widgets
    _widgets.ask = lambda parent, title, text, buttons=QMessageBox.Yes | QMessageBox.No, default=QMessageBox.NoButton, \
        **_k: QMessageBox.question(parent, title, text, buttons, default)
    manifest = json.load(open(os.path.join(BASE, "manifest.json")))["cases"]
    failures = 0

    def check(name, ok, detail=""):
        nonlocal failures
        # every open window must show what its data holds (kerfly.gui.truth)
        from kerfly.gui import truth
        for _i in range(3):
            app.processEvents()                  # widgets added to a shown window appear a moment later
        for n, win in enumerate(list(OPEN_WINDOWS)):
            for problem in truth.check_window(win):
                print("TRUTH [%s] window %d: %s" % (name[:50], n, problem))
                ok = False                       # the window shows something else than it holds
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

    # 3b. boundary trace with the laser on: the M3 board gets the trace power from Settings → Vector
    # (a user asked for it: the power during the trace could not be set)
    w = make_window(board_name="LASER-M3", show_power="1", max_power="30", trace_w_laser="1", Trace_power="0.2")
    w.load_design(os.path.join(FIX, "shapes.dxf"))
    fake = FakeK40()
    w.laser.k40 = fake
    w.start_job(trace=True)
    run_until_idle(app, w)
    powers = [p for p, _d in fake.sent]
    from kerfly.gui.settings_dialog import SettingsDialog as _SD, SettingsForm as _LF
    sd = _LF(dict(w.values, trace_w_laser="0"), machine=True, window=w)          # a laser's settings (Lasers)
    field = sd._widgets["Trace_power"]
    greyed = not field.isEnabled()
    sd._widgets["trace_w_laser"].setChecked(True)
    field.setValue(35)
    stored = sd.result_values()[0]["Trace_power"]
    check("boundary trace with laser on: trace power sent (M3), its field below the tick, greyed out "
          "without it, stored as K40 Whisperer's fraction",
          bool(powers) and all(abs(p - 6.0) < 1e-6 for p in powers) and greyed and field.isEnabled()
          and stored == "0.35", "(%s)" % [powers, greyed, field.isEnabled(), stored])
    sd.close()

    # 3b2. power settings only with the M3 board (the others have no power control: the knob sets it)
    sd = _LF(dict(config.DEFAULT_VALUES, board_name="LASER-M2", trace_w_laser="1", show_power="1"), machine=True)
    wd = sd._widgets
    m2_off = not wd["show_power"].isEnabled() and not wd["max_power"].isEnabled() \
        and not wd["Trace_power"].isEnabled()
    wd["board_name"].setCurrentText("LASER-M3")
    m3_on = wd["show_power"].isEnabled() and wd["max_power"].isEnabled() and wd["Trace_power"].isEnabled()
    wd["show_power"].setChecked(False)
    max_follows = not wd["max_power"].isEnabled() and wd["Trace_power"].isEnabled()
    sd.close()
    check("power settings greyed out without the M3 board (power per operation, maximum power, trace power)",
          m2_off and m3_on and max_follows, "(%s)" % [m2_off, m3_on, max_follows])

    # 3b3. Settings → Raster → Dithering method: the list, greyed out without halftone, a change recomputes
    sd = _SD(dict(config.DEFAULT_VALUES, halftone="0"), None, tab=1)
    combo = sd._widgets["dither"]
    methods = [combo.itemData(i) for i in range(combo.count())]
    greyed = not combo.isEnabled()
    sd._widgets["halftone"].setChecked(True)
    combo.setCurrentIndex(combo.findData("atkinson"))
    chosen = combo.isEnabled() and sd.result_values()[0]["dither"] == "atkinson"
    sd.close()
    from kerfly.gui.settings_dialog import RASTER_KEYS as _RK
    check("Settings → Raster → Dithering method: 8 methods, greyed out without halftone, chosen, recomputes",
          methods[0] == "floyd" and len(methods) == 8 and greyed and chosen and "dither" in _RK,
          "(%s)" % [methods, greyed, chosen])

    # 3c. after a job (K40 Whisperer's Popup Report and Run Batch File): a report window with the job
    # time (on by default, not blocking), a program run after the job with its output in the report,
    # its errors shown even with the report off; nothing after a boundary trace
    def _job_then(w, trace=False):
        w.start_job(trace=trace)
        run_until_idle(app, w)
        t0 = time.time()
        while getattr(w, "_after_job_process", None) is not None and time.time() - t0 < 20:
            app.processEvents()
            time.sleep(0.02)
        app.processEvents()
        box = getattr(w, "_job_report", None)
        return box.text() if box is not None and box.isVisible() else None
    w = make_window()
    w.load_design(os.path.join(FIX, "shapes.dxf"))
    w.laser.k40 = FakeK40()
    plain = _job_then(w)
    non_blocking = getattr(w, "_job_report", None) is not None and not w._job_report.isModal()
    if plain is not None:
        w._job_report.close()
    after_trace = _job_then(w, trace=True)
    tmp_dir = tempfile.mkdtemp(prefix="kerfly_after_job_")
    marker = os.path.join(tmp_dir, "ran.txt")
    if sys.platform == "win32":
        good, bad = os.path.join(tmp_dir, "good.bat"), os.path.join(tmp_dir, "bad.bat")
        open(good, "w").write('@echo off\r\necho done > "%s"\r\necho exhaust off\r\n' % marker)
        open(bad, "w").write("@echo off\r\necho no plug 1>&2\r\nexit /b 3\r\n")
    else:
        good, bad = os.path.join(tmp_dir, "good.sh"), os.path.join(tmp_dir, "bad.sh")
        open(good, "w").write('#!/bin/sh\necho done > "%s"\necho exhaust off\n' % marker)
        open(bad, "w").write("#!/bin/sh\necho no plug >&2\nexit 3\n")
    w.values.update(post_exec="1", batch_path=good)
    with_program = _job_then(w)
    if with_program is not None:
        w._job_report.close()
    w.values.update(post_disp="0", batch_path=bad)
    with_error = _job_then(w)
    w.values.update(post_exec="0", post_disp="0")
    quiet = _job_then(w) if with_error is None else None
    sd = _LF(dict(w.values, rotary="0", post_exec="0"), machine=True, window=w)
    greyed = not sd._widgets["LaserRscale"].isEnabled() and not sd._widgets["batch_path"].isEnabled()
    sd._widgets["rotary"].setChecked(True)
    sd._widgets["post_exec"].setChecked(True)
    on_again = sd._widgets["LaserRscale"].isEnabled() and sd._widgets["rapid_feed"].isEnabled() \
        and sd._widgets["batch_path"].isEnabled()
    sd.close()
    check("after a job: report with the job time (default, not blocking), none after a trace; the program "
          "runs, its output in the report, its error shown even with the report off; rotary and program "
          "fields greyed out without their tick",
          plain is not None and _("Job time: %s") % "" in plain and non_blocking and after_trace is None
          and os.path.isfile(marker) and with_program is not None and "exhaust off" in with_program
          and with_error is not None and "no plug" in with_error and "3" in with_error
          and greyed and on_again,
          "(%s)" % [plain, non_blocking, after_trace, os.path.isfile(marker), with_program, with_error,
                    quiet, greyed, on_again])
    if getattr(w, "_job_report", None) is not None:
        w._job_report.close()

    # 3d. a program before a job (the exhaust on): the job waits for it; when it fails the user is asked,
    # No sends nothing, Yes sends the job; not before a boundary trace
    def _wait_job(w):
        t0 = time.time()
        while (getattr(w, "_before_job_process", None) is not None or w.worker is not None) \
                and time.time() - t0 < 30:
            app.processEvents()
            time.sleep(0.02)
        run_until_idle(app, w)
    w = make_window(post_disp="0")
    w.load_design(os.path.join(FIX, "shapes.dxf"))
    fake = FakeK40()
    w.laser.k40 = fake
    order_file = os.path.join(tmp_dir, "before.txt")
    if sys.platform == "win32":
        before_ok = os.path.join(tmp_dir, "before.bat")
        open(before_ok, "w").write('@echo off\r\necho exhaust on > "%s"\r\n' % order_file)
    else:
        before_ok = os.path.join(tmp_dir, "before.sh")
        open(before_ok, "w").write('#!/bin/sh\necho exhaust on > "%s"\n' % order_file)
    w.values.update(pre_exec="1", pre_batch_path=before_ok)
    sent_at_start = len(fake.sent)
    w.start_job()
    waited = w.worker is None and not fake.sent[sent_at_start:]      # nothing sent before the program ends
    _wait_job(w)
    ran_then_sent = os.path.isfile(order_file) and len(fake.sent) > sent_at_start
    os.remove(order_file)
    w.start_job(trace=True)
    _wait_job(w)
    not_for_trace = not os.path.isfile(order_file)
    asked_before = []
    real_question = QMessageBox.question
    w.values.update(pre_batch_path=bad)
    answers = [QMessageBox.No, QMessageBox.Yes]
    QMessageBox.question = staticmethod(lambda *a, **k: (asked_before.append(a[2] if len(a) > 2 else ""),
                                                         answers.pop(0))[1])
    n = len(fake.sent)
    w.start_job()
    _wait_job(w)
    refused = len(fake.sent) == n
    w.start_job()
    _wait_job(w)
    anyway = len(fake.sent) > n
    QMessageBox.question = real_question
    w.values.update(pre_exec="0")
    check("program before a job: the job waits for it, not before a trace; when it fails the user is "
          "asked (No: nothing sent, Yes: the job runs)",
          waited and ran_then_sent and not_for_trace and len(asked_before) == 2 and "no plug" in asked_before[0]
          and refused and anyway,
          "(%s)" % [waited, ran_then_sent, not_for_trace, asked_before, refused, anyway])

    # 3e. from the 14 Nov notes: Help → Keyboard shortcuts (from the menus, the tools and the mouse, with a
    # filter), a minimum window size, Generators after Settings, no Updates button on the toolbar
    w = make_window()
    w.resize(1200, 800)
    w.show()
    app.processEvents()
    w.act_shortcuts.trigger()
    app.processEvents()
    sc = w._shortcuts
    rows = sc.rows()
    keys = {(c, k) for _s, c, k in rows}
    has_menu = any(k == QKeySequence("Ctrl+N").toString(QKeySequence.NativeText) for _c, k in keys)
    has_tool = any(sec == _("Drawing tools") and k == "S" for sec, _c, k in rows)
    has_mouse = any(sec == _("Mouse and other keys") for sec, _c, _k in rows)
    sc.filter.setText(QKeySequence("Ctrl+G").toString(QKeySequence.NativeText))
    filtered = sc.rows()
    one_window = (w.act_shortcuts.trigger(), app.processEvents(), w._shortcuts is sc)[2]
    sc.close()
    titles = [a.text().replace("&", "") for a in w.menuBar().actions()]
    order_ok = titles.index(_("&Generators").replace("&", "")) == titles.index(_("&Settings").replace("&", "")) + 1
    from PySide6.QtWidgets import QToolBar as _TB
    toolbar = w.findChild(_TB, "main_toolbar")
    on_toolbar = {b.defaultAction() for b in toolbar.findChildren(QToolButton)}
    # the generators in the list under the ribbon's Generators button (docs/ui-mockups/GeneratorsMenu)
    no_updates_button = (w.act_check_updates not in on_toolbar and w.generators_button.menu() is w.generators_menu
                         and w.act_generators["gear"] in w.generators_menu.actions())
    w.resize(400, 300)
    app.processEvents()
    screen = QApplication.primaryScreen().availableGeometry()
    min_ok = w.width() >= min(1024, screen.width()) and w.minimumWidth() >= min(1024, screen.width())
    groups_kept = all(g.width() >= g.minimumWidth() > 0 for g in w._ribbon_groups if g.isVisible())
    check("Help → Keyboard shortcuts: menus, tools and mouse, filter, one window; minimum window size; "
          "Generators after Settings; no Updates button; toolbar groups never squeezed",
          len(rows) > 50 and has_menu and has_tool and has_mouse and 0 < len(filtered) < 5 and one_window
          and order_ok and no_updates_button and min_ok and groups_kept,
          "(%s)" % [len(rows), has_menu, has_tool, has_mouse, filtered, one_window, titles, no_updates_button,
                    w.size().toTuple(), groups_kept])

    # 3e2. dark theme (Settings → View → Theme, after a restart): dark palette, light icons, readable
    # style sheet colours; the light theme back as before
    from kerfly.gui import theme as _theme, icons as _icons
    from PySide6.QtGui import QPalette as _QP
    _theme.apply(app, "dark")
    dark_window = app.palette().color(_QP.Window).lightness() < 80
    dark_text = app.palette().color(_QP.WindowText).lightness() > 180
    pm = _icons.tabler("file").pixmap(32, 32).toImage()
    inked = [pm.pixelColor(x, y) for y in range(32) for x in range(32) if pm.pixelColor(x, y).alpha() > 200]
    light_icons = bool(inked) and min(c.lightness() for c in inked) > 150
    dark_sheet = _theme.TOKENS["dark"]["top_bar"] in app.styleSheet()
    dw = make_window(theme="dark")
    from kerfly.gui.settings_dialog import SettingsDialog as _SD3
    sd = _SD3(dict(dw.values), dw)
    combo = sd._widgets["theme"]
    choices = [combo.itemData(i) for i in range(combo.count())]
    combo.setCurrentIndex(combo.findData("system"))
    stored = sd.result_values()[0]["theme"]
    sd.close()
    dw.close()
    _theme.apply(app, "light")
    pm = _icons.tabler("file").pixmap(32, 32).toImage()
    inked = [pm.pixelColor(x, y) for y in range(32) for x in range(32) if pm.pixelColor(x, y).alpha() > 200]
    light_back = app.palette().color(_QP.Window).lightness() > 180 and max(c.lightness() for c in inked) < 100
    check("dark theme: dark palette, light icons, its style sheet; Settings → View → Theme (light, dark, as the "
          "system); light theme back",
          dark_window and dark_text and light_icons and dark_sheet and choices == ["light", "dark", "system"]
          and stored == "system" and light_back,
          "(%s)" % [dark_window, dark_text, light_icons, dark_sheet, choices, stored, light_back])

    # 3e3. laser profiles (one laser at a time; a laptop used with two lasers): the machine settings under a
    # name, kept in mm whatever the units; choosing one puts them into the window; a machine setting changed
    # in Settings goes into the profile in use, a program setting (language, grid) does not; the manager adds,
    # duplicates, renames, deletes, exports and imports; no switching during a job; at start the profile in use
    from kerfly.core import profiles as _pc
    from kerfly.gui.profiles_dialog import ProfilesDialog as _PD
    inch = config.convert_units(dict(config.DEFAULT_VALUES), "in")     # 12.80 in, rounded as K40 Whisperer does
    mm_kept = abs(float(_pc.from_values(inch)["LaserXsize"]) - 325) < 0.2
    back_in = abs(float(_pc.to_values(inch, {"LaserXsize": "508"})["LaserXsize"]) - 20.0) < 0.01
    pw = make_window()
    first = pw.profiles.current
    pw.profiles.add("Workshop M3", dict(_pc.from_values(pw.values), board_name="LASER-M3", LaserXsize="500",
                                         rotary="1"))
    _pc.save(pw.profiles)
    pw._refresh_profile_box()
    pw.profile_box.setCurrentIndex(pw.profile_box.findText("Workshop M3"))
    pw.profile_box.activated.emit(pw.profile_box.currentIndex())
    switched = pw.values["board_name"] == "LASER-M3" and float(pw.values["LaserXsize"]) == 500 \
        and pw.values["rotary"] == "1" and pw.power_per_stage() and pw.profiles.current == "Workshop M3"
    # a laser's settings in Settings → Lasers…, the program's in Settings → Settings…
    from kerfly.gui.settings_dialog import SettingsDialog as _SD4
    ld = _PD(pw)
    ld.form._widgets["LaserYsize"].setValue(300)
    ld._save_and_close()
    real_exec = _SD4.exec
    _SD4.exec = lambda self: (self._widgets["grid_mm"].setValue(5), 1)[1]
    pw.edit_settings()
    _SD4.exec = real_exec
    saved = _pc.load()
    machine_kept = (float(saved.get("Workshop M3")["LaserYsize"]) == 300 and "grid_mm" not in saved.get("Workshop M3")
                    and float(pw.values["LaserYsize"]) == 300 and float(pw.values["grid_mm"]) == 5)
    # another laser changed without using it: kept while going to another one in the list, written on Save
    # into its profile only (the window keeps the laser in use); Cancel leaves the changes
    ld = _PD(pw)
    ld.list.setCurrentRow(pw.profiles.names().index(first))
    gap_now = float(pw.values["trace_gap"])
    ld.form._widgets["trace_gap"].setValue(7)
    ld.list.setCurrentRow(pw.profiles.names().index("Workshop M3"))
    ld.list.setCurrentRow(pw.profiles.names().index(first))
    still = abs(ld.form._widgets["trace_gap"].value() - 7) < 1e-6
    ld._save_and_close()
    other_saved = abs(float(_pc.load().get(first)["trace_gap"]) - 7) < 1e-6 and \
        abs(float(pw.values["trace_gap"]) - gap_now) < 1e-6 and pw.profiles.current == "Workshop M3"
    ld = _PD(pw)
    ld.form._widgets["LaserXsize"].setValue(222)
    ld.reject()
    cancelled = float(pw.values["LaserXsize"]) == 500 and abs(float(_pc.load().get("Workshop M3")["LaserXsize"]) - 500) < 1e-6
    machine_kept = machine_kept and still and other_saved and cancelled
    # a material library for each laser: one added to the second laser's is not in the first's; shared, the
    # second laser uses the first's; a copy shares the original's; an old common library is kept by migration
    import copy as _copy
    from kerfly.core import materials as _mat
    first_names = [m.name for m in pw.materials]
    pw.switch_profile("Workshop M3")
    extra = _copy.deepcopy(pw.materials[0])
    extra.name = "Only on M3"
    pw.materials.append(extra)
    _mat.save_library(pw.materials, pw._materials_path())
    pw.switch_profile(first)
    separate = "Only on M3" not in [m.name for m in pw.materials] and [m.name for m in pw.materials] == first_names
    ld = _PD(pw)
    ld.list.setCurrentRow(pw.profiles.names().index("Workshop M3"))
    ld.form._widgets["materials_shared"].setChecked(True)
    combo = ld.form._widgets["materials_from"]
    combo.setCurrentIndex(combo.findData(pw.profiles.get(first)["laser_id"]))
    ld._save_and_close()
    pw.switch_profile("Workshop M3")
    shared_lib = [m.name for m in pw.materials] == first_names
    pw.switch_profile(first)
    ld = _PD(pw)
    ld.list.setCurrentRow(pw.profiles.names().index(first))
    ld._duplicate()
    copy_name = ld.selected()
    copy_shares = pw.profiles.library_owner(copy_name) == pw.profiles.get(first)["laser_id"]
    ld.reject()
    old_style = _pc.Profiles([("A", {"board_name": "LASER-M2"}), ("B", {"board_name": "LASER-M2"})], "A")
    old_style.ensure_ids()
    migrated = (old_style.library_owner("B") == old_style.get("A")["laser_id"] != ""
                and old_style.library_owner("A") == old_style.get("A")["laser_id"])
    libraries = [separate, shared_lib, copy_shares, migrated]
    machine_kept = machine_kept and all(libraries)
    pw.switch_profile(first)
    back = pw.values["board_name"] == "LASER-M2" and float(pw.values["LaserXsize"]) == 325
    pw.worker = object()
    refused = not pw.switch_profile("Workshop M3") and pw.profiles.current == first
    pw.worker = None
    # the manager
    dlg = _PD(pw)
    n0 = len(pw.profiles.items)
    dlg._new()
    new_name = dlg.selected()
    dlg.name_edit.setText("Laptop K40")                   # the name field (Enter / leaving it renames)
    dlg.name_edit.editingFinished.emit()
    renamed = "Laptop K40" in pw.profiles.names() and new_name not in pw.profiles.names()
    dlg._duplicate()
    duplicated = len(pw.profiles.items) == n0 + 2
    export = os.path.join(tempfile.mkdtemp(), "laser.json")
    real_save, real_open = QFileDialog.getSaveFileName, QFileDialog.getOpenFileName
    QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: (export, ""))
    QFileDialog.getOpenFileName = staticmethod(lambda *a, **k: (export, ""))
    dlg.list.setCurrentRow(pw.profiles.names().index("Laptop K40"))
    dlg._export()
    dlg._import()
    imported = "Laptop K40 (2)" in pw.profiles.names() or any(n.startswith("Laptop K40 (") for n in pw.profiles.names())
    QFileDialog.getSaveFileName, QFileDialog.getOpenFileName = real_save, real_open
    real_q = QMessageBox.question
    QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Yes)
    count = len(pw.profiles.items)
    dlg._delete()
    QMessageBox.question = real_q
    deleted = len(pw.profiles.items) == count - 1
    dlg.list.setCurrentRow(pw.profiles.names().index("Workshop M3"))
    dlg._use()
    used = pw.profiles.current == "Workshop M3" and pw.values["board_name"] == "LASER-M3"
    in_box = [pw.profile_box.itemText(i) for i in range(pw.profile_box.count())] == pw.profiles.names()
    dlg.close()
    start_values = dict(config.DEFAULT_VALUES)
    _pc.apply_current(start_values, "My laser")
    at_start = start_values["board_name"] == "LASER-M3" and float(start_values["LaserYsize"]) == 300
    pw.close()
    check("laser profiles: kept in mm, chosen in the Laser tab, machine settings go into the profile in use (not "
          "the grid), back to the first, no switch during a job, the manager (new, rename, duplicate, export, import, "
          "delete, use), the profile in use at start; a material library for each laser (own, shared, a copy "
          "shares, the old common one kept)",
          mm_kept and back_in and switched and machine_kept and back and refused and renamed and duplicated
          and imported and deleted and used and in_box and at_start,
          "(%s)" % [mm_kept, back_in, switched, machine_kept, back, refused, renamed, duplicated, imported, deleted,
                    used, in_box, at_start, pw.profiles.names(), libraries])

    # 3e4. Trace picture: the dark areas of a picture become a path element exactly over them (also with the
    # picture turned, and with home in the upper right corner); the picture's options bar has the button
    from PIL import Image as _PImage, ImageDraw as _PDraw
    from kerfly.gui.trace_dialog import TraceDialog as _TD
    pic = os.path.join(tempfile.mkdtemp(), "square.png")
    im = _PImage.new("L", (200, 100), 255)                # 100 dpi: 50.8 x 25.4 mm
    _PDraw.Draw(im).rectangle((20, 10, 59, 49), fill=0)   # 40 x 40 px = 10.16 mm, 5.08 mm from the left
    im.save(pic, dpi=(100, 100))
    real_exec = _TD.exec
    _TD.exec = lambda self: 1
    from kerfly.gui import image_dialog as _imgd
    real_size_exec = _imgd.ImageSizeDialog.exec
    _imgd.ImageSizeDialog.exec = lambda self: True          # the size of the picture: as in the file
    results = []
    for home_ur, turn in (("0", 0), ("0", 90), ("1", 0)):
        tw = make_window(HomeUR=home_ur, grid_mm="0", follow_head="0")
        tw.load_design(pic)
        picture = tw.elements[-1]
        if turn:
            picture.rotation = turn
        select(tw, picture)
        bar_button = any(b.defaultAction() is tw.act_trace_image for b in tw.tool_options.findChildren(QToolButton))
        f = picture.transform()
        d = picture.design
        dpi = float(d.input_dpi)
        corners = [f(d.bounds[0] + px * (dpi / 100.0) / dpi, d.bounds[3] - py * (dpi / 100.0) / dpi)
                   for px, py in ((20, 10), (60, 50))]
        want = (min(c[0] for c in corners), max(c[0] for c in corners), min(c[1] for c in corners),
                max(c[1] for c in corners))
        n = len(tw.elements)
        tw.trace_image()
        traced = tw.elements[-1]
        got = traced.bounds
        close = all(abs(a - b) * 25.4 < 0.4 for a, b in zip(got, want))
        tw.act_undo.trigger()
        undone = len(tw.elements) == n
        results.append((home_ur, turn, bar_button, len(traced.shape.subpaths) >= 1 and traced.shape.closed, close,
                        undone, [round(v * 25.4, 2) for v in got], [round(v * 25.4, 2) for v in want]))
        tw.close()
    _TD.exec = real_exec
    _imgd.ImageSizeDialog.exec = real_size_exec
    check("Trace picture: a closed path exactly over the dark square (turned picture, home upper right), Undo, "
          "the button in the picture's options bar",
          all(r[2] and r[3] and r[4] and r[5] for r in results), "(%s)" % results)

    # 3e5. Cut out of a picture: the piece inside the dragged rectangle / ellipse stays exactly where it was
    # dragged (also turned, home upper right), the rest goes; one undo step; outside an ellipse is white
    from PySide6.QtCore import QPointF as _QPF, QRectF as _QRF
    from kerfly.gui.preview import element_transform as _et
    from kerfly.gui import image_dialog as _imgd2
    real_size_exec2 = _imgd2.ImageSizeDialog.exec
    _imgd2.ImageSizeDialog.exec = lambda self: True
    crop_results = []
    for home_ur, turn, shape in (("0", 0, "rect"), ("0", 90, "rect"), ("1", 0, "rect"), ("0", 0, "ellipse")):
        cw = make_window(HomeUR=home_ur, grid_mm="0", follow_head="0")
        cw.load_design(pic)
        picture = cw.elements[-1]
        picture.rotation = turn
        cw._layout_changed()
        cw.set_tool("crop")
        if shape == "ellipse":
            cw.tool_options.crop_shape_box.setCurrentIndex(cw.tool_options.crop_shape_box.findData("ellipse"))
        db = picture.design.bounds
        local = _QRF(0, 0, (db[1] - db[0]) * 25.4, (db[3] - db[2]) * 25.4)
        r = _et(picture, cw.preview.home_ur, cw.preview.bed_w_mm).mapRect(local)
        drag = _QRF(r.left() + r.width() * 0.1, r.top() + r.height() * 0.05, r.width() * 0.3, r.height() * 0.6)
        n = len(cw.elements)
        cw._preview_drawn("crop", drag.topLeft(), drag.bottomRight(), False)
        piece = cw.elements[-1]
        pd = piece.design.bounds
        got = _et(piece, cw.preview.home_ur, cw.preview.bed_w_mm).mapRect(_QRF(0, 0, (pd[1] - pd[0]) * 25.4,
                                                                                 (pd[3] - pd[2]) * 25.4))
        placed = all(abs(a - b) < 0.3 for a, b in ((got.left(), drag.left()), (got.top(), drag.top()),
                                                   (got.right(), drag.right()), (got.bottom(), drag.bottom())))
        img = piece.design.raster.image.convert("L")
        corner_white = img.getpixel((1, 1)) == 255 if shape == "ellipse" else True
        replaced = len(cw.elements) == n and piece is not picture
        cw.act_undo.trigger()
        undone = cw.elements[-1].design is picture.design
        crop_results.append((home_ur, turn, shape, placed, corner_white, replaced, undone,
                             [round(v, 2) for v in (got.left(), got.top(), got.right(), got.bottom())],
                             [round(v, 2) for v in (drag.left(), drag.top(), drag.right(), drag.bottom())]))
        cw.close()
    _imgd2.ImageSizeDialog.exec = real_size_exec2
    check("Cut out of a picture: the piece stays exactly where it was dragged (turned, home upper right, "
          "ellipse with white corners), the picture replaced, Undo",
          all(r[3] and r[4] and r[5] and r[6] for r in crop_results), "(%s)" % crop_results)

    # 3e6. USB port per laser (beta; two K40 on one computer): the remembered port is used without asking,
    # two plugged in and none remembered: the user chooses and it goes into the profile, one plugged in: no
    # question; "Which one?" moves that head right and back; another profile's port releases the USB
    import nano_library as _nl
    from kerfly.core import usbports as _up
    from kerfly.gui import usb_port_dialog as _upd
    calls = []

    class _FakeBoard:
        def __init__(self):
            self.USB_Location = None

        def initialize_device(self, location=None, verbose=False):
            calls.append(("init", location))
            self.USB_Location = location or (1, 5)

        def say_hello(self):
            return 1

        def home_position(self):
            calls.append(("home", self.USB_Location))

        def unlock_rail(self):
            calls.append(("unlock", self.USB_Location))

        def rapid_move(self, dx, dy):
            calls.append(("move", self.USB_Location, dx))

        def release_usb(self):
            calls.append(("release", self.USB_Location))
    real_board, real_list = _nl.K40_CLASS, _up.list_lasers
    two = [_up.Port("1-2", 1, 5, True), _up.Port("1-3", 1, 7, True)]
    _nl.K40_CLASS = _FakeBoard
    _up.list_lasers = lambda: list(two)
    uw = make_window(usb_port="1-3")
    uw.connect_laser()
    remembered = calls[0] == ("init", (1, 7)) and uw.laser.port_key == "1-3"
    calls.clear()
    real_dlg_exec = _upd.ChooseLaserDialog.exec

    def pick_second(self):
        self.list.setCurrentRow(1)
        self.which.click()                               # Which one?
        return 1
    _upd.ChooseLaserDialog.exec = pick_second
    uw.values["usb_port"] = ""
    uw.connect_laser()
    which = [c for c in calls if c[0] == "move"]
    asked = ("init", (1, 7)) in calls and uw.values["usb_port"] == "1-3" \
        and _pc.load().get(uw.profiles.current).get("usb_port") == "1-3"
    moved_right_back = len(which) == 2 and which[0][1] == (1, 7) and which[0][2] > 0 and which[1][2] < 0
    _upd.ChooseLaserDialog.exec = real_dlg_exec
    calls.clear()
    _up.list_lasers = lambda: [two[0]]
    uw.values["usb_port"] = ""
    uw.connect_laser()
    single = next((c for c in calls if c[0] == "init"), None) == ("init", None)
    # another laser profile on another port: the USB is released
    _up.list_lasers = lambda: list(two)
    uw.values["usb_port"] = "1-2"
    uw.connect_laser()
    uw.profiles.add("Second K40", dict(_pc.from_values(uw.values), usb_port="1-3"))
    uw.switch_profile("Second K40")
    released = not uw.laser.connected
    from kerfly.gui.settings_dialog import SettingsForm as _LF5
    sd = _LF5(dict(uw.values), machine=True, window=uw)
    listed = [sd.usb_port_box.itemData(i) for i in range(sd.usb_port_box.count())]
    sd.close()
    _nl.K40_CLASS, _up.list_lasers = real_board, real_list
    uw.close()
    check("USB port per laser: remembered port used, chosen when two (and kept in the profile), Which one? "
          "moves that head, one laser: no question, another profile's port releases the USB, Settings lists them",
          remembered and asked and moved_right_back and single and released and listed == ["", "1-2", "1-3"],
          "(%s)" % [remembered, asked, moved_right_back, single, released, listed, calls[:6]])

    # 3f. .kerfly projects open in Kerfly: the Linux AppImage writes its menu entry and file type into the
    # user's own folders, with the AppImage as the program; a newer AppImage takes the entry over
    from kerfly.gui import desktop_entry as _de
    data = tempfile.mkdtemp(prefix="kerfly_xdg_data_")
    old_env = {k: os.environ.get(k) for k in ("XDG_DATA_HOME", "APPIMAGE")}
    fake_image = os.path.join(data, "Kerfly-9.9.9-x86_64.AppImage")
    open(fake_image, "w").close()
    os.environ["XDG_DATA_HOME"], os.environ["APPIMAGE"] = data, fake_image
    commands = []
    written = _de.install(run=lambda cmd, **k: commands.append(cmd[0]))
    entry = open(os.path.join(data, "applications", "kerfly.desktop"), encoding="utf-8").read()
    mime = open(os.path.join(data, "mime", "packages", "kerfly.xml"), encoding="utf-8").read()
    for k, v in old_env.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    check(".kerfly file type (Linux AppImage): menu entry runs the AppImage, the file type and icon written",
          ("Exec=%s %%F" % fake_image) in entry and "application/x-kerfly" in entry and "*.kerfly" in mime
          and len(written) == 3 and _de.applies() == (sys.platform.startswith("linux") and bool(old_env["APPIMAGE"])),
          "(%s)" % [entry[:200], len(written), commands])

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
    select(w, b)
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
    w.element_list.item(1).setCheckState(Qt.Unchecked)       # untick it in the element list
    w._compiled = None
    hidden_ok = w.design is e.design or w.design.bounds == e.design.bounds   # only e compiled
    select(w, e)
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
    select(w, rect)
    choose_layer(w, next(l for l in w.layers if l.kind == "engrave"))
    bar_set(w, "corner_radius", 4)
    engraved = bool(rect.design.vector_engrave.ecoords) and not rect.design.vector_cut.ecoords \
        and rect.shape.corner_radius == 4
    select(w, text)
    bar_set(w, "text", "Kerfly")
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
    bar_set(w, "text", "Kerfly")
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
    saved = os.path.isfile(w._materials_path())          # the library of the laser in use
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
    pass  # Qt: imported at the top
    from PySide6.QtTest import QTest
    w = make_window()
    w.resize(1200, 800)
    w.show()
    for _settle in range(5):             # the panel measures itself once more after showing: let it settle
        app.processEvents()              # (the bed view must not move between the clicks)
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
    second._press_pos = second.pos()
    second._dragging = True
    r = second.sceneBoundingRect()                                     # top-left near the first one's corner
    second.setPos(second.pos() + QPointF(60.5 - r.left(), 50.4 - r.top()))
    r = second.sceneBoundingRect()
    dragged = abs(r.left() - 60) < 1e-6 and abs(r.top() - 50) < 1e-6 and view.last_move_snapped
    moved_el = second.element
    second.finish_drag()                                               # mouse released: the element moves
    dragged = dragged and abs(moved_el.x * 25.4 - 60) < 1e-6 and abs(moved_el.y * 25.4 + 50) < 1e-6
    check("snapping: draw from a corner, off switch, drag onto another element",
          corner and off and dragged, "(left %.3f)" % (moved_el.x * 25.4))
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
    # (the node tool's bar shows the node buttons alone: the shape itself is now a path)
    inserted = ed.insert_at(mid) and len(view.node_scene_points()) == 5 and rect.shape.kind == "path"
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
    from PySide6.QtCore import QEvent
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

    # 28b. Offset tool (right strip): click a shape -> a new outline around it (or inside it);
    # "Offset selected" for shapes selected before; a hole moves the other way
    w = make_window(grid_mm="0")
    w.resize(1200, 800)
    w.show()
    app.processEvents()
    w.preview.fit_all()
    app.processEvents()

    def click_scene(x, y):
        vp = w.preview.viewport()
        QTest.mouseClick(vp, Qt.LeftButton, Qt.NoModifier, w.preview.mapFromScene(QPointF(x, y)))
        app.processEvents()
    w._preview_drawn("rectangle", QPointF(20, 20), QPointF(60, 60), False)      # 40 x 40
    w.tool_actions["offset"].trigger()
    from kerfly.gui import truth as _otruth
    in_strip = w.preview.tool == "offset" and set(_otruth.bar_fields(w.tool_options)) == {
        "offset_distance", "offset_join", "offset_keep"}
    bar_set(w, "offset_distance", 2.0)
    bar_set(w, "offset_join", "miter")
    bar_set(w, "offset_keep", True)
    click_scene(40, 40)
    grown = w.elements[-1]
    out_ok = (len(w.elements) == 2 and grown.shape.kind == "path"
              and (round(grown.size[0] * 25.4, 2), round(grown.size[1] * 25.4, 2)) == (44.0, 44.0)
              and abs(grown.bounds[0] * 25.4 - 18.0) < 0.01)
    bar_set(w, "offset_distance", -5.0)
    bar_set(w, "offset_join", "round")
    bar_set(w, "offset_keep", False)
    w.preview.select_element([w.elements[0]])
    app.processEvents()
    click_bar_button(w, "Offset selected")
    inner = w.elements[0]
    in_ok = len(w.elements) == 2 and (round(inner.size[0] * 25.4, 2), round(inner.size[1] * 25.4, 2)) == (30.0, 30.0)
    w.undo()
    undo_ok = len(w.elements) == 2 and round(w.elements[0].size[0] * 25.4, 2) == 40.0
    # a frame (square with a hole): the outside grows, the hole shrinks
    for e in list(w.elements):
        w.elements.remove(e)
    w.set_tool("select")
    w._preview_drawn("rectangle", QPointF(20, 20), QPointF(60, 60), False)
    w._preview_drawn("rectangle", QPointF(30, 30), QPointF(50, 50), False)
    w.preview.select_element(w.elements[-2:])
    w.boolean_selected("difference")
    w.set_tool("offset")
    bar_set(w, "offset_distance", 1.0)
    bar_set(w, "offset_join", "miter")
    click_scene(25, 40)                                  # on the frame, not in its hole
    frame = w.elements[-1]
    holes = sorted(round(max(n[0] for n in sp["nodes"]) - min(n[0] for n in sp["nodes"]), 2)
                   for sp in frame.shape.subpaths)
    hole_ok = holes == [18.0, 42.0] and len(w.elements) == 1
    check("Offset tool: in the right strip, click a shape (2 mm out, kept), Offset selected (5 mm in, "
          "replaced), undo, a hole shrinks", in_strip and out_ok and in_ok and undo_ok and hole_ok,
          "(%s)" % [in_strip, out_ok, in_ok, undo_ok, holes])
    w.close()

    # 28c. Join into a polyline (Ctrl+J): lines whose ends meet (closer than 0.05 mm) become one path, closed
    # when the chain comes round; a line that meets nothing and a gap of 0.2 mm stay as they are; one undo step;
    # the same with home in the upper right corner
    from kerfly.gui import truth as _truth_j
    joins = []
    for home_ur in ("0", "1"):
        jw = make_window(grid_mm="0", HomeUR=home_ur)

        def line(a, b, jw=jw):
            jw._preview_drawn("line", QPointF(*a), QPointF(*b), False)
        line((20, 20), (60, 20))
        line((60, 20), (40, 50))
        line((40, 50), (20, 20))                     # a triangle of three lines
        line((100, 20), (130, 20))
        line((130.04, 20), (130, 50))                # 0.04 mm apart: joined
        line((150, 20), (180, 20))
        line((180.2, 20), (180, 50))                 # 0.2 mm apart: not
        line((200, 80), (240, 90))                   # alone
        before = [round(b, 4) for e in jw.elements[:3] for b in e.bounds]
        jw.preview.select_element(list(jw.elements))
        jw.act_join.trigger()
        kinds = [(e.shape.kind, [sp["closed"] for sp in e.shape.subpaths] if e.shape.kind == "path" else None)
                 for e in jw.elements]
        tri = jw.elements[0]
        same_place = [round(v, 4) for v in tri.bounds] == [min(before[0::4]), max(before[1::4]),
                                                            min(before[2::4]), max(before[3::4])]
        nodes = [len(sp["nodes"]) for e in jw.elements[:2] for sp in e.shape.subpaths]
        jw.undo()
        joins.append(kinds == [("path", [True]), ("path", [False])] + [("line", None)] * 3 and same_place
                     and nodes == [3, 3] and len(jw.elements) == 8 and not _truth_j.check_window(jw))
        jw._dirty = False
        jw.close()
    check("Join into a polyline (Ctrl+J): a triangle of lines closed, a 0.04 mm gap joined, 0.2 mm and a lone "
          "line kept, in place, one undo step (home upper left and upper right)", all(joins), "(%s)" % joins)

    # 28c2. The dialog pattern (kerfly/gui/widgets.py): a body, a footer with Cancel first and the action named
    # for what it does (never "OK", role primary, the theme's height), a beta badge by a new section; the
    # style puts every dialog's buttons in that order and without icons (also a message box)
    from PySide6.QtWidgets import QDialogButtonBox as _DBB, QLabel as _QL, QMessageBox as _QMB, QStyle as _QS
    from kerfly.gui import theme as _th
    from kerfly.gui.gcode_dialog import GcodeDialog as _GD
    from kerfly.gui.nest_dialog import NestDialog as _ND
    pattern = []
    for dlg, action in ((_ND({}, (300, 200), 2), _("Nest")), (_GD({}), _("Save…"))):
        dlg.show()
        app.processEvents()
        box = dlg.findChild(_DBB)
        ok_b, cancel_b = box.button(_DBB.Ok), box.button(_DBB.Cancel)
        badges = [lb for lb in dlg.findChildren(_QL) if lb.property("role") == "beta"]
        pattern.append((ok_b.text() == action and ok_b.property("role") == "primary" and ok_b.isDefault()
                        and ok_b.height() == _th.HEIGHT_BUTTON and cancel_b.mapTo(dlg, cancel_b.rect().topLeft()).x()
                        < ok_b.mapTo(dlg, ok_b.rect().topLeft()).x() and ok_b.icon().isNull(),
                        len(badges)))
        dlg.close()
    mb = _QMB(_QMB.Question, "?", "?", _QMB.Yes | _QMB.No)
    mb.show()
    app.processEvents()
    mb_order = mb.button(_QMB.No).x() < mb.button(_QMB.Yes).x()
    mb.close()
    check("dialog pattern: Cancel first, the named action (role primary, default, 32 px, no icon) last; a beta "
          "badge by the nesting method (by outlines is new), none on G-code (GRBL confirmed on a laser); a message "
          "box's buttons in the same order",
          [p[0] for p in pattern] == [True, True] and [p[1] for p in pattern] == [1, 0] and mb_order
          and app.style().styleHint(_QS.SH_DialogButtonBox_ButtonsHaveIcons) == 0,
          "(%s, message box %s)" % (pattern, mb_order))

    # 28c3. side handles: the middles of a selected shape's sides stretch it along one axis only, the opposite
    # side staying where it is; one undo step each
    from PySide6.QtGui import QMouseEvent as _QME
    from PySide6.QtCore import QEvent as _QEv
    hw = make_window(grid_mm="0")
    hw.resize(1200, 800)
    hw.show()
    app.processEvents()
    hw._preview_drawn("rectangle", QPointF(20, 20), QPointF(60, 50), False)        # 40 x 30 mm
    rect_e = hw.elements[-1]
    hw.preview.select_element([rect_e])
    app.processEvents()

    def side_drag(kind, pick, dx_mm, dy_mm):
        QTest.qWait(QApplication.doubleClickInterval() + 100)      # a press, not the second half of a double click
        handle = pick([h for h in hw.preview._handles if h.kind == kind])
        vp = hw.preview.viewport()
        a = hw.preview.mapFromScene(handle.scenePos())
        b = hw.preview.mapFromScene(handle.scenePos() + QPointF(dx_mm, dy_mm))
        QTest.mousePress(vp, Qt.LeftButton, Qt.NoModifier, a)
        for i in range(1, 9):
            p = a + (b - a) * i / 8
            QApplication.sendEvent(vp, _QME(_QEv.MouseMove, QPointF(p), QPointF(vp.mapToGlobal(p)), Qt.NoButton,
                                            Qt.LeftButton, Qt.NoModifier))
            app.processEvents()
        QTest.mouseRelease(vp, Qt.LeftButton, Qt.NoModifier, b)
        app.processEvents()
    kinds = sorted(h.kind for h in hw.preview._handles)
    left0, top0 = rect_e.bounds[0], rect_e.bounds[3]
    side_drag("side_x", lambda hs: max(hs, key=lambda h: h.scenePos().x()), 10, 0)
    w1, h1 = (round(v * 25.4, 1) for v in rect_e.size)
    # (the mouse moves by whole pixels: within 0.3 mm)
    stretched_x = abs(w1 - 50.0) < 0.3 and h1 == 30.0 and abs(rect_e.bounds[0] - left0) < 0.002
    side_drag("side_y", lambda hs: max(hs, key=lambda h: h.scenePos().y()), 0, 5)
    w2, h2 = (round(v * 25.4, 1) for v in rect_e.size)
    stretched_y = w2 == w1 and abs(h2 - 35.0) < 0.3 and abs(rect_e.bounds[3] - top0) < 0.002
    hw.undo()
    undone = tuple(round(v * 25.4, 1) for v in hw.elements[-1].size) == (w1, h1)
    hw._dirty = False
    hw.close()
    check("side handles: four (with the corners and the rotation one), the right one stretches the width "
          "alone, the bottom one the height alone, the opposite side stays; one undo step",
          kinds.count("side_x") == 2 and kinds.count("side_y") == 2 and stretched_x and stretched_y and undone,
          "(%s)" % [kinds, (w1, h1), (w2, h2), undone])

    # 28c4. the node tool ends with a click on the empty bed (back to Select; like any click there it
    # deselects); a click on the shape keeps it
    nw = make_window(grid_mm="0")
    nw.resize(1200, 800)
    nw.show()
    app.processEvents()
    nw._preview_drawn("rectangle", QPointF(20, 20), QPointF(60, 50), False)
    ne = nw.elements[-1]
    nw.preview.select_element([ne])
    nw.tool_actions["nodes"].trigger()
    app.processEvents()
    nvp = nw.preview.viewport()
    QTest.mouseClick(nvp, Qt.LeftButton, Qt.NoModifier, nw.preview.mapFromScene(QPointF(40, 35)))
    app.processEvents()
    kept_on_shape = nw.preview.tool == "nodes"
    QTest.qWait(QApplication.doubleClickInterval() + 100)          # two clicks, not a double click
    bed_w, bed_h = (v * 25.4 for v in config.bed_size_inches(nw.values))
    QTest.mouseClick(nvp, Qt.LeftButton, Qt.NoModifier, nw.preview.mapFromScene(QPointF(bed_w - 10, bed_h - 10)))
    app.processEvents()
    left_nodes = nw.preview.tool == "select" and nw.tool_actions["select"].isChecked()
    nw._dirty = False
    nw.close()
    check("node tool: a click on the shape keeps it, a click on the empty bed goes back to Select",
          kept_on_shape and left_nodes, "(%s)" % [kept_on_shape, left_nodes])

    # 28c5. a GRBL laser homing to the lower left: To head puts the design's lower left corner at the head (the
    # home corner); its layers have a power each and its trace power counts; a K40 keeps the upper left
    from kerfly.gui.settings_dialog import SettingsForm as _GLF
    corners = {}
    for machine in ("grbl", "k40"):
        gw = make_window(grid_mm="0", machine=machine, grbl_home="lower_left")
        gw._preview_drawn("rectangle", QPointF(40, 40), QPointF(80, 70), False)
        bed_h_in = config.bed_size_inches(gw.values)[1]
        gw.head = gw._home_head() if machine == "grbl" else (0.0, 0.0)
        gw.place_at_head()
        e = gw.elements[-1]
        corners[machine] = (round(e.bounds[0] * 25.4, 2), round(e.bounds[2 if machine == "grbl" else 3] * 25.4, 2),
                            round(gw.head[1] * 25.4, 2))
        if machine == "grbl":
            grbl_power = gw.power_per_stage() and all("power" in row for row in gw.layers_panel.rows.values())
            form = _GLF(dict(gw.values, trace_w_laser="1"), machine=True, window=gw)
            trace_power_on = form._widgets["Trace_power"].isEnabled()
            form.close()
        gw._dirty = False
        gw.close()
    # the homing speed of the laser's settings goes into the board ($25) on connect, only when it differs
    from kerfly.core import grbl as _grbl_hs
    hb = FakeGrbl()
    hc = _grbl_hs.GrblController(opener=lambda port, baud: hb)
    hc.home_speed = 1500
    hc.connect(port="/dev/ttyFAKE")
    hc.release()
    hb2 = FakeGrbl()
    hc2 = _grbl_hs.GrblController(opener=lambda port, baud: hb2)
    hc2.home_speed = 500                                  # the board's own already
    hc2.connect(port="/dev/ttyFAKE")
    hc2.release()
    home_speed_ok = hb.settings["$25"] == "1500" and "$25=1500" in hb.lines and \
        not any(l.startswith("$25=") for l in hb2.lines)
    trace_power_on = trace_power_on and home_speed_ok
    corner_ok = corners["grbl"][0] == 0 and corners["grbl"][1] == corners["grbl"][2] == round(-bed_h_in * 25.4, 2) \
        and corners["k40"][:2] == (0, 0)
    check("To head: a GRBL laser homing to the lower left gets the design's lower left corner at the head, a K40 "
          "its upper left; a GRBL laser has a power for each layer and its trace power; its homing speed ($25) "
          "written on connect when it differs",
          corner_ok and grbl_power and trace_power_on, "(%s)" % [corners, grbl_power, trace_power_on])

    # 28c6. four home corners for every laser (a picture of the bed with a radio button in each corner, in the
    # laser's settings): Home puts the head in that corner, To head brings the design's same corner to it; a
    # K40's upper corners keep HomeUR (its data), a lower one is home_lower
    from kerfly.gui.settings_dialog import GRBL_CORNERS as _GC
    four = {}
    for machine in ("k40", "grbl"):
        for corner in ("UL", "UR", "LL", "LR"):
            values = {"HomeUR": "1" if corner[1] == "R" else "0", "home_lower": "1" if corner[0] == "L" else "0",
                      "grbl_home": {c: n for n, c in _GC.items()}[corner]}
            cw4 = make_window(grid_mm="0", follow_head="0", machine=machine, **values)
            form = _GLF(dict(cw4.values), machine=True, window=cw4)
            picker = form._widgets["HomeUR" if machine == "k40" else "grbl_home"]
            shown = picker.isVisibleTo(form) or not form.isVisible()
            other = form._widgets["grbl_home" if machine == "k40" else "HomeUR"]
            picked = picker.current() == corner and all(b.isEnabled() for b in picker.buttons.values()) \
                and not other.isVisibleTo(form)
            # choosing another corner in the picture changes the laser's setting
            flip = {"UL": "LR", "UR": "LL", "LL": "UR", "LR": "UL"}[corner]
            picker.buttons[flip].setChecked(True)
            got = form.result_values()[0]
            saved = (got["HomeUR"] == ("1" if flip[1] == "R" else "0")
                     and got["home_lower"] == ("1" if flip[0] == "L" else "0")) if machine == "k40" else \
                got["grbl_home"] == {c: n for n, c in _GC.items()}[flip]
            form.close()
            cw4._preview_drawn("rectangle", QPointF(40, 40), QPointF(80, 70), False)
            cw4.home()
            cw4.place_at_head()
            e = cw4.elements[-1]
            bw4, bh4 = config.bed_size_inches(cw4.values)
            # the head (bed inches from the left / top for GRBL; a K40's x from home), the design's corner
            hx = (bw4 if corner[1] == "R" and machine == "grbl" else 0.0)
            hy = -bh4 if corner[0] == "L" else 0.0
            ex = e.bounds[1] if corner[1] == "R" and machine == "grbl" else e.bounds[0]
            ey = e.bounds[2] if corner[0] == "L" else e.bounds[3]
            four[(machine, corner)] = (picked and shown and saved, abs(cw4.head[0] - hx) < 1e-3
                                       and abs(cw4.head[1] - hy) < 1e-3, abs(ex - hx) < 1e-3 and abs(ey - hy) < 1e-3)
            cw4._dirty = False
            cw4.close()
    check("home corner: four corners for a K40 and a GRBL laser (a picture with radio buttons); Home puts the head "
          "there, To head brings the design's same corner to it",
          all(all(v) for v in four.values()), "(%s)" % {k: v for k, v in four.items() if not all(v)})

    # 28d. Nest on the bed (Ctrl+Shift+N): the selected parts laid out inside the bed with the gap between them,
    # nothing over another; what does not fit on more sheets (groups Sheet N, sheets 2 and on unticked); a group
    # moves as one part (its members keep their places to each other); without turning nothing is turned; a
    # second nesting lays the parts out again (no sheet in a sheet); one undo step; also with home upper right
    import random as _rnd
    import kerfly.gui.nest_dialog as _nd
    from kerfly.core.layout import on_bed as _on_bed
    from kerfly.gui import truth as _truth_n
    _nd_exec = _nd.NestDialog.exec
    _nd.NestDialog.exec = lambda self: 1                     # the dialog answered with its values

    def _box(e):
        return e.bounds[0] * 25.4, e.bounds[1] * 25.4, -e.bounds[3] * 25.4, -e.bounds[2] * 25.4

    def _clash(els, gap):
        for i in range(len(els)):
            for j in range(i + 1, len(els)):
                (x0, x1, y0, y1), (X0, X1, Y0, Y1) = _box(els[i]), _box(els[j])
                # rectangles (all the shapes here): closer than the gap (corner to corner too)
                if math.hypot(max(0.0, X0 - x1, x0 - X1), max(0.0, Y0 - y1, y0 - Y1)) < gap - 0.05:
                    return True
        return False
    nests = []
    from kerfly.core.nesting import outlines_available as _outl
    for home_ur, count, turn, method in (("0", 30, True, "rectangles"), ("1", 12, True, "rectangles"),
                                         ("0", 12, False, "rectangles")) + \
            ((("0", 12, True, "outlines"), ("1", 30, False, "outlines")) if _outl() else ()):
        nw = make_window(grid_mm="0", HomeUR=home_ur)
        r = _rnd.Random(3)
        for _k in range(count):
            x, y = r.uniform(0, 200), r.uniform(0, 120)
            nw._preview_drawn("rectangle", QPointF(x, y), QPointF(x + r.uniform(20, 120), y + r.uniform(15, 90)),
                              False)
        pair = nw.elements[:2]
        nw.preview.select_element(pair)
        nw.group_selected()                                 # two rectangles as one part
        rel = (round((pair[1].x - pair[0].x) * 25.4, 3), round((pair[1].y - pair[0].y) * 25.4, 3))
        rotations = [e.rotation for e in nw.elements]
        pair_centres = (pair[0].centre, pair[1].centre)
        nw.preview.scope = ""
        nw.preview.select_element(list(nw.elements))
        nw.nest_defaults = {"method": method, "gap": 2.0, "turn": turn, "seconds": 2}
        undo_before = len(nw._undo)
        nw.nest_selected()
        bw, bh = config.bed_size_inches(nw.values)
        sheets = {}
        for e in nw.elements:
            name = nw.group_names.get(e.group.split("/")[0], "") if e.group else ""
            sheets.setdefault(name if name.startswith("Sheet ") else "Sheet 1", []).append(e)
        ok = all(_on_bed(e, bw, bh) for e in nw.elements) and not any(_clash(v, 2.0) for v in sheets.values()) \
            and len(nw._undo) == undo_before + 1 and not _truth_n.check_window(nw)
        # a group moves as one part: its members keep their distance (and their places, when not turned)
        moved = (round((pair[1].x - pair[0].x) * 25.4, 3), round((pair[1].y - pair[0].y) * 25.4, 3))
        ok_pair = moved == rel if pair[0].rotation == rotations[0] else \
            abs(math.dist(pair[0].centre, pair[1].centre) - math.dist(*pair_centres)) * 25.4 < 0.02
        diag = [all(_on_bed(e, bw, bh) for e in nw.elements), not any(_clash(v, 2.0) for v in sheets.values()),
                len(nw._undo) == undo_before + 1, not _truth_n.check_window(nw), ok_pair]
        ok = ok and ok_pair and len({e.group.split("/")[-1] for e in pair}) == 1
        ok = ok and all(e.visible == (n == "Sheet 1") for n, v in sheets.items() for e in v)
        if not turn:
            ok = ok and [e.rotation for e in nw.elements] == rotations
        if count == 30 and method == "rectangles":
            ok = ok and len(sheets) >= 2 and all(len(e.group.split("/")) <= 2 for e in nw.elements)
            nw.preview.select_element(list(nw.elements))
            nw.nest_selected()                              # again: laid out again, still a sheet a level deep
            ok = ok and all(len(e.group.split("/")) <= 2 for e in nw.elements) and \
                len({e.group.split("/")[0] for e in nw.elements}) == len(sheets)
            nw.undo()
        nw.undo()
        ok = ok and all(not e.group or "/" not in e.group for e in nw.elements) and all(e.visible for e in nw.elements)
        nests.append(ok if ok else (method, home_ur, diag))
        nw._dirty = False
        nw.close()
    _nd.NestDialog.exec = _nd_exec
    check("Nest on the bed: inside the bed with the gap, nothing over another, more sheets as groups (2 and on "
          "unticked), a group as one part, no turning when off, nested again, one undo step (both homes); by "
          "rectangles and by outlines",
          all(n is True for n in nests), "(%s)" % nests)

    # 28e. G-code for GRBL (File → Save G-code): a cut rectangle, an engraved ellipse (2 passes) and a 10 x 5 mm
    # picture come out as the reference file (tests/fixtures/gcode/basic.nc), and where they belong: the
    # rectangle at X 10..40, Y 190..210 from the bed's lower left corner, the picture's dark part burnt at X
    # 32..36, Y 177..179; the same with home in the upper right; with the origin at the design the rectangle is
    # at X 0..30, Y -20..0; the power is S of the layer's power; the options are kept in the laser profile
    import re as _re
    from PIL import Image as _GImage, ImageDraw as _GDraw
    from kerfly.core import gcode as _gcode, loaders as _gloaders
    from kerfly.core.design import Design as _GDesign
    from kerfly.core.layout import Element as _GElement
    gdir = tempfile.mkdtemp()
    gpng = os.path.join(gdir, "dark.png")
    gim = _GImage.new("L", (100, 50), 255)
    _GDraw.Draw(gim).rectangle((20, 10, 59, 29), fill=0)              # 10 px / mm: 4 x 2 mm at (2, 1) mm
    gim.save(gpng, dpi=(254, 254))

    def gscene(home_ur):
        gw = make_window(grid_mm="0", HomeUR=home_ur, halftone="0")
        gw._preview_drawn("rectangle", QPointF(10, 10), QPointF(40, 30), False)
        gw.shape_defaults["ellipse"].operation = "engrave"
        gw._preview_drawn("ellipse", QPointF(50, 10), QPointF(70, 20), False)
        next(l for l in gw.layers if l.kind == "engrave").passes = 2
        d = _GDesign()
        _gloaders.load_image(gpng, d, 254, False)
        pic = _GElement(d, name="dark", source_file=gpng)
        pic.y = -40 / 25.4
        pic.x = (325 - 30 - 10) / 25.4 if home_ur == "1" else 30 / 25.4        # the same place on the bed
        gw.elements.append(pic)
        gw._layout_changed()
        return gw

    def gmoves(text):
        """[(x, y, power)] of the G1 moves (the power that is on during each)."""
        out, power = [], 0
        for line in text.splitlines():
            if line.startswith("G1"):
                words = dict((w[0], w[1:]) for w in line.split()[1:])
                power = int(words.get("S", power))
                out.append((float(words["X"]), float(words["Y"]), power))
        return out
    gtexts = {}
    for home_ur in ("0", "1"):
        gw = gscene(home_ur)
        gtexts[home_ur] = _gcode.build(gw.elements, gw.layers, gw.job_settings(), gw.values)
        if home_ur == "0":
            gdesign = _gcode.build(gw.elements, gw.layers, gw.job_settings(), gw.values,
                                   _gcode.GcodeOptions(origin="design"))
        gw._dirty = False
        gw.close()
    gref = os.path.join(FIX, "gcode", "basic.nc")
    if os.environ.get("KERFLY_WRITE_REFERENCES"):
        with open(gref, "w", encoding="utf-8") as f:
            f.write(gtexts["0"])
    with open(gref, encoding="utf-8") as f:
        gsame = f.read() == gtexts["0"]
    moves = gmoves(gtexts["0"])
    rect = [(x, y) for x, y, p in moves if 9.9 < x < 40.1 and 189.9 < y < 210.1]
    burnt = []
    prev = None
    for x, y, p in moves:
        if p and prev is not None and abs(y - prev[1]) < 1e-6 and 176 < y < 180:
            burnt += [prev, (x, y)]
        prev = (x, y)
    gpowers = sorted({p for _x, _y, p in moves})
    passes = gtexts["0"].count("Vector engrave: engrave, pass")
    bx = [p[0] for p in burnt]
    by = [p[1] for p in burnt]
    gplaces = rect and min(x for x, _y in rect) == 10 and max(x for x, _y in rect) == 40 and \
        bx and abs(min(bx) - 32) < 0.15 and abs(max(bx) - 36) < 0.15 and abs(min(by) - 177) < 0.15 and \
        abs(max(by) - 179) < 0.15
    drect = [(x, y) for x, y, _p in gmoves(gdesign)]
    gdesign_ok = min(x for x, _y in drect) == 0 and max(y for _x, y in drect) == 0
    gw = make_window(grid_mm="0")
    gw._preview_drawn("rectangle", QPointF(10, 10), QPointF(40, 30), False)
    import kerfly.gui.gcode_dialog as _gd
    _gd_exec, _gd_values = _gd.GcodeDialog.exec, _gd.GcodeDialog.values
    _gd.GcodeDialog.exec = lambda self: 1
    _gd.GcodeDialog.values = lambda self: {"gcode_origin": "design", "gcode_s_max": "255", "gcode_overscan": "3"}
    gout = os.path.join(gdir, "out.nc")
    _gsave = QFileDialog.getSaveFileName
    QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: (gout, ""))
    gw.save_gcode()
    QFileDialog.getSaveFileName = _gsave
    _gd.GcodeDialog.exec, _gd.GcodeDialog.values = _gd_exec, _gd_values
    from kerfly.core import profiles as _gprof
    gsaved = os.path.isfile(gout) and gw.profiles.get(gw.profiles.current).get("gcode_s_max") == "255" and \
        max(p for _x, _y, p in gmoves(open(gout, encoding="utf-8").read())) <= 255
    gw._dirty = False
    gw.close()
    check("G-code for GRBL: the reference file; the rectangle and the picture's dark part where they are on the "
          "bed, also with home upper right; origin at the design; S of the layer power, 2 engrave passes; "
          "Save G-code writes the file and keeps its options in the laser profile",
          gsame and gtexts["0"] == gtexts["1"] and gplaces and gdesign_ok and gpowers == [0, 500] and passes == 2
          and gsaved,
          "(%s)" % [gsame, gtexts["0"] == gtexts["1"], gplaces, gdesign_ok, gpowers, passes, gsaved])

    # 28f. GRBL lasers over the serial port, on a stand-in board: the stream never overfills GRBL's
    # 128-byte buffer and waits until the moves are done; an error or an alarm of the board stops it with its
    # meaning; a board without homing ($22=0) says so for Home; laser mode off ($32=0) is pointed out; the
    # machine type of Settings → Machine picks the controller; a whole job: G92 at the head, then the G-code
    import time as _gtime
    import kerfly.core.grbl as _grbl
    from kerfly.core.laser import LaserError as _LErr
    gb = FakeGrbl(busy_reports=3)
    gc = _grbl.GrblController(opener=lambda port, baud: gb)
    gc.connect(port="/dev/ttyFAKE")
    long = ["G1 X%d.123 Y%d.456 S500 F1200" % (i, i) for i in range(400)]
    gc.stream(long)
    stream_ok = not gb.overflow and gb.lines.count("G1 X399.123 Y399.456 S500 F1200") == 1 and gb.state == "Idle"
    errors = []
    for bad in (["G1 X1 Y1 F100", "FOO"], ["$H"]):
        if bad == ["$H"]:
            gb._line = lambda line, gb=gb: setattr(gb, "out", gb.out + b"ALARM:9\r\n")
        try:
            gc.stream(bad) if bad != ["$H"] else gc.home()
        except _LErr as e:
            errors.append(str(e))
    errors_ok = len(errors) == 2 and "error 20" in errors[0] and "alarm 9" in errors[1]
    nb = FakeGrbl(homing=False)
    nb.settings["$32"] = "0"
    nc = _grbl.GrblController(opener=lambda port, baud: nb)
    nc.connect(port="/dev/ttyFAKE", init_home=True)
    try:
        nc.home()
        no_home = False
    except _LErr as e:
        no_home = "$22=0" in str(e) and "$H" not in nb.lines
    _ports = _grbl.serial_ports
    _open = _grbl.open_serial
    _grbl.serial_ports = lambda: [("/dev/ttyFAKE", "stand-in")]
    _grbl.open_serial = lambda port, baud: nb
    mw = make_window(grid_mm="0", machine="grbl", post_disp="0", grbl_air="1", board_name="LASER-M3")
    is_grbl = mw.is_grbl()
    mw.connect_laser()
    laser_mode = "$32=1" in mw.statusBar().currentMessage()
    # only what a GRBL laser has: no test fire (a K40 M3 board's), no EGV files; "Connected (GRBL)"
    k40_things_hidden = not mw.test_fire_row.isVisibleTo(mw) and not mw.act_save_egv.isVisible() \
        and not mw.act_send_egv.isVisible() and "GRBL" in mw.laser_label.text()
    mw._preview_drawn("rectangle", QPointF(20, 20), QPointF(60, 50), False)
    mw.start_job()
    gt0 = _gtime.time()
    while mw.worker is not None and _gtime.time() - gt0 < 30:
        app.processEvents()
        _gtime.sleep(0.02)
    job_ok = "G92 X0 Y0" in nb.lines and nb.lines.index("G92 X0 Y0") < nb.lines.index("M4 S0") and \
        any(l.startswith("$J=") for l in nb.lines)
    # air assist (the laser's setting): M8 right after the start, M9 after the laser goes off
    air_ok = "M8" in nb.lines and nb.lines.index("M8") == nb.lines.index("M4 S0") + 1 and "M9" in nb.lines \
        and nb.lines.index("M9") == nb.lines.index("M5 S0") + 1
    mw._apply_settings(dict(mw.values, machine="k40"), {"machine"})
    back = not mw.is_grbl() and not mw.laser.connected and mw.act_save_egv.isVisible()
    mw._dirty = False
    mw.close()
    _grbl.serial_ports, _grbl.open_serial = _ports, _open
    check("GRBL laser (stand-in board): stream within the buffer, waits for Idle; error / alarm stop it with their "
          "meaning; no homing and laser mode off are said; Settings picks the controller; a job: G92, G-code, "
          "air assist M8 / M9; no K40 things shown (test fire, EGV)",
          stream_ok and errors_ok and no_home and is_grbl and laser_mode and job_ok and back and air_ok
          and k40_things_hidden,
          "(%s)" % [stream_ok, errors, no_home, is_grbl, laser_mode, job_ok, back, air_ok, k40_things_hidden])

    # 28f2. a laser's settings show only what its machine has: a GRBL laser no K40 board, USB, power setting
    # or rail (their sections hidden), a K40 no GRBL fields; air assist is a GRBL laser's tick, saved with it
    from kerfly.gui.settings_dialog import SettingsForm as _SF2
    shown_ok = []
    for machine in ("grbl", "k40"):
        sw = make_window(grid_mm="0", machine=machine, board_name="LASER-M3")
        form = _SF2(dict(sw.values), machine=True, window=sw)
        form.resize(900, 900)
        form.show()
        app.processEvents()
        vis = {k: form._widgets[k].isVisible() for k in ("board_name", "usb_port", "show_power", "post_home",
                                                         "pre_pr_crc", "t_timeout", "grbl_port", "grbl_air",
                                                         "grbl_jog", "LaserXsize")}
        sections = {s.title.text(): s.isVisible() for s, _keys in form._sections if s.title is not None}
        if machine == "grbl":
            form._widgets["grbl_air"].setChecked(True)
            shown_ok.append(vis["grbl_air"] and vis["grbl_port"] and vis["grbl_jog"] and vis["LaserXsize"]
                            and not any(vis[k] for k in ("board_name", "usb_port", "show_power", "post_home",
                                                         "pre_pr_crc", "t_timeout"))
                            and not sections.get(_("USB connection"), True)
                            and not sections.get(_("Power (M3 board)"), True)
                            and form.result_values()[0]["grbl_air"] == "1")
        else:
            shown_ok.append(vis["board_name"] and vis["usb_port"] and vis["show_power"] and vis["pre_pr_crc"]
                            and not vis["grbl_air"] and not vis["grbl_port"] and not vis["grbl_jog"]
                            and not sections.get(_("Head movement"), True))
        form.close()
        sw._dirty = False
        sw.close()
    check("a laser's settings show only what its machine has (GRBL: no K40 board, USB, power, rail; K40: no "
          "GRBL fields; empty sections hidden); air assist is a GRBL laser's tick", all(shown_ok), "(%s)" % shown_ok)

    # 28g. speeds in mm/min for a GRBL machine only (the K40 stays in mm/s): the layers, the material test (its
    # fields and the speeds engraved on it), Settings and the material library show and take mm/min; what is
    # kept stays mm/s, so the K40 jobs and the profiles do not change
    from kerfly.gui.generators import GeneratorDialog as _SGD
    from kerfly.gui.settings_dialog import SettingsForm as _SLF
    from kerfly.gui.materials_dialog import MaterialsDialog as _SMD
    from PySide6.QtWidgets import QDoubleSpinBox as _SDS
    shown = {}
    for machine in ("k40", "grbl"):
        sw = make_window(grid_mm="0", machine=machine)
        sw._preview_drawn("rectangle", QPointF(20, 20), QPointF(60, 50), False)
        cut = next(l for l in sw.layers if l.kind == "cut")
        spin = sw.layers_panel.rows[cut.id]["speed"]
        f = 60.0 if machine == "grbl" else 1.0
        layer_ok = ("(%s)" % ("mm/min" if f > 1 else "mm/s") in sw.layers_panel.speed_header.text()
                    and abs(spin.value() - cut.speed * f) < 1e-6)
        spin.setValue(300.0 if f > 1 else 12.0)
        typed_ok = abs(cut.speed - (5.0 if f > 1 else 12.0)) < 1e-9
        gd = _SGD(sw, "material_test", remember=False)
        des = gd.result_design()
        mt_ok = abs(gd.widgets["speed_min"].value() - gd.values()["speed_min"] * f) < 1e-6 and \
            des.layers[0].name.startswith("%g %s" % (des.layers[0].speed * f, "mm/min" if f > 1 else "mm/s"))
        gd.deleteLater()
        sd = _SLF(sw.values, machine=True, window=sw)                       # the laser's settings
        ts = next(c for c in sd.findChildren(_SDS) if c.property("setting_key") == "trace_speed")
        set_ok = abs(ts.value() - float(sw.values["trace_speed"]) * f) < 1e-6 and \
            abs(float(sd._getters["trace_speed"]()) - float(sw.values["trace_speed"])) < 1e-6
        md = _SMD(sw.materials, {}, "mm", sw, speed_factor=config.speed_factor(sw.values))
        mat_ok = "(%s)" % ("mm/min" if f > 1 else "mm/s") in md.speed_header.text()      # the table's header
        shown[machine] = [layer_ok, typed_ok, mt_ok, set_ok, mat_ok]
        sw._dirty = False
        sw.close()
    check("speeds: mm/s for the K40, mm/min for a GRBL machine (layers, material test, Settings, materials); "
          "kept in mm/s", all(all(v) for v in shown.values()), "(%s)" % shown)

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

    # 31. lines without the outline (the former hatch) from the Fill section of the options bar:
    # its settings appear, only engraved lines, no cut; no separate Hatch section any more
    w = make_window(grid_mm="0")
    w._preview_drawn("rectangle", QPointF(20, 20), QPointF(60, 50), False)
    bar_set(w, "fill_pattern", "lines")
    bar_set(w, "fill_spacing", 0.5)
    bar_set(w, "fill_outline", False)
    labels = [l.text() for l in w.tool_options.findChildren(QLabel)]
    e = w.selected
    lines_ok = e.design.vector_engrave.ecoords and not e.design.vector_cut.ecoords
    check("fill with lines, no outline (former hatch): settings shown, engraved lines only, no Hatch section",
          lines_ok and "Fill" in labels and "Hatch" not in labels, "(%s)" % labels)
    bar_set(w, "fill_outline", True)                     # back to a plain cut shape for the bridges
    bar_set(w, "fill_pattern", "")
    bar_set(w, "tabs", 2)
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
    auto_speed = dlg.speed.currentData() >= 5                 # 5x at least (a long job faster)
    dlg.skip_layer()
    skipped = dlg.time > 0
    dlg.seek(dlg.total)
    drawn = len(dlg.items) >= 2 and auto_speed and skipped
    from kerfly.gui.simulation import SimulationDialog as _SD
    w.simulate_job()                                    # clicked again: the same window, not a second one
    app.processEvents()
    drawn = drawn and w._simulation is dlg and len([d for d in w.findChildren(_SD) if d.isVisible()]) == 1
    # its own window and preview (docs/ui-mockups/Simulation): nothing drawn on the main bed view
    own = dlg.scene is not w.preview.scene() and all(it.scene() is dlg.scene for it in dlg.items)
    # the design changes while it is open: after a pause the job is worked out again, at the same place in
    # time, paused, with a note; a change that is not the job's (a selection) changes nothing
    if dlg.timer.isActive():
        dlg.toggle()                                    # paused (at 5x it would run on while the test waits)
    dlg.seek(dlg.total * 0.5)
    total_before = dlg.total
    w.elements[0].x += 20 / 25.4
    w._layout_changed()
    waited = dlg.refresh_timer.isActive()
    import time as _time
    t_end = _time.time() + 2
    while dlg.refresh_timer.isActive() and _time.time() < t_end:
        app.processEvents()
        _time.sleep(0.02)
    app.processEvents()
    followed = (waited and abs(dlg.time - dlg.total * 0.5) < 0.05 * dlg.total + 1e-6 and not dlg.timer.isActive()
                and dlg.info.text() == _("The design changed: the simulation was worked out again")
                and abs(dlg.total - total_before) < 1e-6 + 0.5 * total_before)
    # New: another design, the simulation closes
    w._dirty = False
    w.new_project()
    app.processEvents()
    closed = w._open_simulation() is None
    check("simulation: plays, draws the path in its own window, follows a change of the design (paused, at "
          "its place, a note), New closes it", played and drawn and own and followed and closed,
          "(%.1f s, own %s, followed %s, closed %s)" % (dlg.total if dlg else 0, own, followed, closed))
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

    def rows():                                  # the elements' rows (a group's row is -1)
        return sorted(lst.row(i) for i in lst.selectedItems() if lst.row(i) >= 0)
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
    lst.item(0).setSelected(True)                       # a group member's own row: that element alone
    member_alone = rows() == [0] and w.preview.selected_elements() == [e1] and w._selection() == [e1]
    lst.clearSelection()
    lst.group_item(e1.group).setSelected(True)          # the group's row: the whole group
    group_rows = rows() == [0, 1] and len(w.preview.selected_elements()) == 2 and \
        lst.group_item(e1.group).isSelected()
    w.preview.scope = ""                                # as after a click on the empty bed
    w.preview.select_element(e2)                        # a click on the bed: the whole group
    bed_group = len(w._selection()) == 2
    check("element list <-> bed selection: one, several, from the list, a member's row alone, a group's row, "
          "the bed takes the group",
          one and several and from_list and member_alone and group_rows and bed_group,
          "(%s)" % [one, several, from_list, member_alone, group_rows, bed_group])
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
    check("report a problem: in the Help menu, not on the ribbon (docs/ui-mockups/Main)",
          w.act_report_problem in [a for m in w.menuBar().actions() for a in m.menu().actions()]
          and not any(getattr(b, "defaultAction", lambda: None)() is w.act_report_problem
                      for b in w.findChildren(QToolButton)))

    # 44. Fill tool: click a closed shape to fill it with a pattern (one undo step), the outline
    # stays a cut; the options bar shows the patterns; an opened file must be ungrouped first
    from PySide6.QtCore import QPointF as _QPointF
    from kerfly.core.shapes import ShapeSpec as _Spec
    w3 = make_window(grid_mm="0")
    w3._add_drawn_element(_Spec(kind="ellipse", width=60, height=40, operation="cut"), "ellipse", 20, 20)
    w3._add_drawn_element(_Spec(kind="rectangle", width=30, height=30, operation="cut"), "rectangle", 120, 20)
    shape, square = w3.elements[0], w3.elements[1]       # the square is selected (just drawn)
    w3.set_tool("fill")
    combos = [c for c in w3.tool_options.findChildren(QComboBox) if c.findData("honeycomb") >= 0]
    if combos:
        combos[0].setCurrentIndex(combos[0].findData("honeycomb"))
        combos[0].activated.emit(combos[0].currentIndex())          # as a mouse choice does
    selected_got_it = square.shape.fill_pattern == "honeycomb" and shape.shape.fill_pattern == ""
    undo0 = len(w3._undo)
    w3._fill_clicked(_QPointF(50, 40))                    # inside the ellipse
    filled = shape.shape.fill_pattern == "honeycomb" and bool(shape.design.vector_cut.ecoords) \
        and len(shape.design.vector_engrave.ecoords) > 50 and len(w3._undo) == undo0 + 1
    w3.undo()
    shape = w3.elements[0]
    undone = shape.shape.fill_pattern == "" and not shape.design.vector_engrave.ecoords
    w3.load_design(os.path.join(FIX, "shapes.dxf"), add=True)
    file_el = [e for e in w3.elements if e.shape is None]
    if file_el:
        b = file_el[0].bounds
        w3._fill_clicked(_QPointF((b[0] + b[1]) / 2 * 25.4, -(b[2] + b[3]) / 2 * 25.4))
    msg = w3.statusBar().currentMessage()
    check("fill tool: patterns, click fills (one undo step), outline stays, files need Ungroup",
          bool(combos) and selected_got_it and filled and undone and bool(file_el) and "Ungroup" in msg,
          "(%s)" % ([bool(combos), selected_got_it, filled, undone, msg[:40]],))
    w3._dirty = False
    w3.close()

    # 45. order of elements = order of the job (top of the list first): down / up one place, to the
    # end / start, a message at the end, undo, toolbar
    w4 = make_window(grid_mm="0")
    for i in range(4):
        w4._add_drawn_element(_Spec(kind="rectangle", width=20, height=20), "rectangle", 10 + 30 * i, 10)
    a, b, c, d = w4.elements
    select(w4, b)
    w4.reorder_selected("down")
    step = w4.elements == [a, c, b, d]
    w4.reorder_selected("last")
    last = w4.elements == [a, c, d, b]
    w4.reorder_selected("down")
    already = w4.statusBar().currentMessage() == _("Already at the end of the list.") \
        and w4.elements == [a, c, d, b]
    w4.reorder_selected("first")
    first = w4.elements == [b, a, c, d]
    w4.reorder_selected("up")
    already_top = w4.statusBar().currentMessage() == _("Already at the start of the list.")
    w4.undo()
    undone = w4.elements == [a, c, d, b]
    on_bar = any(getattr(t, "defaultAction", lambda: None)() is w4.act_order["up"]
                 for t in w4.findChildren(QToolButton))
    beside_list = any(b.defaultAction() is w4.act_order["up"] and w4.element_header.isAncestorOf(b)
                      for b in w4.findChildren(QToolButton))
    on_bar = on_bar and beside_list
    check("element order: down, to the end, already at the end, to the start, undo, buttons in the list's header",
          step and last and already and first and already_top and undone and on_bar,
          "(%s)" % ([step, last, already, first, already_top, undone, on_bar],))
    w4._dirty = False
    w4.close()

    # single-line fonts built into Kerfly (Hershey, EMS): at the top of the font list; open strokes engraved
    # once (no raster, no closed outlines), raster fill switched to outline engrave, Polish letters, text on a
    # path, kept in projects
    from kerfly.core import stroke_fonts as _sf, project as _proj2
    from kerfly.gui.text_shapes import update_text_spec as _uts2
    from kerfly.gui.font_box import FontBox as _FB
    fams = _sf.families()
    sw2 = make_window(grid_mm="0", follow_head="0")
    tt = _Spec(kind="text", text="Zażółć gęślą jaźń", font_size=10, operation="fill")
    _uts2(tt)
    sw2._add_drawn_element(tt, "text", 10, 30)
    te = sw2.elements[-1]
    select(sw2, te)
    box = next(wd for wd in sw2.tool_options.findChildren(_FB))
    on_top = [box.itemText(i) for i in range(len(fams))] == fams
    bar_set(sw2, "font_family", "Hershey Sans 1-stroke")
    te = sw2.elements[-1]
    single = te.shape.single_line and not te.shape.closed and te.shape.operation == "engrave"
    d = te.design
    from kerfly.core.layers import part_present as _pp
    vector_only = not _pp(d, "raster") and not _pp(d, "cut")
    strokes = len(te.shape.text_outlines)
    open_lines = sum(1 for p in te.shape.text_outlines if p[0] != p[-1]) > strokes // 2
    polish = all(ch in _sf._load("Hershey Sans 1-stroke").glyphs for ch in "ąćęłńóśźżĄĆĘŁŃÓŚŹŻ")
    engrave_data = _pp(d, "engrave")
    saved2 = _proj2._shape_from_dict(_proj2._shape_to_dict(te.shape))
    kept2 = saved2.font_family == "Hershey Sans 1-stroke" and saved2.single_line
    from kerfly.gui.text_shapes import path_text_outlines as _pto
    on_path = _pto("ABC", "EMS Tech", 8, False, False, [(0, 0), (50, 0), (50, 50)], 5.0)
    path_ok = len(on_path) > 3 and all(len(p) >= 2 for p in on_path)
    from kerfly.gui import truth as _tr2
    shown = _tr2.check_window(sw2)
    sw2.close()
    check("single-line fonts: at the top of the font list, open strokes engraved once (fill becomes engrave), "
          "Polish letters, text on a path, kept in projects, the window tells the truth",
          len(fams) == 18 and on_top and single and vector_only and strokes > 20 and polish and engrave_data
          and kept2 and path_ok and not shown and open_lines,
          "(%s)" % [len(fams), on_top, single, vector_only, strokes, polish, engrave_data, kept2, path_ok, shown])

    # 46. text on a path: centred above a line, stays in place when edited and after moving it,
    # other side below the line, back to straight text; saved in projects
    from kerfly.gui.text_shapes import update_text_spec as _uts
    from kerfly.core import project as _project
    w5 = make_window(grid_mm="0", follow_head="0")
    w5._add_drawn_element(_Spec(kind="line", width=100, height=0, operation="cut"), "line", 20, 60)
    t = _Spec(kind="text", text="KERFLY", font_size=10, operation="engrave")
    _uts(t)
    w5._add_drawn_element(t, "text", 10, 150)
    guide, text = w5.elements
    select(w5, guide, text)
    w5.put_text_on_path()
    b = [v * 25.4 for v in text.bounds]
    centred = abs((b[0] + b[1]) / 2 - 70.0) < 2.0 and abs(b[2] + 60.0) < 0.6 and b[3] > -60.0
    w5.sel_fields["x"].setValue(w5.sel_fields["x"].value() + 10)   # moved 10 mm right, then edited
    bar_set(w5, "text", "KERFLY!")
    b2 = [v * 25.4 for v in text.bounds]
    kept = abs(b2[0] - (b[0] + 10.0)) < 0.6 and abs(b2[2] - b[2]) < 0.6
    bar_set(w5, "text_path_flip", True)
    below = text.bounds[3] * 25.4 <= -60.0 + 0.6
    saved = _project._shape_from_dict(_project._shape_to_dict(text.shape))
    in_project = saved.text_path_flip and len(saved.text_path) == len(text.shape.text_path)
    click_bar_button(w5, _("Straight text"))
    # height of a 10 mm text in whatever font the system has (Windows has no DejaVu Sans)
    straight = not text.shape.text_path and 4.0 < text.size[1] * 25.4 < 14.0
    # the Text on a path tool: click near the line -> a new text on it; dragging slides it
    # along the line (it stays on it); spacing makes it longer; distance lifts it off the line
    select(w5)                                              # no text selected: the tool makes a new one
    w5.set_tool("textpath")
    tool_bar_text = w5._options_target == "textpath"
    w5.shape_defaults["textpath"].text = "ABC"
    n0 = len(w5.elements)
    w5._shape_picked("textpath", _QPointF(70, 61))           # 1 mm below the line
    t2 = w5.elements[-1]
    made = len(w5.elements) == n0 + 1 and t2.shape.text == "ABC" and bool(t2.shape.text_path) \
        and w5.preview.tool == "select"
    left0 = t2.bounds[0]
    select(w5, t2)
    w5._preview_moved(t2, 15 / 25.4, 8 / 25.4)               # drag right (and a bit up)
    slid = abs((t2.bounds[0] - left0) * 25.4 - 15.0) < 0.6 and abs(t2.bounds[2] * 25.4 + 60.0) < 0.6
    w_before = t2.size[0]
    bar_set(w5, "text_spacing", 2.0)
    bar_set(w5, "text_path_distance", 3.0)
    spaced = t2.size[0] * 25.4 > w_before * 25.4 + 3.5 and abs(t2.bounds[2] * 25.4 + 57.0) < 0.6
    check("text on a path tool: click puts a text on the line, drag slides along it, spacing, distance",
          tool_bar_text and made and slid and spaced, "(%s)" % ([tool_bar_text, made, slid, spaced],))
    # a selected text is moved onto the clicked shape: no second copy stays behind
    t3 = _Spec(kind="text", text="MOVE ME", font_size=8, operation="engrave")
    _uts(t3)
    w5._add_drawn_element(t3, "text", 20, 120)               # drawn: selected
    plain_text = w5.elements[-1]
    n1 = len(w5.elements)
    w5.set_tool("textpath")
    shows_it = w5._options_element is plain_text
    w5._shape_picked("textpath", _QPointF(30, 60))
    moved_on = len(w5.elements) == n1 and bool(plain_text.shape.text_path) \
        and abs(plain_text.bounds[2] * 25.4 + 60.0) < 0.6
    check("text on a path tool: the selected text goes onto the shape (no copy left)", shows_it and moved_on,
          "(%s)" % ([shows_it, moved_on, len(w5.elements) - n1],))

    # changing a text on a path in the options bar, several times in a row (the bar kept an old copy
    # of the path, so every change moved the text further: +10, +20, +30 mm; the font jumped too)
    from PySide6.QtGui import QFont as _QFont
    from PySide6.QtWidgets import QDoubleSpinBox as _QDSB
    select(w5, t2)
    off = [sp for sp in w5.tool_options.findChildren(_QDSB) if sp.toolTip().startswith(_("Position along the path"))]
    lefts = []
    for _i in range(3):
        off[0].setValue(off[0].value() + 10.0)
        lefts.append(t2.bounds[0] * 25.4)
    steps_ok = all(abs((b - a) - 10.0) < 0.3 for a, b in zip(lefts, lefts[1:]))
    width0, left0 = t2.size[0], t2.bounds[0]
    before_font = t2.shape.font_family
    # another font, set through the options bar the way its font list does it (on the Windows CI
    # the font list can be empty without a screen, so the family name comes from the font database)
    from PySide6.QtGui import QFontDatabase as _QFDB
    other = next((f for f in _QFDB.families() if f != before_font and "Symbol" not in f
                  and not f.startswith(("Wingdings", "Webdings", "Marlett"))), "Arial")
    bar_set(w5, "font_family", other)
    font_ok = t2.shape.font_family != before_font and abs(t2.bounds[0] - left0) * 25.4 < 1.0 \
        and abs(t2.bounds[2] * 25.4 + 57.0) < 0.6
    check("text on a path: changes in the options bar move it exactly, the font changes in place",
          bool(off) and steps_ok and font_ok, "(steps %s, font %s)" % ([round(b - a, 2) for a, b in zip(lefts, lefts[1:])],
                                                                      t2.shape.font_family))

    # the options of a selected text (all its sections) scroll instead of widening the window
    select(w5, text)
    narrow = w5.minimumSizeHint().width() < 1100
    check("text on a path: centred, kept when edited / moved, other side, saved, straight again",
          centred and kept and below and in_project and straight,
          "(%s)" % ([centred, kept, below, in_project, straight],))
    check("options bar scrolls: a selected text does not make the window wider",
          narrow, "(minimum width %d px)" % w5.minimumSizeHint().width())
    w5._dirty = False
    w5.close()

    # 47. Living hinge tool: click a closed shape -> cuts inside (one undo step), the Living hinge
    # section shows on that shape; a text gets none
    w6 = make_window(grid_mm="0")
    w6._add_drawn_element(_Spec(kind="rectangle", width=120, height=60, operation="cut"), "rectangle", 20, 20)
    box = w6.elements[0]
    select(w6)
    w6.set_tool("hinge")
    tool_bar = w6._options_target == "hinge"
    plain_n = len(box.design.vector_cut.ecoords)
    u0 = len(w6._undo)
    w6._shape_picked("hinge", _QPointF(80, 50))
    cut_in = box.shape.hinge_pattern == "straight" and len(box.design.vector_cut.ecoords) > plain_n * 20 \
        and len(w6._undo) == u0 + 1
    w6.set_tool("select")
    select(w6, box)
    section = any(c.findData("zigzag") >= 0 for c in w6.tool_options.findChildren(QComboBox))
    w6.undo()
    undone = not w6.elements[0].shape.hinge_pattern
    check("living hinge tool: click cuts a hinge (one undo step), its section on the shape, undo",
          tool_bar and cut_in and section and undone, "(%s)" % ([tool_bar, cut_in, section, undone],))
    w6._dirty = False
    w6.close()

    # 48. Fill tool with several shapes selected: the bar shows what they have ("no pattern", not the
    # pattern a click gives), every choice reaches all of them (the selection was lost after the
    # first change), and a number changed under "no pattern" fills nothing
    w7 = make_window(grid_mm="0")
    for i in range(4):
        w7._add_drawn_element(_Spec(kind="rectangle", width=30, height=30, operation="cut"), "rectangle",
                              10 + 40 * i, 10)
    boxes = list(w7.elements)
    select(w7, *boxes[:3])
    w7.set_tool("fill")
    combo = [c for c in w7.tool_options.findChildren(QComboBox) if c.findData("waves") >= 0][0]
    shows_none = combo.currentData() == ""
    bar_set(w7, "fill_spacing", 3.0)                       # under "no pattern": nothing is filled
    none_kept = all(not e.shape.fill_pattern for e in w7.elements) and w7.fill_defaults.fill_pattern == "lines"
    seen = []
    for code in ("lines", "waves", "honeycomb"):
        bar_set(w7, "fill_pattern", code)
        seen.append([e.shape.fill_pattern for e in w7.elements[:3]])
    multi_ok = seen == [["lines"] * 3, ["waves"] * 3, ["honeycomb"] * 3]
    w7._fill_clicked(QPointF(10 + 120 + 15, 25))           # a click on the fourth gives the last choice
    clicked_ok = w7.elements[3].shape.fill_pattern == "honeycomb" and w7.elements[3].shape.fill_spacing == 3.0
    select(w7, *boxes[:3])
    w7.set_tool("hinge")
    hcombo = [c for c in w7.tool_options.findChildren(QComboBox) if c.findData("wave") >= 0][0]
    hinge_none = hcombo.currentData() == ""
    # a selected shape clicked with the tool: the bar shows what it got (it stayed "no hinge")
    w7.set_tool("select")
    select(w7, boxes[0])
    w7.set_tool("hinge")
    w7._hinge_clicked(QPointF(25, 25))
    hcombo = [c for c in w7.tool_options.findChildren(QComboBox) if c.findData("wave") >= 0][0]
    hinge_none = hinge_none and boxes[0].shape.hinge_pattern == "straight" and hcombo.currentData() == "straight"
    check("fill tool with several shapes: shows \"no pattern\", each choice reaches all of them",
          shows_none and none_kept and multi_ok and clicked_ok and hinge_none,
          "(none %s, kept %s, %s, click %s, hinge %s)" % (shows_none, none_kept, seen, clicked_ok, hinge_none))
    w7._dirty = False
    w7.close()

    # 51. the "window tells the truth" checks find what they should: a field not refreshed, an element
    # drawn elsewhere, a stale list row, a wrong layer list, a missing field; and a saved and reopened
    # project has the same state
    from kerfly.gui import truth as _truth
    w10 = make_window(grid_mm="0")
    w10._add_drawn_element(_Spec(kind="rectangle", width=30, height=20, operation="cut"), "rectangle", 10, 10)
    w10._add_drawn_element(_Spec(kind="ellipse", width=30, height=20, operation="cut"), "ellipse", 60, 10)
    r10, e10 = w10.elements
    select(w10, r10)
    clean = _truth.check_window(w10) == []
    found = {}
    spec = r10.shape.copy()                               # data changed behind the bar's back
    spec.tabs = 3
    r10.shape = spec
    found["bar"] = any("'tabs' shows 0, should be 3" in p for p in _truth.check_window(w10))
    spec.tabs = 0
    r10.x += 5 / 25.4                                     # moved without redrawing
    found["bed"] = any("bed view: Rectangle" in p for p in _truth.check_window(w10))
    found["fields"] = any("position fields: x" in p for p in _truth.check_window(w10))
    r10.x -= 5 / 25.4
    e10.visible = False                                   # left out of the job without the list knowing
    found["list"] = any("element list row 2" in p and "tick" in p for p in _truth.check_window(w10))
    e10.visible = True
    r10.layers["cut"] = w10.add_layer("cut").id           # the Layer list above the bed not updated
    w10.layer_assign_box.findChildren(QComboBox)[0].blockSignals(True)
    w10.layer_assign_box.findChildren(QComboBox)[0].setCurrentIndex(0)
    found["layer"] = any("layer choice for Rectangle" in p for p in _truth.check_window(w10))
    w10.refresh_preview()
    for f in w10.tool_options.findChildren(QWidget):     # a field gone from the bar
        if f.property("spec_attr") == "corner_radius":
            f.hide()
    found["missing"] = any("'corner_radius' is missing" in p for p in _truth.check_window(w10))
    w10._update_tool_options(force=True)
    before = _truth.state(w10)
    path = tempfile.mktemp(suffix=".kerfly")
    w10._write_project(path)
    w11 = make_window(grid_mm="0")
    w11.open_project(path)
    os.remove(path)
    same = _truth.difference(before, _truth.state(w11)) == ""
    check("truth checks: a clean window passes, each kind of wrong display is found, reopened project same",
          clean and all(found.values()) and same, "(%s, same %s)" % (found, same))
    for win in (w10, w11):
        win._dirty = False
        win.close()

    # 52. grid, snapping and "design follows the head" are remembered for the next start at once
    # (without "Save settings as default"); switching the grid on again uses the last size; the
    # Settings dialog (View tab) changes them too
    from kerfly.gui import viewstate as _viewstate
    v1 = make_window(grid_mm="0")
    v1.remember_geometry = True
    v1.set_grid(2)
    v1.toggle_snap(False)
    v1.act_snap.setChecked(False)
    v1.act_snap_objects.trigger()                           # off
    v1.act_follow_head.trigger()                            # on
    grid_off = v1.values["grid_mm"] == "0"
    v1._dirty = False
    v1.close()
    vals = _viewstate.load(dict(config.DEFAULT_VALUES))
    v2 = MainWindow(vals)
    OPEN_WINDOWS.append(v2)
    v2.remember_geometry = True
    remembered = (not v2.act_snap.isChecked() and not v2.act_snap_objects.isChecked()
                  and v2.act_follow_head.isChecked())
    v2.act_snap.trigger()                                    # grid on again: the last size
    last_size = v2._grid_mm() == 2.0
    v2.values["grid_mm"] = "10"                              # as the Settings dialog sets it
    v2.values["snap_objects"] = "1"
    v2._sync_view_actions()
    from_dialog = v2.act_snap.isChecked() and v2.act_snap_objects.isChecked() \
        and _viewstate.load({})["grid_mm"] in ("10", "10.0")
    v2._dirty = False
    OPEN_WINDOWS.remove(v2)
    v2.close()
    check("view settings remembered at once (grid on/off and size, snapping, follow head), Settings tab",
          grid_off and remembered and last_size and from_dialog,
          "(%s)" % ([grid_off, remembered, last_size, from_dialog],))

    # 52b. the language chosen in Settings is kept for the next start at once (it was lost unless the
    # settings were saved as default, so the new language never came after a restart)
    from kerfly.gui import settings_dialog as _sd
    lw = make_window(grid_mm="0")
    lw.remember_geometry = True
    _orig_exec, _orig_info = _sd.SettingsDialog.exec, QMessageBox.information

    def _pick_german(dlg):
        combo = next(c for c in dlg.findChildren(QComboBox) if c.findData("de") >= 0 and c.findData("") >= 0)
        combo.setCurrentIndex(combo.findData("de"))
        return True
    told = []
    _sd.SettingsDialog.exec = _pick_german
    QMessageBox.information = staticmethod(lambda *a, **k: told.append(a[2] if len(a) > 2 else ""))
    try:
        lw.edit_settings()
    finally:
        _sd.SettingsDialog.exec, QMessageBox.information = _orig_exec, _orig_info
    # the next start: the settings file (never saved here) and then window.ini
    next_start = _viewstate.load(config.load_user_settings())
    lang_ok = lw.values.get("language") == "de" and next_start.get("language") == "de" and bool(told)
    lw.values["language"] = ""                               # back to the system language
    lw._remember_view()
    lang_back = _viewstate.load({}).get("language") == ""
    lw._dirty = False
    lw.close()
    check("language from Settings is kept for the next start without Save settings as default",
          lang_ok and lang_back, "(%s)" % ([lang_ok, lang_back, next_start.get("language")],))

    # 52c. small screens (1366 x 768): the wheel changes a number field only after it was clicked
    # (scrolling down to Start changed the layer speeds on the way, a user's report); Start, Pause
    # and Stop stay visible below the scrolling panel
    from PySide6.QtCore import QPoint as _QPoint
    from PySide6.QtGui import QWheelEvent as _QWheelEvent
    sw = make_window(grid_mm="0")
    sw.resize(1366, 700)
    sw.show()
    sw._preview_drawn("rectangle", QPointF(20, 20), QPointF(60, 60), False)
    app.processEvents()
    speed = next(r["speed"] for r in sw.layers_panel.rows.values() if "speed" in r)
    bar = sw.panel_scroll.verticalScrollBar()

    def _wheel(widget):
        pos = QPointF(widget.rect().center())
        QApplication.sendEvent(widget, _QWheelEvent(pos, QPointF(widget.mapToGlobal(pos.toPoint())), _QPoint(0, 0),
                                                    _QPoint(0, -120), Qt.NoButton, Qt.NoModifier, Qt.NoScrollPhase,
                                                    False))
        app.processEvents()
    bar.setValue(0)
    before = speed.value()
    _wheel(speed)
    untouched = speed.value() == before and (bar.maximum() == 0 or bar.value() > 0)
    sw.activateWindow()
    app.processEvents()
    speed.setFocus()
    app.processEvents()
    _wheel(speed)
    clicked = speed.value() != before
    pinned = not sw.panel_scroll.isAncestorOf(sw.btn_start) and sw.btn_start.isVisible()
    check("wheel over a number field not clicked scrolls the panel; clicked, it changes the value; Start "
          "stays below the panel", untouched and clicked and pinned,
          "(%s)" % [untouched, clicked, pinned, bar.value(), bar.maximum()])
    sw._dirty = False
    sw.close()

    # 52d. new versions: a bar above the bed with a link to the release; skipping a version; the
    # manual check says when there is nothing new; switched off in Settings: no check at start
    from kerfly.core import updates as _upd
    from PySide6.QtGui import QDesktopServices
    uw = make_window(grid_mm="0")
    uw.remember_geometry = True
    uw.show()

    def _answer(version):
        return lambda current, timeout=6.0: _upd.Release(version, "https://github.com/cyryllo/Kerfly/releases/tag/v"
                                                         + version)

    def _run_check(**kw):
        uw.check_for_updates(**kw)
        uw._update_check.wait(5000)
        for _i in range(5):
            app.processEvents()
    _run_check(manual=True, fetch=_answer("99.0"))
    shown = uw.update_bar.isVisible() and "99.0" in uw.update_bar.text.text()
    opened = []
    _orig_open = QDesktopServices.openUrl
    QDesktopServices.openUrl = staticmethod(lambda url: opened.append(url.toString()) or True)
    try:
        uw.update_bar.open_button.click()
    finally:
        QDesktopServices.openUrl = _orig_open
    linked = opened == ["https://github.com/cyryllo/Kerfly/releases/tag/v99.0"]
    uw.update_bar.skip_button.click()
    skipped = not uw.update_bar.isVisible() and uw.values.get("update_skip") == "99.0"
    _run_check(manual=False, fetch=_answer("99.0"))
    not_again = not uw.update_bar.isVisible()
    from kerfly import __version__ as _kv
    _run_check(manual=True, fetch=_answer(_kv))
    newest = _kv in uw.statusBar().currentMessage() and not uw.update_bar.isVisible()

    def _offline(current, timeout=6.0):
        raise OSError("no internet")
    _run_check(manual=True, fetch=_offline)
    offline = "no internet" in uw.statusBar().currentMessage()
    asked = []
    _orig_check = uw.check_for_updates
    uw.check_for_updates = lambda **kw: asked.append(kw)
    uw.values["check_updates"], uw.values["update_last"] = "0", "0"
    uw.check_updates_on_start()
    off_ok = asked == []
    uw.values["check_updates"] = "1"
    uw.check_updates_on_start()
    on_ok = asked == [{"manual": False}]
    uw.check_for_updates = _orig_check
    check("new versions: bar with a link to the release, skip a version, nothing new / offline said, "
          "off in Settings", shown and linked and skipped and not_again and newest and offline and off_ok and on_ok,
          "(%s)" % [shown, linked, skipped, not_again, newest, offline, off_ok, on_ok])
    uw.values["check_updates"], uw.values["update_skip"] = "1", ""
    uw._dirty = False
    uw.close()

    # 52e. clipboard as in Inkscape: copy / paste (a new group, 5 mm further when the mouse is not on
    # the bed), paste in place, cut + undo, select all, Esc, layers by name; Ctrl+C in a text field
    # copies the text, not the elements
    from PySide6.QtTest import QTest as _QT
    from PySide6.QtWidgets import QLineEdit as _QLE
    from PySide6.QtCore import QPoint
    from PySide6.QtGui import QCursor
    cw = make_window(grid_mm="0")
    cw.resize(1200, 800)
    cw.show()
    app.processEvents()
    cw._preview_drawn("rectangle", QPointF(20, 20), QPointF(60, 60), False)
    cw._preview_drawn("ellipse", QPointF(80, 20), QPointF(120, 50), False)
    ca, cb = cw.elements
    cw.preview.select_element([ca, cb])
    cw.group_selected()
    from kerfly.core.layers import Layer as _Layer
    second = _Layer("cut", name="Cut 2", color="#2e7d32", speed=5.0)
    cw.layers.append(second)
    cb.layers = {"cut": second.id}
    cw.preview.select_element([ca])
    app.processEvents()
    QCursor.setPos(cw.mapToGlobal(QPoint(5, 5)))            # not over the bed
    cw.act_copy.trigger()
    cw.act_paste.trigger()
    p1, p2 = cw.elements[2], cw.elements[3]
    pasted = (len(cw.elements) == 4 and p1.group and p1.group == p2.group and p1.group != ca.group
              and abs((p1.x - ca.x) * 25.4 - 5) < 1e-6 and p2.layers.get("cut") == second.id)
    cw.act_paste_in_place.trigger()
    in_place = len(cw.elements) == 6 and abs(cw.elements[4].x - ca.x) < 1e-9
    cw.act_select_all.trigger()
    app.processEvents()
    all_sel = len(cw.preview.selected_elements()) == 6
    cw.preview.setFocus()
    _QT.keyClick(cw.preview.viewport(), Qt.Key_Escape)
    app.processEvents()
    esc = cw.preview.selected_elements() == []
    cw.preview.select_element([cw.elements[-1]])
    cw.act_cut.trigger()
    cut_ok = len(cw.elements) == 4
    cw.undo()
    undo_ok = len(cw.elements) == 6
    cw.layers.remove(second)                                # its layer gone: the copy goes to the cut layer
    cw.act_paste.trigger()
    no_layer = "cut" not in cw.elements[-1].layers
    field = _QLE("text")
    field.setParent(cw)
    field.show()
    field.setFocus()
    field.selectAll()
    app.processEvents()
    before = cw._clipboard
    cw.preview.select_element([ca])
    field.setFocus()
    app.processEvents()
    _QT.keyClick(field, Qt.Key_C, Qt.ControlModifier)
    text_only = cw._clipboard is before
    check("clipboard: copy and paste (new group, layers by name), paste in place, cut + undo, select all, "
          "Esc, Ctrl+C in a text field", pasted and in_place and all_sel and esc and cut_ok and undo_ok and no_layer
          and text_only, "(%s)" % [pasted, in_place, all_sel, esc, cut_ok, undo_ok, no_layer, text_only])
    cw._dirty = False
    cw.close()

    # 52f. right-click menu: a right click without moving opens it (a right drag pans); on an element
    # it selects it and offers its commands, Layer moves all selected elements at once; on the empty bed:
    # Move the head here (greyed out without the laser), Paste, Select all
    rw = make_window(grid_mm="0")
    rw.resize(1200, 800)
    rw.show()
    for _settle in range(5):
        app.processEvents()
    rw.preview.fit_all()
    app.processEvents()
    rw._preview_drawn("rectangle", QPointF(20, 20), QPointF(60, 60), False)
    rw._preview_drawn("ellipse", QPointF(80, 20), QPointF(120, 50), False)
    r1, r2 = rw.elements
    from kerfly.core.layers import Layer as _Layer2, layer_of as _layer_of
    cut2 = _Layer2("cut", name="Cut 2", color="#2e7d32", speed=5.0)
    rw.layers.append(cut2)
    rvp = rw.preview.viewport()

    def _rclick(x, y):
        pos = rw.preview.mapFromScene(QPointF(x, y))
        QTest.mouseClick(rvp, Qt.RightButton, Qt.NoModifier, pos)
        for _i in range(3):
            app.processEvents()
        return rw._context_menu

    menu = _rclick(40, 40)
    texts = [a.text() for a in menu.actions()]
    on_element = (menu.isVisible() and rw.preview.selected_elements() == [r1] and rw.act_copy in menu.actions()
                  and _("Combine shapes") not in texts)
    menu.close()
    rw.preview.select_element([r1, r2])
    menu = _rclick(40, 40)                                 # on a selected element: the selection stays
    kept = len(rw.preview.selected_elements()) == 2 and _("Combine shapes") in [a.text() for a in menu.actions()]
    layer_menu = next(a.menu() for a in menu.actions() if a.menu() and a.menu().objectName() == "layer_submenu")
    next(a for a in layer_menu.actions() if a.text() == "Cut 2" and not a.isSeparator()).trigger()
    both = _layer_of(r1, "cut", rw.layers) is cut2 and _layer_of(r2, "cut", rw.layers) is cut2
    rw.undo()
    one_step = _layer_of(r1, "cut", rw.layers) is not cut2 and _layer_of(r2, "cut", rw.layers) is not cut2
    menu.close()
    menu = _rclick(250, 180)
    empty_texts = [a.text() for a in menu.actions()]
    here = next(a for a in menu.actions() if a.text() == _("Move the head here"))
    empty = rw.act_paste in menu.actions() and rw.act_select_all in menu.actions() and not here.isEnabled()
    menu.close()
    # a right drag pans and opens nothing
    rw._context_menu = None
    p0 = rw.preview.mapFromScene(QPointF(150, 150))
    QTest.mousePress(rvp, Qt.RightButton, Qt.NoModifier, p0)
    QApplication.sendEvent(rvp, QMouseEvent(QEvent.MouseMove, QPointF(p0 + QPoint(60, 40)),
                                            QPointF(rvp.mapToGlobal(p0 + QPoint(60, 40))), Qt.NoButton,
                                            Qt.RightButton, Qt.NoModifier))
    QTest.mouseRelease(rvp, Qt.RightButton, Qt.NoModifier, p0 + QPoint(60, 40))
    app.processEvents()
    drag_no_menu = rw._context_menu is None
    # the bed's white rectangle survives the right clicks (it vanished once: a user's report)
    drag_no_menu = drag_no_menu and rw.preview.bed_item.scene() is rw.preview.scene()
    check("right-click menu: element (selected, its commands), Layer moves all selected in one step, empty bed, "
          "a right drag only pans", on_element and kept and both and one_step and empty and drag_no_menu,
          "(%s %s)" % ([on_element, kept, both, one_step, empty, drag_no_menu], empty_texts))
    rw._dirty = False
    rw.close()

    # 52g. Engrave / Outline / Cut only: hidden by default (Settings → View), below the scrolling panel
    # with Start, greyed out without a ticked layer of that kind that has something on it
    kw_ = make_window(grid_mm="0")
    hidden = not kw_.kind_row.isVisibleTo(kw_)
    kw_.values["kind_buttons"] = "1"
    kw_.kind_row.setVisible(True)
    kw_._preview_drawn("rectangle", QPointF(20, 20), QPointF(60, 60), False)       # a cut shape
    app.processEvents()
    states = {k: a.isEnabled() for k, a in kw_.act_run_kind.items()}
    pinned_k = not kw_.panel_scroll.isAncestorOf(kw_.kind_row)
    cut_layer = [l for l in kw_.layers if l.kind == "cut"][0]
    cut_layer.enabled = False
    kw_._update_bed_check()
    unticked = not kw_.act_run_kind["cut"].isEnabled()
    check("Engrave / Outline / Cut only: hidden by default, pinned with Start, greyed out without data",
          hidden and states == {"raster": False, "engrave": False, "cut": True} and pinned_k and unticked,
          "(%s)" % [hidden, states, pinned_k, unticked])
    kw_._dirty = False
    kw_.close()

    # 52h. the built program (AppImage) gives the programs it starts (Inkscape, a browser) the system's
    # library path, not its own: Inkscape loaded the AppImage's older C++ library and failed
    import os as _os
    from kerfly.gui import app as _kapp
    _saved = (getattr(sys, "frozen", None), sys.platform, dict(_os.environ))
    try:
        sys.frozen = True
        sys.platform = "linux"
        _os.environ["LD_LIBRARY_PATH"], _os.environ["LD_LIBRARY_PATH_ORIG"] = "/tmp/_MEIxyz", "/opt/lib"
        _kapp.restore_system_libraries()
        restored = _os.environ.get("LD_LIBRARY_PATH") == "/opt/lib"
        del _os.environ["LD_LIBRARY_PATH_ORIG"]
        _os.environ["LD_LIBRARY_PATH"] = "/tmp/_MEIxyz"
        _kapp.restore_system_libraries()
        removed = "LD_LIBRARY_PATH" not in _os.environ
    finally:
        if _saved[0] is None:
            del sys.frozen
        sys.platform = _saved[1]
        _os.environ.clear()
        _os.environ.update(_saved[2])
    check("built program: programs it starts get the system's library path", restored and removed,
          "(%s)" % [restored, removed])

    # 52i. designs of the same name from different folders (one folder per customer): the element list
    # shows the folder, the bottom bar the path of the design under the mouse pointer; a saved and
    # reopened project and the parts of a split file keep where they came from
    import shutil as _sh
    from PySide6.QtTest import QTest as _QT2
    tmp_dirs = tempfile.mkdtemp()
    paths = []
    for folder in ("Pg4 Zosi", "Pg4 OSKAR"):
        _os_dir = os.path.join(tmp_dirs, folder)
        os.makedirs(_os_dir)
        paths.append(os.path.join(_os_dir, "PG-4-wnetrze-A.dxf"))
        _sh.copy(os.path.join(FIX, "shapes.dxf"), paths[-1])
    pw2 = make_window(grid_mm="0")
    pw2.resize(1200, 800)
    pw2.show()
    app.processEvents()
    pw2.load_design(paths[0])
    pw2.load_design(paths[1], add=True)
    app.processEvents()
    rows = [pw2.element_list.item(i).text() for i in range(pw2.element_list.count())]
    listed = rows[0].startswith("Pg4 Zosi") and rows[1].startswith("Pg4 OSKAR")
    second = pw2.elements[1]
    x0, x1, y0, y1 = second.bounds
    _QT2.mouseMove(pw2.preview.viewport(), pw2.preview.mapFromScene(QPointF((x0 + x1) / 2 * 25.4, -(y0 + y1) / 2 * 25.4)))
    app.processEvents()
    hovered = "Pg4 OSKAR" in pw2.path_label.text() and pw2.path_label.toolTip() == paths[1]
    proj2 = os.path.join(tmp_dirs, "both.kerfly")
    from kerfly.core import project as _project2
    _project2.save_project(proj2, pw2.elements, pw2.layers)
    pw2._dirty = False
    pw2.open_project(proj2)
    app.processEvents()
    reopened = [pw2._element_path(e) for e in pw2.elements] == paths
    check("same names from different folders: the list shows the folder, the bottom bar the path under the "
          "pointer, kept in projects", listed and hovered and reopened, "(%s)" % [listed, hovered, reopened, rows])
    pw2._dirty = False
    pw2.close()

    # 52j. a material made from the current layers keeps the other layers too (a second cut layer,
    # slower), and applying it sets them by name or adds them; the basic layers as before
    from kerfly.gui.materials_dialog import MaterialsDialog as _MD
    from kerfly.core.layers import Layer as _Layer3
    mw1 = make_window(grid_mm="0")
    slow = _Layer3("cut", name="Cut 2", color="#2e7d32", speed=4.0, passes=2, power=0.7, kerf=0.15)
    mw1.layers.append(slow)
    captured = {}
    _orig_md_exec = _MD.exec

    def _new_from_current(dlg):
        dlg._from_current()
        captured["m"] = dlg.materials[-1]
        return False                                  # not saved: the library file stays as it is
    _MD.exec = _new_from_current
    try:
        mw1.edit_materials()
    finally:
        _MD.exec = _orig_md_exec
    mat = captured.get("m")
    kept = mat is not None and [(x.name, x.speed, x.passes, x.kerf) for x in mat.extra_layers] == [("Cut 2", 4.0, 2, 0.15)]
    mw1._dirty = False
    mw1.close()
    mw2 = make_window(grid_mm="0")
    mw2.materials = [mat]
    n_before = len(mw2.layers)
    mw2.apply_material(0)
    added = [l for l in mw2.layers if l.kind == "cut" and l.name == "Cut 2"]
    applied = len(mw2.layers) == n_before + 1 and len(added) == 1 and added[0].passes == 2 \
        and abs(added[0].kerf - 0.15) < 1e-9
    check("material from the current layers keeps the other layers; applying it adds or sets them by name",
          kept and applied, "(%s)" % [kept, applied])
    mw2._dirty = False
    mw2.close()

    # 53. Linux: connecting fails for want of permission -> Kerfly offers the USB rule (pkexec); with
    # a rule already there, Laser → Allow USB access only says to plug the laser in again
    from kerfly.core import udev as _udev
    from kerfly.core.laser import LaserError as _LaserError
    u = make_window(grid_mm="0")
    saved = (_udev.installed, _udev.install, _udev.applies, QMessageBox.question, QMessageBox.information,
             u.laser.connect)
    asked, informed, installs = [], [], []
    try:
        _udev.applies = lambda: True
        _udev.installed = lambda dirs=None: False
        _udev.install = lambda: installs.append(1) or (True, "")
        QMessageBox.question = staticmethod(lambda *a, **k: asked.append(a[2]) or QMessageBox.Yes)
        QMessageBox.information = staticmethod(lambda *a, **k: informed.append(a[2]))

        def refuse(init_home=True, **_kw):
            raise _LaserError("USB error: [Errno 13] Access denied (insufficient permissions)")
        u.laser.connect = refuse
        u.connect_laser()
        for _i in range(5):
            app.processEvents()
        offered = bool(installs) and any("was found" in q for q in asked) and any("Unplug" in t for t in informed)
        _udev.installed = lambda dirs=None: True
        installs.clear()
        u.allow_usb_access()
        already = not installs and any("already installed" in t for t in informed)
    finally:
        (_udev.installed, _udev.install, _udev.applies, QMessageBox.question, QMessageBox.information,
         u.laser.connect) = saved
    check("Linux USB access: refused connection offers the rule (pkexec), an existing rule only a hint",
          offered and already, "(%s, %s, %s)" % (offered, already, asked[:1]))
    u._dirty = False
    u.close()

    # 54. generators: each one's dialog makes a design that goes on the bed as one group and one
    # undo step (with its layers), the window tells the truth; the dialog remembers its numbers
    from kerfly.gui.generators import GENERATORS as _GENS, GeneratorDialog as _GD
    from kerfly.gui import truth as _truth2
    gw = make_window(grid_mm="0")
    made = {}
    for key, *_rest in _GENS:
        dlg = _GD(gw, key, remember=False)
        before = _truth2.state(gw)
        els = gw.insert_generated(dlg.result_design())
        grouped = len(els) == 1 or len({e.group.split("/")[0] for e in els}) == 1 and bool(els[0].group)
        ok = bool(els) and grouped and not _truth2.check_window(gw)
        gw.undo()
        ok = ok and _truth2.difference(before, _truth2.state(gw)) == ""
        made[key] = ok
        dlg.deleteLater()
    from PySide6.QtTest import QTest as _QTest
    d0 = _GD(gw, "gear", remember=False)
    d0.show()
    app.processEvents()
    _QTest.keyClick(d0.widgets["teeth"].lineEdit(), Qt.Key_Return)      # Enter: the preview, not Insert
    app.processEvents()
    enter_stays = d0.isVisible() and d0.result() == 0
    d0.reject()
    gw.remember_geometry = True
    d1 = _GD(gw, "gear", remember=True)
    d1.widgets["teeth"].setValue(33)
    d1.accept()
    remembered = _GD(gw, "gear", remember=True).widgets["teeth"].value() == 33
    check("generators: every one inserts a group as one undo step, window tells the truth; numbers remembered",
          all(made.values()) and remembered and enter_stays,
          "(%s, remembered %s, Enter keeps the dialog %s)" % (made, remembered, enter_stays))

    # 54b. the generators' 3D tab: only for boxes (finger box, rounded box), drawn (wood on the background),
    # Pulled apart moves the parts, the lid slider only with a sliding lid and moves it out
    shown3d = {}
    for key in ("finger_box", "hinge_box", "gear"):
        d3 = _GD(gw, key, remember=False)
        d3.resize(1200, 700)
        d3.show()
        app.processEvents()
        shown3d[key] = d3.preview_tabs.isTabVisible(1) and d3.preview_tabs.tabBar().isVisible()
        if key == "finger_box":
            d3.widgets["sliding"].setChecked(True)
            d3._preview()                                   # (the preview waits 150 ms after a change)
            app.processEvents()
            d3.preview_tabs.setCurrentIndex(1)
            app.processEvents()
            img = d3.box3d.grab().toImage()
            wood = sum(1 for y in range(0, img.height(), 6) for x in range(0, img.width(), 6)
                       if img.pixelColor(x, y).red() - img.pixelColor(x, y).blue() > 40)
            slider = d3.lid_slider.isVisible()
            d3.lid_slider.setValue(100)
            lid_out = d3.box3d.lid_out
            d3.exploded.setChecked(True)
            apart = d3.box3d.exploded
            d3.widgets["sliding"].setChecked(False)
            d3._preview()
            app.processEvents()
            slider_gone = not d3.lid_slider.isVisible()
        d3.reject()
        d3.deleteLater()
    # the parts are drawn as solids in the right order: from each side the part on that side is seen in the
    # middle, through an open top the bottom; and turned all round, the order never runs in a loop
    from kerfly.core import generators as _gen3
    from kerfly.gui.box3d import Box3DView as _B3
    v3 = _B3()
    v3.resize(400, 300)
    sides3 = {"top": (0, 89), "bottom": (0, -89), "front": (0, 0), "back": (180, 0), "left": (90, 0),
              "right": (-90, 0)}
    expect3 = {
        "box": (_gen3.finger_box(100, 80, 50, 3, 10, 0, True), dict(top="Lid", bottom="Bottom", front="Front",
                                                                   back="Back", left="Left", right="Right")),
        "open box": (_gen3.finger_box(100, 80, 50, 3, 10, 0, False), dict(top="Bottom", front="Front")),
        "rounded box": (_gen3.hinge_box(120, 90, 50, 20, 3, 10, 0, True),
                        dict(top="Lid", bottom="Bottom", front="Wall", left="Wall")),
    }
    seen3 = {}
    for name3, (g3, want) in expect3.items():
        v3.set_assembly(g3.assembly)
        for side, part in want.items():
            v3.yaw, v3.pitch = sides3[side]
            got = v3.part_at(200, 150)
            if got != part:
                seen3["%s from the %s" % (name3, side)] = got
    # what is drawn is what a ray from each point of the view hits first (the parts' faces, cast one by one):
    # boxes with fingers, rails, a sliding lid half out, crossing dividers, slots of a bent wall, pulled apart
    def ray_part(view3, sx, sy, w3, h3):
        polys3, _tree, _edges, mid3, radius3 = view3.model()
        k3 = 0.47 * min(w3, h3) / radius3 * view3.zoom
        x, z = (sx - w3 / 2.0) / k3, (h3 / 2.0 - sy) / k3
        best, part = None, -1
        for poly in polys3:
            nv = view3.turn(poly.normal)
            if abs(nv[1]) < 1e-6:
                continue
            flat = [[view3.turn((q[0] - mid3[0], q[1] - mid3[1], q[2] - mid3[2])) for q in lp] for lp in poly.loops]
            xs3 = [q[0] for q in flat[0]]
            zs3 = [q[2] for q in flat[0]]
            if not (min(xs3) <= x <= max(xs3) and min(zs3) <= z <= max(zs3)):
                continue
            inside = False
            for lp in flat:
                for (x1, _y1, z1), (x2, _y2, z2) in zip(lp, lp[1:] + lp[:1]):
                    if (z1 > z) != (z2 > z) and x < x1 + (z - z1) * (x2 - x1) / (z2 - z1):
                        inside = not inside
            if not inside:
                continue
            p0 = flat[0][0]
            depth = p0[1] - (nv[0] * (x - p0[0]) + nv[2] * (z - p0[2])) / nv[1]
            if best is None or depth < best:
                best, part = depth, poly.part
        return part
    wrong_rays = []
    for g3, ex3, lid3 in ((_gen3.finger_box(150, 100, 50, 3, 10, 0.15, True, sliding=True, dividers_across=1,
                                            dividers_along=1), 0, 40),
                          (_gen3.finger_box(120, 90, 50, 3, 10, 0, False, dividers_across=1, dividers_along=2), 25, 0),
                          (_gen3.hinge_box(120, 90, 50, 20, 3, 10, 0.15, True), 0, 0)):
        v3.set_assembly(g3.assembly)
        v3.set_exploded(ex3)
        v3.set_lid_out(lid3)
        for yaw, pitch in ((-20, 30), (140, 55), (-110, -35)):
            v3.yaw, v3.pitch = yaw, pitch
            img3 = QImage(400, 300, QImage.Format_RGB32)
            img3.fill(QColor(0, 0, 0))
            p3 = QPainter(img3)
            v3.render(p3, 400, 300, ids=True)
            p3.end()
            for sy in range(10, 300, 14):
                for sx in range(10, 400, 14):
                    want = ray_part(v3, sx + 0.5, sy + 0.5, 400, 300)
                    near = {img3.pixelColor(sx + dx, sy + dy).red() - 1 for dx in (-1, 0, 1) for dy in (-1, 0, 1)}
                    if want not in near:
                        wrong_rays.append((g3.name, yaw, pitch, sx, sy, want, sorted(near)))
    check("box 3D: solids drawn in the right order (each side seen from its side; what is drawn is what a ray "
          "hits first, from 9 views of 3 boxes)",
          not seen3 and not wrong_rays, "(wrong %s, rays %d %s)" % (seen3, len(wrong_rays), wrong_rays[:4]))
    check("generators: 3D tab only for boxes, the box drawn, pulled apart, the sliding lid slides out",
          shown3d == {"finger_box": True, "hinge_box": True, "gear": False} and wood > 200 and slider
          and lid_out > 50 and apart > 0 and slider_gone,
          "(%s, wood %d, slider %s, lid out %.1f, apart %.1f, slider hidden %s)"
          % (shown3d, wood, slider, lid_out, apart, slider_gone))
    gw._dirty = False
    gw.close()

    # 54c. groups in groups: a box on several sheets is one group with a group for each sheet, and in it a group
    # for each part made of several shapes (an outline and its slots); rows that open in the element list; a
    # click on the bed takes the whole box, a sheet's row that sheet alone, a part's row that part, a shape's
    # row that shape; a sheet's tick takes it out of the job; Ungroup takes one level away (the sheets stay
    # groups), Group puts them together again; copies and saved projects keep the groups and their names
    from kerfly.core import generators as _gen4
    from kerfly.core.groups import paths as _gpaths, within as _within
    gw4 = make_window(grid_mm="0")
    box4 = _gen4.finger_box(250, 180, 60, 3, 10, 0.0, True, sliding=True, bed=(300.0, 200.0),
                            sheet_name="Sheet %d", names={"left": "Left side"})
    els4 = gw4.insert_generated(box4)
    lst4 = gw4.element_list
    groups4 = [e.group for e in els4]

    def sheet_of(e):
        return "/".join(e.group.split("/")[:2])

    def name_of(path):
        return gw4.group_names.get(path.rsplit("/", 1)[-1], "")
    top4 = {e.group.split("/")[0] for e in els4}
    sheets4 = sorted({sheet_of(e) for e in els4})
    n4 = box4.sheets
    tree4 = len(top4) == 1 and n4 >= 3 and len(sheets4) == n4 and \
        lst4.topLevelItemCount() == 1 and lst4.topLevelItem(0).childCount() == n4 and \
        lst4.topLevelItem(0).text().startswith("Finger-joint box") and \
        [lst4.topLevelItem(0).child(i).text().split(" (")[0] for i in range(n4)] == \
        ["Sheet %d" % (i + 1) for i in range(n4)]
    # the left side (an outline with slots): a group of its own, named after it, with all its shapes
    left4 = [e for e in els4 if e.name == "Left side"]
    parts4 = len(left4) > 1 and len({e.group for e in left4}) == 1 and len(_gpaths(left4[0].group)) == 3 and \
        name_of(left4[0].group) == "Left side" and \
        all(len(_gpaths(e.group)) == 2 for e in els4 if sum(x.group == e.group for x in els4) == 1 and
            e.name.endswith("rail"))                         # a part of one shape: no group of its own
    # every sheet on the cut layer (one colour), sheet 1 in the job, the others ticked when their turn comes
    on_layer = all(not e.layers for e in els4) and not [l for l in gw4.layers if l.name.startswith("Sheet ")]
    one_colour = all(e.visible == (name_of(sheet_of(e)) == "Sheet 1") for e in els4)
    gw4.preview.select_element(els4[-1])                     # a click on the bed: the whole box
    whole = len(gw4._selection()) == len(els4)
    sheet2 = next(p for p in sheets4 if name_of(p) == "Sheet 2")
    lst4.clearSelection()
    lst4.group_item(sheet2).setSelected(True)                 # the row of sheet 2: that sheet alone
    app.processEvents()
    alone = {id(e) for e in gw4._selection()} == {id(e) for e in els4 if _within(e.group, sheet2)}
    lst4.clearSelection()
    lst4.group_item(left4[0].group).setSelected(True)        # a part's row: that part
    part_alone = {id(e) for e in gw4._selection()} == {id(e) for e in left4}
    lst4.clearSelection()
    lst4.item(gw4.elements.index(left4[0])).setSelected(True)  # a shape's row: that shape
    shape_alone = gw4._selection() == [left4[0]]
    sheet3 = next(p for p in sheets4 if name_of(p) == "Sheet 3")
    sheet1 = next(p for p in sheets4 if name_of(p) == "Sheet 1")
    lst4.group_item(sheet1).setCheckState(Qt.Unchecked)       # sheet 1 cut: out of the job,
    app.processEvents()                                       # (the list is filled again after the click)
    lst4.group_item(sheet3).setCheckState(Qt.Checked)         # sheet 3 in
    app.processEvents()
    from kerfly.gui.simulation import simulation_steps as _sim_steps
    out3 = all(e.visible == _within(e.group, sheet3) for e in els4) and \
        lst4.topLevelItem(0).checkState() == Qt.PartiallyChecked and \
        lst4.group_item(sheet1).checkState() == Qt.Unchecked and bool(_sim_steps(gw4))   # sheet 3 simulated
    gw4.undo()
    gw4.undo()
    gw4.preview.scope = ""
    gw4.preview.select_element(els4[0])
    gw4.ungroup_selected()                                    # one level: the sheets stay groups
    after_ungroup = all(len(_gpaths(e.group)) == len(_gpaths(g)) - 1 for e, g in zip(els4, groups4)) and \
        len({e.group.split("/")[0] for e in els4}) == n4 and lst4.topLevelItemCount() == n4
    gw4.preview.select_element(list(els4))
    gw4.group_selected()                                      # and together again: the sheets in one group
    regrouped = len({e.group.split("/")[0] for e in els4}) == 1 and \
        all(len(_gpaths(e.group)) == len(_gpaths(g)) for e, g in zip(els4, groups4))
    gw4.undo()
    gw4.undo()                                                # back to the box as inserted
    back = [e.group for e in els4] == groups4
    gw4.preview.select_element(els4[0])
    gw4.copy_selected()
    gw4.paste()
    copies4 = gw4.elements[len(els4):]
    copied = len(copies4) == len(els4) and not ({e.group for e in copies4} & set(groups4)) and \
        [name_of(sheet_of(e)) for e in copies4] == [name_of(sheet_of(e)) for e in els4]
    path4 = tempfile.mktemp(suffix=".kerfly")
    gw4._write_project(path4)
    gw5 = make_window(grid_mm="0")
    gw5.open_project(path4)
    os.remove(path4)
    kept = [e.group for e in gw5.elements] == [e.group for e in gw4.elements] and \
        gw5.element_list.topLevelItemCount() == 2 and \
        gw5.element_list.topLevelItem(0).text() == lst4.topLevelItem(0).text() and \
        not _truth.check_window(gw5) and not _truth.check_window(gw4)
    check("groups in groups: a box on several sheets (all on the cut layer, sheet 1 in the job), a group for "
          "each sheet and each part of several shapes; "
          "bed click takes the box, a sheet's / part's / shape's row that alone; sheet ticks; Ungroup one "
          "level, Group again; copied and saved with their names",
          tree4 and parts4 and on_layer and one_colour and whole and alone and part_alone and shape_alone and out3 and
          after_ungroup and regrouped and back and copied and kept,
          "(%s)" % [tree4, parts4, on_layer, one_colour, whole, alone, part_alone, shape_alone, out3, after_ungroup,
                    regrouped, back, copied, kept])
    for win in (gw4, gw5):
        win._dirty = False
        win.close()

    # 55. stamp: the picture is inverted (background burnt, text raised) and mirrored, black and white,
    # at the chosen size; it is kept as a file (projects can save it) and the outline is cut
    from kerfly.gui import stamp as _stamp
    base = dict(preset="custom", width=40.0, height=15.0, text="AB", font="DejaVu Sans", bold=True, text_size=0.0,
                picture="", place="left", frame=0.0, corner=0.0, margin=1.0, outline=True)
    plain = _stamp.render(dict(base, invert=False, mirror=False))
    stamp_img = _stamp.render(dict(base, invert=True, mirror=True))

    def dark(img):
        return sum(1 for y in range(0, img.height(), 4) for x in range(0, img.width(), 4)
                   if img.pixelColor(x, y).lightness() < 128)
    total = len(range(0, plain.height(), 4)) * len(range(0, plain.width(), 4))
    inverted = dark(plain) < total * 0.5 < dark(stamp_img)
    mirrored = all((plain.pixelColor(x, y).lightness() < 128) ==
                   (stamp_img.pixelColor(plain.width() - 1 - x, y).lightness() >= 128)
                   for y in range(0, plain.height(), 25) for x in range(0, plain.width(), 25))
    two_tone = all(plain.pixelColor(x, y).lightness() in (0, 255)
                   for y in range(0, plain.height(), 9) for x in range(0, plain.width(), 9))
    size_ok = abs(plain.width() / 1000 * 25.4 - 40) < 0.1 and abs(plain.height() / 1000 * 25.4 - 15) < 0.1
    sw = make_window(grid_mm="0")
    els = sw.insert_generated(_stamp.make(dict(base, invert=True, mirror=True), sw))
    kept = els and os.path.isfile(els[0].source_file) and els[0].design.raster.image is not None \
        and els[1].shape is not None and els[1].shape.operation == "cut"
    check("stamp: inverted, mirrored, black and white, its size, kept as a file, outline cut",
          inverted and mirrored and two_tone and size_ok and bool(kept),
          "(%s)" % ([inverted, mirrored, two_tone, size_ok, bool(kept)],))
    sw._dirty = False
    sw.close()

    # 55b. round stamp: text around the top (letters standing on the circle) and the bottom, the
    # middle text, the ready-made diameters, inverted and mirrored, a round outline cut
    rbase = {f[0]: f[3] for f in _stamp.ROUND_FIELDS}
    rbase.update(preset="40", top_text="TOP TEXT HERE", bottom_text="BOTTOM", text="MID", invert=False,
                 mirror=False, picture="")
    r_plain = _stamp.render_round(rbase)

    def region(img, y0, y1, x0=0.3, x1=0.7):
        return sum(1 for y in range(int(img.height() * y0), int(img.height() * y1), 4)
                   for x in range(int(img.width() * x0), int(img.width() * x1), 4)
                   if img.pixelColor(x, y).lightness() < 128)
    empty = _stamp.render_round(dict(rbase, top_text="", bottom_text="", text=""))
    texts_ok = (region(r_plain, 0.04, 0.2) > region(empty, 0.04, 0.2) + 50
                and region(r_plain, 0.8, 0.96) > region(empty, 0.8, 0.96) + 50
                and region(r_plain, 0.4, 0.6) > region(empty, 0.4, 0.6) + 50)
    r_size_ok = abs(r_plain.width() / 1000 * 25.4 - 40) < 0.1 and r_plain.width() == r_plain.height()
    small = _stamp.render_round(dict(rbase, preset="custom", diameter=25.0))
    r_burn = _stamp.render_round(dict(rbase, invert=True, mirror=True))
    r_mirrored = all((r_plain.pixelColor(x, y).lightness() < 128) ==
                     (r_burn.pixelColor(r_plain.width() - 1 - x, y).lightness() >= 128)
                     for y in range(0, r_plain.height(), 31) for x in range(0, r_plain.width(), 31))
    sw = make_window(grid_mm="0")
    els = sw.insert_generated(_stamp.make_round(dict(rbase, invert=True, mirror=True), sw))
    r_cut = (len(els) == 2 and els[1].shape.kind == "ellipse" and els[1].shape.operation == "cut"
             and abs(els[1].shape.width - 40) < 1e-6)
    check("round stamp: texts at the top, bottom and middle, its diameter, inverted and mirrored, round cut",
          texts_ok and r_size_ok and abs(small.width() / 1000 * 25.4 - 25) < 0.1 and r_mirrored and r_cut,
          "(%s)" % ([texts_ok, r_size_ok, small.width(), r_mirrored, r_cut],))
    sw._dirty = False
    sw.close()

    # 55c. the stamp picture is clean: the frame unbroken along its whole length, nothing between the
    # frame and the text (on Windows the frame came out dashed and streaks ran across the letters);
    # tests/test_stamp.py runs the same on Windows' own platform in CI
    # Windows offscreen has no fonts (bold looks like regular, the text tiny): there CI checks the stamp
    # with tests/test_stamp.py on the real Windows platform instead
    fonts_real = not (sys.platform == "win32" and QApplication.platformName() == "offscreen")
    from test_stamp import clean_report as _stamp_clean
    for _name, _ok, _detail in (_stamp_clean() if fonts_real else []):
        check(_name + " (font %s)" % _stamp.default_font(), _ok, _detail)

    # 55d. the stamp's text editor (WYSIWYG): a line selected, B makes it bold, A+ bigger; the stamp
    # follows (a user asked for the name and the address in different sizes and weights)
    from PySide6.QtGui import QTextCursor as _QTC
    from kerfly.gui.generators import GeneratorDialog as _GD, RichTextField as _RTF
    sd = _GD(make_window(), "stamp", remember=False)
    rich = next(wd for wd in sd.widgets.values() if isinstance(wd, _RTF))

    def _ink(values):
        im = _stamp.render(dict(values, invert=False, mirror=False))
        return sum(1 for y in range(0, im.height(), 3) for x in range(0, im.width(), 3)
                   if im.pixelColor(x, y).lightness() < 128)
    plain_ink = _ink(sd.values())
    cur = rich.edit.textCursor()
    cur.movePosition(_QTC.Start)
    cur.movePosition(_QTC.NextBlock)
    cur.select(_QTC.BlockUnderCursor)
    rich.edit.setTextCursor(cur)
    rich.buttons["bold"].click()
    bold_html = sd.values()["text_html"]
    bold_ink = _ink(sd.values())
    cur = rich.edit.textCursor()
    second_bold = cur.charFormat().fontWeight() >= 700
    cur.movePosition(_QTC.Start)
    cur.select(_QTC.BlockUnderCursor)
    rich.edit.setTextCursor(cur)
    before_size = rich.edit.textCursor().charFormat().fontPointSize()
    rich.buttons["bigger"].click()
    after_size = rich.edit.textCursor().charFormat().fontPointSize()
    check("stamp text editor: B makes a line bold, A+ bigger, the stamp follows",
          second_bold and (bold_ink > plain_ink or not fonts_real) and after_size > before_size > 0
          and "700" in bold_html,
          "(%s)" % [second_bold, plain_ink, bold_ink, before_size, after_size])
    sd.close()

    # 56. a path shape put on the bed starts at (0, 0) of its outline, so the node editor draws its
    # nodes on the shape (a curve whose handles stuck out was drawn shifted)
    from kerfly.core import curves as _cv
    pw = make_window(grid_mm="0")
    heart = _Spec(kind="path", operation="cut", subpaths=[{"closed": True, "nodes": [
        _cv.node(45, 15, (30, -5), (60, -5)), _cv.node(85, 25, (90, 0), (80, 50)),
        _cv.node(45, 75, (60, 60), (30, 60)), _cv.node(5, 25, (10, 50), (0, 0))]}])
    pw._add_drawn_element(heart, "pen", 40, 30)
    x0, _x1, y0, _y1 = _cv.bounds(pw.elements[-1].shape.subpaths)
    check("path shapes start at (0, 0) of their outline (node editor on the shape)",
          abs(x0) < 1e-6 and abs(y0) < 1e-6, "(%.3f, %.3f)" % (x0, y0))
    pw._dirty = False
    pw.close()

    # 50. the element list shows a single element too (it was hidden until there were two)
    w9 = make_window(grid_mm="0")
    w9._add_drawn_element(_Spec(kind="rectangle", width=20, height=20), "rectangle", 10, 10)
    shown = not w9.element_list_box.isHidden() and w9.element_list.count() == 1
    w9.new_project()
    hidden_empty = w9.element_list_box.isHidden()
    check("element list: shown with one element, hidden when the bed is empty", shown and hidden_empty)
    w9._dirty = False
    w9.close()

    # 49. File → New project: asks about unsaved changes, then an empty bed, default layers, no undo
    w8 = make_window(grid_mm="0")
    w8._add_drawn_element(_Spec(kind="rectangle", width=20, height=20), "rectangle", 10, 10)
    w8.add_layer("cut")                                   # an extra layer, gone in the new project
    asked = []
    _orig_q = QMessageBox.question
    QMessageBox.question = staticmethod(lambda *a, **k: asked.append(1) or QMessageBox.Discard)
    try:
        w8.new_project()
    finally:
        QMessageBox.question = _orig_q
    kinds = sorted(l.kind for l in w8.layers)
    fresh = not w8.elements and not w8._undo and not w8.project_file and not w8._dirty \
        and kinds == sorted(set(kinds)) and bool(asked)
    on_bar = any(getattr(t, "defaultAction", lambda: None)() is w8.act_new for t in w8.findChildren(QToolButton))
    check("new project: asks first, empty bed, default layers, nothing to undo, toolbar button",
          fresh and on_bar, "(%s, %d layers, asked %s)" % (fresh, len(w8.layers), bool(asked)))
    w8._dirty = False
    w8.close()

    # 43. no keyboard shortcut is used twice (Qt then runs neither action)
    from PySide6.QtGui import QAction as _QAction
    seen, twice = {}, []
    for a in w.findChildren(_QAction):
        for sc in a.shortcuts():
            key = sc.toString()
            if key in seen and seen[key] is not a:
                twice.append("%s: %s / %s" % (key, seen[key].text(), a.text()))
            seen.setdefault(key, a)
    check("no keyboard shortcut is used twice", not twice, "(%s)" % "; ".join(twice))

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

    def head_on_design(win):
        return (round(win.head[0] - win.origin[0], 3), round(win.head[1] - win.origin[1], 3))
    # after a corner button the arrows move the design with the head, the head keeping its place on it
    # (it used to jump back to the origin corner and threw the design off the bed)
    place, x_before = head_on_design(w2), w2.elements[0].x
    w2.jog(1, 0)
    kept = head_on_design(w2) == place and abs(w2.elements[0].x - x_before - 10 / 25.4) < 0.002
    w2.home()
    homed = w2.origin == (0.0, 0.0) == w2.head
    w2.jog(-1, 0)                                         # already at the left edge: stays on the bed
    on_bed = w2.origin == (0.0, 0.0)
    w2.act_follow_head.trigger()
    saved = w2.values["follow_head"] == "0"
    # the same with home in the upper right corner (Marek's report): head on the upper left corner of the design,
    # left arrow: the design goes left with the head; far left: the design stops at the bed's edge
    w3 = make_window(follow_head="0", jog_step="10", HomeUR="1", grid_mm="0")
    w3._preview_drawn("rectangle", QPointF(100, 40), QPointF(160, 80), False)
    w3.act_follow_head.trigger()
    w3.move_to_corner("UL")
    place3, x3 = head_on_design(w3), w3.elements[0].x
    w3.jog(-1, 0)
    ur_kept = place3[0] > 1 and head_on_design(w3) == place3 and abs(w3.elements[0].x - x3 - 10 / 25.4) < 0.002
    for _i in range(60):
        w3.jog(-1, 0)
    bw3, _bh3 = config.bed_size_inches(w3.values)
    ur_on_bed = head_on_design(w3) == place3 and w3.head[0] <= bw3 + 1e-6 and \
        not w3._off_bed_elements()
    check("design follows the head: arrows, corners, Home, undo, setting; after a corner button the head keeps its "
          "place on the design (also with home in the upper right), the design stays on the bed",
          stays and at_head and follows and corner_only and kept and homed and on_bed and saved and ur_kept
          and ur_on_bed,
          "(%s)" % ([stays, at_head, follows, corner_only, kept, homed, on_bed, saved, ur_kept, ur_on_bed],))
    w2._dirty = False
    w2.close()
    w3._dirty = False
    w3.close()
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
