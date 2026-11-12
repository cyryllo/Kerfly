#!/usr/bin/env python3
"""
Release test: a whole working session in the real window, with real mouse
clicks and key presses, the way a user works (ROADMAP: release tests, step 2).

After every step the window must show what its data holds
(kerfly.gui.truth.check_window), and every step that changes the project is
undone and redone with the toolbar buttons: undo must bring back exactly the
state before the step, redo the state after it.

Run it on a Full HD screen (1920 x 1080, the window fills it):

    QT_QPA_PLATFORM=xcb xvfb-run -a -s "-screen 0 1920x1080x24" .venv/bin/python tests/test_release.py

Dialogs that are Kerfly's own (messages, questions, settings) are answered
by clicking their buttons; the system's file and colour pickers and the web
browser are replaced (they are windows of the operating system). The laser
is a stand-in that records what it gets (tests/fakes.py).

Copyright (C) 2026 Kerfly contributors
Licensed under the GNU General Public License v3 or later. See LICENSE.
"""
import faulthandler
import os
import sys
import tempfile
import time
import traceback

os.environ.setdefault("QT_QPA_PLATFORM", "xcb")
faulthandler.enable()                      # a crash inside Qt still shows where the session was
sys.stdout.reconfigure(line_buffering=True)
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp(prefix="kerfly_release_cfg_")   # never the user's settings
os.environ["APPDATA"] = os.environ["XDG_CONFIG_HOME"]
os.environ["HOME"] = tempfile.mkdtemp(prefix="kerfly_release_home_")
TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(TESTS_DIR)
sys.path.insert(0, ROOT_DIR)
sys.path.insert(0, TESTS_DIR)

from PySide6.QtCore import QEvent, QPoint, QPointF, Qt, QTimer  # noqa: E402
from PySide6.QtGui import QAction, QKeySequence, QMouseEvent  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import (QAbstractButton, QApplication, QColorDialog, QComboBox, QDialog,  # noqa: E402
                               QDoubleSpinBox, QFileDialog, QFontComboBox, QMenu, QMessageBox,
                               QPlainTextEdit, QSpinBox, QToolButton)

from kerfly.core import config  # noqa: E402
from kerfly.gui import truth  # noqa: E402
from kerfly.gui.main_window import MainWindow  # noqa: E402
from fakes import FakeK40  # noqa: E402

FIX = os.path.join(TESTS_DIR, "fixtures")
MM = 25.4


class Session:
    """The window and a user at it: real input, checks after each step."""

    def __init__(self, app):
        self.app = app
        self.failures = []
        self.steps = 0
        self.dialog_handlers = []          # [(description, handler(dialog))] for the next dialogs
        self.files = []                    # answers of the (replaced) file pickers
        self.colors = []                   # answers of the (replaced) colour picker
        self.opened_urls = []
        self.fake = None
        self.covered_actions = set()
        self.covered_fields = set()        # (shape kind or tool, setting)
        self.covered_widgets = set()
        self.touched = set()               # ids of the widgets used
        self.seen_fields = set()           # options bar settings that were shown
        self.tmp = tempfile.mkdtemp(prefix="kerfly_release_")
        self._patch_system_dialogs()
        values = dict(config.DEFAULT_VALUES)
        values.update(grid_mm="0", init_home="1")
        self.w = MainWindow(values)
        self.w.show()
        self.w.setGeometry(app.primaryScreen().availableGeometry())       # Full HD, the whole screen
        self.w.activateWindow()
        self.settle(20)
        self.view = self.w.preview
        self.vp = self.view.viewport()
        for action in self.w.findChildren(QAction):
            if action.text() and not action.menu():
                action.triggered.connect(lambda _c=False, a=action: self.covered_actions.add(id(a)))
        self._dialog_timer = QTimer()
        self._dialog_timer.setInterval(60)
        self._dialog_timer.timeout.connect(self._answer_dialog)
        self._dialog_timer.start()

    # ------------------------------------------------------------------ plumbing
    def settle(self, n=6, sleep=0.0):
        for _ in range(n):
            self.app.processEvents()
            if sleep:
                time.sleep(sleep)

    def wait(self, condition, timeout=20.0):
        t0 = time.time()
        while not condition() and time.time() - t0 < timeout:
            self.app.processEvents()
            time.sleep(0.01)
        return condition()

    def fail(self, step, text):
        self.failures.append("%s: %s" % (step, text))
        print("FAIL  %s: %s" % (step, text))
        if os.environ.get("GITHUB_ACTIONS") and len(self.failures) <= 10:
            # shown on the run's page without logging in (the log itself needs an account)
            detail = (" ".join(text.split()))[-900:]
            print("::error title=release test::%s: %s" % (step[:120], detail.replace("%", "%25")))

    def _patch_system_dialogs(self):
        s = self

        def answer(kind):
            def pick(*_a, **_k):
                if not s.files:
                    s.fail("dialog", "a %s file picker opened without an answer" % kind)
                    return "", ""
                return s.files.pop(0), ""
            return staticmethod(pick)
        QFileDialog.getOpenFileName = answer("open")
        QFileDialog.getSaveFileName = answer("save")

        def get_color(initial, *_a, **_k):
            from PySide6.QtGui import QColor
            return QColor(s.colors.pop(0)) if s.colors else QColor()
        QColorDialog.getColor = staticmethod(get_color)
        from PySide6.QtGui import QDesktopServices
        QDesktopServices.openUrl = staticmethod(lambda url: s.opened_urls.append(url.toString()) or True)
        from kerfly.core import updates             # GitHub is never asked: a newer release is "out"
        updates.latest_release = lambda current, timeout=6.0: updates.Release(
            "99.0", "https://github.com/cyryllo/Kerfly/releases/tag/v99.0")
        from kerfly.core import udev                # pkexec's password window belongs to the system
        s.udev_installs = []
        udev.installed = lambda dirs=None: False
        udev.install = lambda: s.udev_installs.append(1) or (True, "")
        import nano_library                         # the laser: a stand-in that records what it gets

        def board():
            s.fake = FakeK40()
            return s.fake
        nano_library.K40_CLASS = board

    def expect_dialog(self, description, handler, optional=False):
        """The next dialog that opens during the next step is answered by handler(dialog)
        (it must close it). A dialog that is not optional must open."""
        self.dialog_handlers.append((description, handler, optional))

    def _answer_dialog(self):
        dlg = QApplication.activeModalWidget()
        if dlg is None:
            return
        if not self.dialog_handlers:
            text = dlg.text() if isinstance(dlg, QMessageBox) else dlg.windowTitle()
            self.fail("dialog", "unexpected dialog: %s" % text)
            dlg.reject() if isinstance(dlg, QDialog) else dlg.close()
            return
        description, handler, _optional = self.dialog_handlers.pop(0)
        try:
            handler(dlg)
        except Exception:
            self.fail("dialog", "%s: %s" % (description, traceback.format_exc(limit=3)))
            dlg.close()

    @staticmethod
    def click_dialog_button(dlg, role_or_text):
        """Click a button of a dialog (a QMessageBox standard button, or by its text)."""
        if isinstance(dlg, QMessageBox) and not isinstance(role_or_text, str):
            button = dlg.button(role_or_text)
        else:
            button = next((b for b in dlg.findChildren(QAbstractButton) if b.text().replace("&", "") == role_or_text),
                          None)
        if button is None or not Session.on_screen(button):
            names = [b.text() for b in dlg.findChildren(QAbstractButton)]
            text = dlg.text() if isinstance(dlg, QMessageBox) else dlg.windowTitle()
            raise LookupError("no button %r in the dialog '%s' (buttons %s)" % (role_or_text, text, names))
        QTest.mouseClick(button, Qt.LeftButton)

    # ------------------------------------------------------------------ real input
    def pos(self, x, y):
        """Viewport position of a bed point (scene mm, y down from the bed's top)."""
        return self.view.mapFromScene(QPointF(x, y))

    def _move(self, widget, p, buttons=Qt.LeftButton, mods=Qt.NoModifier):
        ev = QMouseEvent(QEvent.MouseMove, QPointF(p), QPointF(widget.mapToGlobal(p)), Qt.NoButton, buttons, mods)
        QApplication.sendEvent(widget, ev)

    def drag(self, a, b, mods=Qt.NoModifier, steps=12, widget=None, points=None):
        """Press at a, move to b (through points), release: bed points in mm (or widget pixels)."""
        widget = widget or self.vp
        to_px = (lambda p: p) if widget is not self.vp else (lambda p: self.pos(*p))
        path = [to_px(a)] + [to_px(p) for p in (points or [])] + [to_px(b)]
        QTest.mouseMove(widget, path[0])
        QTest.mousePress(widget, Qt.LeftButton, mods, path[0])
        for p0, p1 in zip(path, path[1:]):
            for i in range(1, steps + 1):
                self._move(widget, QPoint(p0.x() + (p1.x() - p0.x()) * i // steps,
                                          p0.y() + (p1.y() - p0.y()) * i // steps), mods=mods)
                self.settle(1)
        QTest.mouseRelease(widget, Qt.LeftButton, mods, path[-1])
        self.settle()

    def click_bed(self, x, y, mods=Qt.NoModifier, double=False):
        p = self.pos(x, y)
        QTest.mouseMove(self.vp, p)
        if double:
            QTest.mouseDClick(self.vp, Qt.LeftButton, mods, p)
        else:
            QTest.mouseClick(self.vp, Qt.LeftButton, mods, p)
        self.settle()

    def key(self, key, mods=Qt.NoModifier, widget=None):
        QTest.keyClick(widget or self.vp, key, mods)
        self.settle()

    @staticmethod
    def on_screen(widget):
        """A widget a user can click: shown, in a window that is on the screen."""
        try:
            return widget.isVisible() and widget.window().windowHandle() is not None
        except RuntimeError:
            return False                             # already deleted

    def click(self, widget):
        if not self.on_screen(widget):
            raise RuntimeError("%s is not on the screen" % (widget.toolTip() or widget.objectName() or widget))
        self.touched.add(id(widget))
        QTest.mouseClick(widget, Qt.LeftButton)
        self.settle()

    def wheel(self, widget, notches=-1):
        """Turn the mouse wheel over a widget (negative: towards the user)."""
        from PySide6.QtCore import QPoint, QPointF
        from PySide6.QtGui import QWheelEvent
        pos = QPointF(widget.rect().center())
        QApplication.sendEvent(widget, QWheelEvent(pos, QPointF(widget.mapToGlobal(pos.toPoint())), QPoint(0, 0),
                                                   QPoint(0, 120 * notches), Qt.NoButton, Qt.NoModifier,
                                                   Qt.NoScrollPhase, False))
        self.settle()

    def type_number(self, spin, value):
        """Click into a number field, select it, type the number, press Enter."""
        self.touched.add(id(spin))
        edit = spin.lineEdit()
        QTest.mouseClick(edit, Qt.LeftButton)
        QTest.keyClick(edit, Qt.Key_A, Qt.ControlModifier)
        QTest.keyClicks(edit, spin.textFromValue(value))
        QTest.keyClick(edit, Qt.Key_Return)
        self.settle()

    @staticmethod
    def type_chars(widget, text):
        """Key presses for a text, also letters like ą ę ł ó ś ż (QTest types only ASCII)."""
        from PySide6.QtGui import QKeyEvent
        for ch in text:
            if ord(ch) < 128:
                QTest.keyClicks(widget, ch)
            else:
                for kind in (QEvent.KeyPress, QEvent.KeyRelease):
                    QApplication.sendEvent(widget, QKeyEvent(kind, 0, Qt.NoModifier, ch))

    def type_text(self, edit, text):
        self.touched.add(id(edit))
        QTest.mouseClick(edit.viewport() if isinstance(edit, QPlainTextEdit) else edit, Qt.LeftButton)
        QTest.keyClick(edit, Qt.Key_A, Qt.ControlModifier)
        self.type_chars(edit, text)
        bar = self.w.tool_options
        self.wait(lambda: not bar._text_timer.isActive(), 3.0)     # the text is applied when typing pauses
        self.settle()

    def pick(self, combo, data=None, index=None):
        """Open a drop-down list with a click and click one of its entries."""
        self.touched.add(id(combo))
        at = combo.rect().center()
        if combo.isEditable():                       # a list you can also type into: its arrow opens it
            from PySide6.QtWidgets import QStyle, QStyleOptionComboBox
            opt = QStyleOptionComboBox()
            combo.initStyleOption(opt)
            at = combo.style().subControlRect(QStyle.CC_ComboBox, opt, QStyle.SC_ComboBoxArrow, combo).center()
        QTest.mouseClick(combo, Qt.LeftButton, Qt.NoModifier, at)
        self.settle()
        if not combo.view().isVisible():
            raise RuntimeError("the list did not open on a click")
        # Qt ignores a release in a just-opened list for a double-click time (so the opening
        # click does not pick an entry); a person is never that quick
        t0 = time.time()
        while time.time() - t0 < QApplication.doubleClickInterval() / 1000.0 + 0.05:
            self.settle(1, 0.01)
        view = combo.view()
        if index is None:
            index = combo.findData(data)
        if index < 0:
            raise ValueError("no %r in the list" % (data,))
        mi = view.model().index(index, combo.modelColumn())
        view.scrollTo(mi)
        self.settle()
        r = view.visualRect(mi)
        QTest.mouseMove(view.viewport(), r.center())
        self.settle()
        QTest.mouseClick(view.viewport(), Qt.LeftButton, Qt.NoModifier, r.center())
        self.settle()
        try:
            still_open = view.isVisible()
        except RuntimeError:
            return                                   # the bar was rebuilt by the choice: the list is gone
        if still_open:
            item = view.model().index(index, combo.modelColumn())
            detail = "entry %d '%s' of %d, enabled %s, at %s in a list of %s on the screen at %s" % (
                index, combo.itemText(index), combo.count(), bool(view.model().flags(item) & Qt.ItemIsEnabled),
                r.getRect(), view.viewport().rect().getRect(), view.window().geometry().getRect())
            combo.hidePopup()
            raise RuntimeError("the list stayed open after the click (%s)" % detail)

    def tab(self, index):
        bar = self.w.tabs.tabBar()
        QTest.mouseClick(bar, Qt.LeftButton, Qt.NoModifier, bar.tabRect(index).center())
        self.settle()

    def buttons_for(self, action):
        return [b for b in self.w.findChildren(QToolButton)
                if b.defaultAction() is action and b.isVisible() and b.isEnabled()]

    def menu_path(self, action):
        """[top menu, submenu, ...] that holds an action (from the menu bar)."""
        def search(menu, path):
            for a in menu.actions():
                if a is action:
                    return path + [menu]
                if a.menu() is not None:
                    found = search(a.menu(), path + [menu])
                    if found:
                        return found
            return None
        for top in self.w.menuBar().actions():
            if top.menu() is not None:
                found = search(top.menu(), [])
                if found:
                    return found
        return None

    def trigger(self, action, via="button"):
        """Use a command the way a user does: its button (toolbar, strip, panel), its
        menu entry (menu bar, submenus), or its keyboard shortcut."""
        if via == "button":
            buttons = self.buttons_for(action)
            if buttons:
                self.click(buttons[0])
                return
            via = "menu"
        if via == "menu":
            path = self.menu_path(action)
            if path:
                bar = self.w.menuBar()
                QTest.mouseClick(bar, Qt.LeftButton, Qt.NoModifier, bar.actionGeometry(path[0].menuAction()).center())
                self.settle(4)
                for parent, sub in zip(path, path[1:]):
                    r = parent.actionGeometry(sub.menuAction())
                    QTest.mouseMove(parent, r.center())
                    self.settle(4, 0.08)                 # submenus open after a short hover
                    if not sub.isVisible():
                        QTest.mouseClick(parent, Qt.LeftButton, Qt.NoModifier, r.center())
                        self.settle(4, 0.05)
                menu = path[-1]
                r = menu.actionGeometry(action)
                QTest.mouseMove(menu, r.center())
                self.settle(2)
                QTest.mouseClick(menu, Qt.LeftButton, Qt.NoModifier, r.center())
                self.settle()
                return
            via = "key"
        # "key" uses the command's first shortcut; "key:Ctrl+[" one of its other keys
        sequence = QKeySequence(via[4:]) if via.startswith("key:") else action.shortcut()
        if sequence.isEmpty():
            raise RuntimeError("%s has no button, menu entry or shortcut" % action.text())
        combo = sequence[0]
        if QApplication.activeWindow() is not self.w and QApplication.activeModalWidget() is None:
            # a desktop's window manager makes the main window active again when a dialog
            # closes; the test screen has none, so the test does it
            self.w.activateWindow()
            self.settle()
        fired = []

        def note(*_args):
            fired.append(1)
        action.triggered.connect(note)
        target = QApplication.focusWidget() or self.w           # where the system sends a key press
        QTest.keyClick(target, combo.key(), combo.keyboardModifiers())
        self.settle()
        action.triggered.disconnect(note)
        if not fired:
            raise RuntimeError("the shortcut %s did nothing (keyboard focus in %s, active window %s)" % (
                sequence.toString(), type(target).__name__, type(QApplication.activeWindow()).__name__))

    # ------------------------------------------------------------------ steps
    def element_at(self, e):
        """A bed point inside an element (scene mm): the middle of its bounding box."""
        xmin, xmax, ymin, ymax = e.bounds
        return (xmin + xmax) / 2 * MM, -(ymin + ymax) / 2 * MM

    def undo_redo_buttons(self):
        return self.buttons_for(self.w.act_undo), self.buttons_for(self.w.act_redo)

    def step(self, name, action, undo=True, change=True, check=None, undo_steps=1):
        """Run one step: action(), then the window must tell the truth; check()
        (optional) returns (ok, detail); a step that changes the project is undone
        and redone with the toolbar buttons."""
        self.steps += 1
        before = truth.state(self.w)
        try:
            action()
            self.settle()
        except Exception:
            self.fail(name, "error: %s" % traceback.format_exc(limit=4))
            return False
        ok = True
        self.seen_fields |= set(truth.bar_fields(self.w.tool_options))
        for description, _handler, optional in self.dialog_handlers:
            if not optional:
                self.fail(name, "the dialog '%s' did not open" % description)
                ok = False
        self.dialog_handlers = []                    # answers are for this step only
        for problem in truth.check_window(self.w):
            self.fail(name, problem)
            ok = False
        if check is not None:
            good, detail = check()
            if not good:
                self.fail(name, "check: %s" % detail)
                ok = False
        after = truth.state(self.w)
        if change is None:
            pass
        elif change and before == after:
            self.fail(name, "nothing changed")
            return False
        elif not change and before != after:
            self.fail(name, "the project changed: %s" % truth.difference(before, after))
            ok = False
        if undo and before != after:
            for _i in range(undo_steps):
                self.trigger(self.w.act_undo)
            diff = truth.difference(before, truth.state(self.w))
            if diff:
                self.fail(name, "undo did not bring back the state before: %s" % diff)
                ok = False
            for problem in truth.check_window(self.w):
                self.fail(name + " (after undo)", problem)
                ok = False
            for _i in range(undo_steps):
                self.trigger(self.w.act_redo)
            diff = truth.difference(after, truth.state(self.w))
            if diff:
                self.fail(name, "redo did not bring back the state after: %s" % diff)
                ok = False
            for problem in truth.check_window(self.w):
                self.fail(name + " (after redo)", problem)
                ok = False
        if not ok or not getattr(self, "quiet", False):
            print("%-5s %s" % ("OK" if ok else "FAIL", name))
        return ok

    # ------------------------------------------------------------------ options bar
    def new_value(self, widget, attr):
        """Another valid value for a field (what a user would type or pick)."""
        if isinstance(widget, QFontComboBox):
            current = widget.currentIndex()
            return widget.itemText(1 if current != 1 else 2)
        if isinstance(widget, QComboBox):
            current = widget.currentIndex()
            index = (current + 1) % widget.count()
            return widget.itemData(index)
        if isinstance(widget, QToolButton):
            return not widget.isChecked()
        if isinstance(widget, QPlainTextEdit):
            return widget.toPlainText() + " 2"
        if isinstance(widget, (QSpinBox, QDoubleSpinBox)):
            step = {"hinge_angle": 45.0, "fill_angle": 30.0, "sides": 1, "tabs": 2, "text_path_offset": 5.0,
                    "hinge_band": 20.0, "hinge_band_offset": 5.0, "corner_radius": 3.0, "font_size": 2.0,
                    "text_spacing": 0.5, "text_path_distance": 1.0}.get(attr, widget.singleStep() * 2)
            value = widget.value() + step
            if value > widget.maximum():
                value = widget.value() - step
            return value
        raise TypeError(widget)

    def set_field(self, attr, value):
        """Change a field of the options bar with real input."""
        widget = truth.bar_fields(self.w.tool_options)[attr]
        if isinstance(widget, QFontComboBox):
            self.pick(widget, index=widget.findText(value))
        elif isinstance(widget, QComboBox):
            self.pick(widget, data=value)
        elif isinstance(widget, QToolButton):
            if widget.isChecked() != bool(value):
                self.click(widget)
        elif isinstance(widget, QPlainTextEdit):
            self.type_text(widget, value)
        else:
            self.type_number(widget, value)

    def every_field(self, what, change=True):
        """Change every field the options bar shows now, one after the other (fields
        that appear after a change are done too). change=False: the fields are the
        tool's settings, the project stays as it is."""
        done = set()
        while True:
            fields = truth.bar_fields(self.w.tool_options)
            todo = [a for a in sorted(fields) if a not in done]
            if not todo:
                break
            attr = todo[0]
            done.add(attr)
            widget = fields[attr]
            value = self.new_value(widget, attr)
            if attr in ("fill_pattern", "hinge_pattern") and not value:
                value = widget.itemData(1)               # a pattern, so its settings appear
            self.covered_fields.add((what, attr))
            self.covered_widgets.add("bar " + attr)
            self.step("%s: options bar %s -> %r" % (what, attr, value), lambda: self.set_field(attr, value),
                      change=change, check=lambda a=attr, v=value: self._field_shows(a, v))

    def _field_shows(self, attr, value):
        fields = truth.bar_fields(self.w.tool_options)
        if attr not in fields:
            return True, ""                              # e.g. "straight text": the section went away
        shown = truth.shown_value(fields[attr])
        if isinstance(shown, float):
            return abs(shown - value) < 0.02, "shows %r, typed %r" % (shown, value)
        return shown == value, "shows %r, chose %r" % (shown, value)


# ====================================================================== the session
def session(s):
    w = s.w

    # --- the laser: connect, jog, home ------------------------------------------------
    s.step("Laser tab (click)", lambda: s.tab(1), change=False)
    s.step("connect to the laser (plug button)", lambda: s.click(w.btn_connect), change=False,
           check=lambda: (w.laser.connected and s.fake is not None, "connected %s" % w.laser.connected))
    s.covered_widgets.add("connect")
    s.step("Design tab (click)", lambda: s.tab(0), change=False)

    # --- draw with every tool ---------------------------------------------------------
    def tool(name):
        s.trigger(w.tool_actions[name])

    def draw(name, a, b, mods=Qt.NoModifier, points=None):
        def run():
            tool(name)
            s.drag(a, b, mods=mods, points=points)
        return run

    n0 = len(w.elements)
    s.step("draw a rectangle (drag)", draw("rectangle", (20, 20), (70, 50)),
           check=lambda: (len(w.elements) == n0 + 1 and abs(w.elements[-1].size[0] * MM - 50) < 0.6,
                          "%d elements, width %.2f" % (len(w.elements), w.elements[-1].size[0] * MM)))
    s.step("draw a circle (ellipse tool, Shift)", draw("ellipse", (90, 20), (120, 40), Qt.ShiftModifier),
           check=lambda: (abs(w.elements[-1].size[0] - w.elements[-1].size[1]) * MM < 0.6, "not round"))
    s.step("draw a polygon", draw("polygon", (140, 20), (175, 55)))
    s.step("draw a line (Shift: level)", draw("line", (20, 70), (80, 72), Qt.ShiftModifier),
           check=lambda: (w.elements[-1].size[1] * MM < 0.01, "height %.3f" % (w.elements[-1].size[1] * MM)))

    def polyline():
        tool("polyline")
        for x, y in ((100, 70), (150, 70), (125, 110)):
            s.click_bed(x, y)
        s.click_bed(100, 70)                              # the first point again: closed
    s.step("draw a closed polyline (clicks)", polyline,
           check=lambda: (w.elements[-1].shape.kind == "polyline" and w.elements[-1].shape.closed_path, "not closed"))

    def pen():
        tool("pen")
        s.click_bed(190, 70)
        s.drag((230, 70), (240, 90))                      # press and drag: a smooth curve
        s.click_bed(210, 110)
        s.click_bed(190, 70)                              # close
    s.step("draw with the pen (corner, curve, close)", pen,
           check=lambda: (w.elements[-1].shape.kind == "path", "kind %s" % w.elements[-1].shape.kind))
    s.step("draw freehand", draw("freehand", (20, 130), (22, 131), points=[(50, 125), (60, 160), (25, 165)]))

    def text():
        tool("text")
        s.click_bed(100, 140)
    s.step("text tool: click", text, check=lambda: (w.elements[-1].shape.kind == "text", "no text"))
    s.step("text: type into the options bar",
           lambda: s.type_text(truth.bar_fields(w.tool_options)["text"], "Kerfly 1.0 źdźbło"),
           check=lambda: (w.elements[-1].shape.text == "Kerfly 1.0 źdźbło", w.elements[-1].shape.text))

    # --- every field of the options bar, for every kind of shape -----------------------
    s.trigger(w.tool_actions["select"])
    for e in list(w.elements):
        x, y = s.element_at(e)
        s.step("select %s (click)" % e.name, lambda x=x, y=y: s.click_bed(x, y), change=False,
               check=lambda e=e: (w.selected is e, "selected %s" % (w.selected.name if w.selected else None)))
        s.every_field(e.shape.kind)

    # --- position and size fields -------------------------------------------------------
    rect = w.elements[0]
    x, y = s.element_at(rect)
    s.step("select the rectangle", lambda: s.click_bed(x, y), change=False)
    for key, delta in (("x", 7.0), ("y", 4.0), ("w", 10.0), ("h", -5.0)):
        spin = w.sel_fields[key]
        s.covered_widgets.add("field " + key)
        s.step("type %s in the position fields" % key,
               lambda spin=spin, d=delta: s.type_number(spin, spin.value() + d))
    s.step("unlock the proportions, type the width",
           lambda: (s.click(w.sel_lock), s.type_number(w.sel_fields["w"], w.sel_fields["w"].value() + 6)))
    s.click(w.sel_lock)
    s.step("type a rotation", lambda: s.type_number(w.sel_rotation, 30.0))
    s.step("type the rotation back to 0", lambda: s.type_number(w.sel_rotation, 0.0))

    # --- move with the mouse and the keyboard -------------------------------------------
    x, y = s.element_at(rect)
    s.step("drag the rectangle 15 mm right", lambda: s.drag((x, y), (x + 15, y)),
           check=lambda: (abs(s.element_at(rect)[0] - (x + 15)) < 0.6, "moved to %.2f" % s.element_at(rect)[0]))
    s.step("arrow key: 1 mm right", lambda: s.key(Qt.Key_Right))
    s.step("Shift+arrow: 10 mm down", lambda: s.key(Qt.Key_Down, Qt.ShiftModifier))

    # --- save, new project, open: the same project ---------------------------------------
    path = os.path.join(tempfile.mkdtemp(), "session.kerfly")
    saved = {}

    def save():
        s.files.append(path)
        s.trigger(w.act_save_project_as, via="menu")
        saved["state"] = truth.state(w)
    s.step("File → Save project as", save, undo=False, change=False,
           check=lambda: (os.path.isfile(path), "no file"))

    def new():
        s.trigger(w.act_new)
    s.step("File → New project", new, undo=False, check=lambda: (not w.elements, "%d elements" % len(w.elements)))

    def reopen():
        s.files.append(path)
        s.trigger(w.act_open, via="menu")
    s.step("File → Open the saved project", reopen, undo=False,
           check=lambda: (truth.difference(saved["state"], truth.state(w)) == "",
                          truth.difference(saved["state"], truth.state(w))))


def part_edit(s):
    """Edit commands, arranging, combining, tools that work on shapes, node editing."""
    w = s.w
    s.step("File → New project (discard: the project was saved)", lambda: s.trigger(w.act_new), undo=False,
           check=lambda: (not w.elements, "%d elements" % len(w.elements)))

    def put(kind, x0, y0, x1, y1, mods=Qt.NoModifier):
        s.trigger(w.tool_actions[kind])
        s.drag((x0, y0), (x1, y1), mods=mods)
    s.step("draw three rectangles", lambda: (put("rectangle", 20, 20, 50, 40), put("rectangle", 70, 30, 110, 60),
                                             put("rectangle", 140, 25, 160, 70)), undo_steps=3,
           check=lambda: (len(w.elements) == 3, "%d elements" % len(w.elements)))
    a, b, c = w.elements
    s.trigger(w.tool_actions["select"])

    def frame_all():
        s.drag((5, 5), (200, 90))                 # a frame around them on the empty bed
    s.step("select all three with a frame", frame_all, change=False,
           check=lambda: (len(w.preview.selected_elements()) == 3, "%d selected" % len(w.preview.selected_elements())))
    spread = truth.state(w)
    for key in ("top", "bottom", "left", "right", "hcenter", "vcenter"):
        s.step("Align %s (menu)" % key, lambda k=key: (frame_all(), s.trigger(w.act_align[k], via="menu")))
    s.step("Distribute horizontally", lambda: (frame_all(), s.trigger(w.act_distribute_h, via="menu")), change=None)
    s.step("Distribute vertically", lambda: (frame_all(), s.trigger(w.act_distribute_v, via="menu")), change=None)

    def undo_all_arranging():
        for _i in range(12):                       # several undos in a row, back to the spread-out shapes
            if truth.state(w) == spread:
                return
            s.trigger(w.act_undo)
    s.step("undo all the arranging (Undo button, several times)", undo_all_arranging, undo=False,
           check=lambda: (truth.state(w) == spread, truth.difference(spread, truth.state(w))))

    def pick_el(e, mods=Qt.NoModifier):
        x, y = s.element_at(e)
        s.click_bed(x, y, mods)

    def select_one(e):
        s.drag((1, 1), (2, 2))                     # click on the empty bed first: nothing selected
        pick_el(e)
    s.step("rotate 90° clockwise (toolbar)", lambda: (select_one(a), s.trigger(w.act_rot_right)))
    s.step("rotate 90° counter-clockwise (menu)", lambda: (select_one(a), s.trigger(w.act_rot_left, via="menu")))
    s.step("mirror horizontally", lambda: (select_one(a), s.trigger(w.act_mirror_h)))
    s.step("mirror vertically (Ctrl+Shift+V)", lambda: (select_one(a), s.trigger(w.act_mirror_v, via="key")))
    # the same keys as in Inkscape
    s.step("rotate 90° counter-clockwise (Ctrl+[)", lambda: (select_one(a), s.trigger(w.act_rot_left, via="key:Ctrl+[")))
    s.step("rotate 90° clockwise (Ctrl+])", lambda: (select_one(a), s.trigger(w.act_rot_right, via="key:Ctrl+]")))
    s.step("mirror horizontally (H on the bed)", lambda: (select_one(a), s.trigger(w.mirror_keys[0], via="key")))
    s.step("mirror vertically (V on the bed)", lambda: (select_one(a), s.trigger(w.mirror_keys[1], via="key")))
    s.step("centre on the bed", lambda: (select_one(b), s.trigger(w.act_center)))
    s.step("duplicate (Ctrl+D)", lambda: (select_one(b), s.trigger(w.act_duplicate, via="key")),
           check=lambda: (len(w.elements) == 4, "%d elements" % len(w.elements)))
    s.step("delete (Del)", lambda: (select_one(w.elements[-1]), s.trigger(w.act_delete, via="key")),
           check=lambda: (len(w.elements) == 3, "%d elements" % len(w.elements)))
    # the clipboard, as in Inkscape; the copies are cut again at the end (three elements as before)
    s.step("copy (Ctrl+C)", lambda: (select_one(b), s.trigger(w.act_copy, via="key")), change=False)
    def paste_from_toolbar():
        from PySide6.QtGui import QCursor
        button = s.buttons_for(w.act_paste)[0]
        QCursor.setPos(button.mapToGlobal(button.rect().center()))     # the pointer on the button, off the bed
        s.settle()
        s.trigger(w.act_paste)
    s.step("paste (toolbar): 5 mm next to the original", paste_from_toolbar,
           check=lambda: (len(w.elements) == 4 and abs((w.elements[-1].x - b.x) * 25.4 - 5) < 1e-6,
                          "%d elements, %.2f mm" % (len(w.elements), (w.elements[-1].x - b.x) * 25.4)))
    s.step("paste in place (Ctrl+Alt+V)", lambda: s.trigger(w.act_paste_in_place, via="key"),
           check=lambda: (len(w.elements) == 5 and abs(w.elements[-1].x - b.x) < 1e-9, "%d elements" % len(w.elements)))
    s.step("cut (Ctrl+X) the copy in place", lambda: (select_one(w.elements[-1]), s.trigger(w.act_cut, via="key")),
           check=lambda: (len(w.elements) == 4, "%d elements" % len(w.elements)))
    s.step("Edit → Cut the other copy", lambda: (select_one(w.elements[-1]), s.trigger(w.act_cut, via="menu")),
           check=lambda: (len(w.elements) == 3, "%d elements" % len(w.elements)))
    s.step("select all (Ctrl+A)", lambda: s.trigger(w.act_select_all, via="key"), change=False,
           check=lambda: (len(w.preview.selected_elements()) == len(w.elements),
                          "%d selected" % len(w.preview.selected_elements())))

    def escape_on_bed():
        w.preview.setFocus()
        QTest.keyClick(w.preview.viewport(), Qt.Key_Escape)
        s.settle()
    s.step("Esc on the bed: nothing selected", escape_on_bed, change=False,
           check=lambda: (w.preview.selected_elements() == [], "%d selected" % len(w.preview.selected_elements())))
    s.step("Edit → Deselect", lambda: (select_one(a), s.trigger(w.act_deselect, via="menu")), change=False,
           check=lambda: (w.preview.selected_elements() == [], "%d selected" % len(w.preview.selected_elements())))
    s.step("Ctrl+click: two selected", lambda: (select_one(a), pick_el(c, Qt.ControlModifier)), change=False,
           check=lambda: (len(w.preview.selected_elements()) == 2, "%d" % len(w.preview.selected_elements())))
    s.step("group (Ctrl+G)", lambda: (select_one(a), pick_el(c, Qt.ControlModifier),
                                            s.trigger(w.act_group, via="key")),
           check=lambda: (a.group and a.group == c.group, "not grouped"))
    s.step("one click selects the whole group", lambda: select_one(a), change=False,
           check=lambda: (len(w.preview.selected_elements()) == 2, "%d" % len(w.preview.selected_elements())))
    s.step("ungroup (menu)", lambda: (select_one(a), s.trigger(w.act_ungroup, via="menu")),
           check=lambda: (not a.group, "still grouped"))
    # order beside the element list
    s.step("order: down (button beside the list)", lambda: (select_one(a), s.trigger(w.act_order["down"])),
           check=lambda: (w.elements.index(a) == 1, "at %d" % w.elements.index(a)))
    s.step("order: up", lambda: (select_one(a), s.trigger(w.act_order["up"])),
           check=lambda: (w.elements.index(a) == 0, "at %d" % w.elements.index(a)))
    s.step("order: to the end", lambda: (select_one(a), s.trigger(w.act_order["last"])),
           check=lambda: (w.elements[-1] is a, "not last"))
    s.step("order: to the start (Ctrl+PgUp)", lambda: (select_one(a), s.trigger(w.act_order["first"], via="key")),
           check=lambda: (w.elements[0] is a, "not first"))

    # element list: click a row, Ctrl+click another, untick one
    lst = w.element_list

    def row_click(row, mods=Qt.NoModifier):
        r = lst.visualItemRect(lst.item(row))
        QTest.mouseClick(lst.viewport(), Qt.LeftButton, mods, r.center())
        s.settle()
    s.covered_widgets.add("element list")
    s.step("element list: click a row", lambda: row_click(1), change=False,
           check=lambda: (w.preview.selected_elements() == [w.elements[1]], "selection %s" % w.preview.selected_elements()))
    s.step("element list: Ctrl+click a second row", lambda: row_click(2, Qt.ControlModifier), change=False,
           check=lambda: (len(w.preview.selected_elements()) == 2, "%d" % len(w.preview.selected_elements())))

    def untick(row):
        r = lst.visualItemRect(lst.item(row))
        box = QPoint(r.left() + r.height() // 2, r.center().y())        # the tick box at the row's start
        QTest.mouseClick(lst.viewport(), Qt.LeftButton, Qt.NoModifier, box)
        s.settle()
    s.step("element list: untick an element (left out of the job)", lambda: untick(2),
           check=lambda: (not w.elements[2].visible, "still in the job"))
    s.step("element list: tick it again", lambda: untick(2), check=lambda: (w.elements[2].visible, "still out"))

    # combine shapes: two overlapping rectangles
    def overlap():
        s.trigger(w.tool_actions["rectangle"])
        s.drag((40, 110), (90, 150))
        s.trigger(w.tool_actions["ellipse"])
        s.drag((70, 120), (120, 160))
        s.trigger(w.tool_actions["select"])
    s.step("draw two overlapping shapes", overlap, undo_steps=2)
    for op in ("union", "difference", "intersection", "exclusion"):
        def combine(op=op):
            p, q = w.elements[-2], w.elements[-1]
            select_one(p)
            pick_el(q, Qt.ControlModifier)
            # union and difference with Inkscape's keys (Ctrl++, Ctrl+-), the others from the menu
            s.trigger(w.act_boolean[op], via="key" if op in ("union", "difference") else "menu")
        n = len(w.elements)
        s.step("combine shapes: %s" % op, combine,
               check=lambda n=n: (len(w.elements) == n - 1, "%d elements (was %d)" % (len(w.elements), n)))
        if op != "exclusion":
            s.trigger(w.act_undo)                  # back to the two shapes for the next one

    # Offset tool (right strip): its settings in the options bar, then a click on the combined shape
    n = len(w.elements)
    base = w.elements[-1]
    s.step("Edit → Offset (chooses the Offset tool)", lambda: s.trigger(w.act_offset, via="menu"), change=False,
           check=lambda: (w.preview.tool == "offset", "tool %s" % w.preview.tool))
    s.trigger(w.tool_actions["select"])
    s.step("Offset tool (right strip)", lambda: s.trigger(w.tool_actions["offset"]), change=False,
           check=lambda: (w.preview.tool == "offset", "tool %s" % w.preview.tool))
    s.every_field("offset tool", change=False)
    for attr, value in (("offset_distance", 3.0), ("offset_join", "miter"), ("offset_keep", True)):
        s.step("offset tool: %s %r" % (attr, value), lambda a=attr, v=value: s.set_field(a, v), change=None)
    s.step("Offset tool: click the shape (3 mm around it, kept)", lambda: s.click_bed(*s.element_at(base)),
           check=lambda: (len(w.elements) == n + 1 and abs((w.elements[-1].size[0] - base.size[0]) * 25.4 - 6.0) < 0.05,
                          "%d elements, %.2f mm wider" % (len(w.elements), (w.elements[-1].size[0] - base.size[0]) * 25.4)))
    s.trigger(w.tool_actions["select"])

    # text on a path: Put text on path (menu), then the tool
    def line_and_text():
        s.trigger(w.tool_actions["line"])
        s.drag((150, 120), (240, 120), mods=Qt.ShiftModifier)
        s.trigger(w.tool_actions["text"])
        s.click_bed(160, 170)
        s.type_text(truth.bar_fields(w.tool_options)["text"], "ON A LINE")
        s.trigger(w.tool_actions["select"])
    s.step("draw a line and a text", line_and_text, undo_steps=3)
    line, text = w.elements[-2], w.elements[-1]
    s.step("Edit → Put text on path", lambda: (select_one(line), pick_el(text, Qt.ControlModifier),
                                               s.trigger(w.act_text_path, via="menu")),
           check=lambda: (bool(text.shape.text_path), "not on the path"))
    s.every_field("text on a path")

    def tool_click(name, x, y):
        s.drag((1, 1), (2, 2))
        s.trigger(w.tool_actions[name])
        s.click_bed(x, y)
    s.step("Text on a path tool: click the line", lambda: tool_click("textpath", 200, 121),
           check=lambda: (bool(w.elements[-1].shape.text_path), "no text on the line"))
    # fill and hinge tools on a rectangle of their own (the middle of the bed is busy now)
    s.step("draw a rectangle for the fill and the hinge", lambda: put("rectangle", 250, 150, 310, 200))
    b = w.elements[-1]
    s.trigger(w.tool_actions["select"])
    x, y = s.element_at(b)
    s.step("Fill tool: click a rectangle", lambda: tool_click("fill", x, y),
           check=lambda: (bool(b.shape.fill_pattern), "not filled"))
    s.every_field("fill tool")
    s.step("Living hinge tool: click a rectangle", lambda: tool_click("hinge", x, y),
           check=lambda: (bool(b.shape.hinge_pattern), "no hinge"))
    s.every_field("hinge tool")
    s.trigger(w.tool_actions["select"])
    s.step("select the rectangle with the hinge", lambda: select_one(b), change=False)
    s.every_field("rectangle with a hinge")
    # measure: a drag that changes nothing
    s.step("Measure tool: drag", lambda: (s.trigger(w.tool_actions["measure"]), s.drag((10, 180), (60, 200))),
           change=False, check=lambda: ("mm" in w.statusBar().currentMessage(), w.statusBar().currentMessage()))
    s.trigger(w.tool_actions["select"])

    # nodes: double-click a shape, click a node, every node button
    s.step("Edit nodes tool (N), click a shape", lambda: (select_one(c), s.trigger(w.tool_actions["nodes"], via="key"),
                                                           s.click_bed(*s.element_at(c))),
           change=False, check=lambda: (w.preview.tool == "nodes", "tool %s" % w.preview.tool))
    s.trigger(w.tool_actions["select"])
    s.step("double-click a rectangle: edit its nodes", lambda: (select_one(c), s.click_bed(*s.element_at(c), double=True)),
           change=False, check=lambda: (w.preview.tool == "nodes", "tool %s" % w.preview.tool))
    for code, label in (("insert", "Add"), ("curve", "Curve"), ("smooth", "Smooth"), ("symmetric", "Symmetric"),
                        ("line", "Straight"), ("delete", "Remove"), ("close", "Close / open"), ("break", "Cut open")):
        def node_button(code=code):
            points = w.preview.node_scene_points()
            if points:
                s.click_bed(points[0].x(), points[0].y())   # select a node
            from kerfly.i18n import _ as tr
            from kerfly.gui.tool_options import NODE_SECTIONS
            text = next(lbl for _sec, acts in NODE_SECTIONS for c, lbl, *_r in acts if c == code)
            button = next(b for b in w.tool_options.findChildren(QToolButton) if b.text() == tr(text))
            s.click(button)
        s.step("nodes: %s" % label, node_button, change=None)
    s.trigger(w.tool_actions["select"])


def part_layers(s):
    """Layers panel, the Layer list above the bed, materials."""
    w = s.w
    panel = w.layers_panel
    x, y = s.element_at(w.elements[0])

    def add_layer(which=0):
        QTest.mouseClick(panel.add_button, Qt.LeftButton)
        s.settle(4)
        menu = panel.add_button.menu()
        action = menu.actions()[which]
        r = menu.actionGeometry(action)
        QTest.mouseMove(menu, r.center())
        QTest.mouseClick(menu, Qt.LeftButton, Qt.NoModifier, r.center())
        s.settle()
    n = len(w.layers)
    for which, kind in ((1, "engrave"), (2, "raster")):
        n = len(w.layers)
        s.step("layers: + → add a %s layer" % kind, lambda k=which: add_layer(k),
               check=lambda n=n: (len(w.layers) == n + 1, "%d layers" % len(w.layers)))
    n = len(w.layers)
    s.step("layers: + → add a cut layer", add_layer,
           check=lambda: (len(w.layers) == n + 1, "%d layers" % len(w.layers)))
    new = [l for l in w.layers if l.kind == "cut"][-1]
    s.step("select a shape", lambda: (s.drag((1, 1), (2, 2)), s.click_bed(x, y)), change=False)
    combo = lambda: w.layer_assign_box.layout().itemAtPosition(0, 0).widget()
    s.step("Layer list above the bed: the new layer", lambda: s.pick(combo(), data=new.id),
           check=lambda: (w.selected is not None and w.selected.layers.get("cut") == new.id,
                          "layers %s" % (w.selected.layers if w.selected else None)))
    row = lambda: panel.rows[new.id]
    s.covered_widgets |= {"layer speed", "layer passes", "layer kerf", "layer name", "layer colour", "layer tick", "layer delete",
                          "layer add"}
    s.step("layers: type a speed", lambda: s.type_number(row()["speed"], 12.5), undo=False,
           check=lambda: (abs(new.speed - 12.5) < 1e-6, "speed %s" % new.speed))

    def wheel_without_click():
        s.click_bed(*s.element_at(w.elements[0]))         # the keyboard focus goes to the bed view
        s.wheel(row()["speed"], -2)
    s.step("layers: the wheel over the speed without clicking it changes nothing", wheel_without_click,
           change=None, check=lambda: (abs(new.speed - 12.5) < 1e-6 and abs(row()["speed"].value() - 12.5) < 1e-6,
                                       "speed %s, field %s" % (new.speed, row()["speed"].value())))
    s.step("layers: type the kerf of the cut layer", lambda: s.type_number(row()["kerf"], 0.15), undo=False,
           check=lambda: (abs(new.kerf - 0.15) < 1e-6, "kerf %s" % new.kerf))
    passes = lambda: next(sp for sp in panel.grid_box.findChildren(QSpinBox)
                          if panel.grid.getItemPosition(panel.grid.indexOf(sp))[0] ==
                          panel.grid.getItemPosition(panel.grid.indexOf(row()["speed"]))[0])
    s.step("layers: type the passes", lambda: s.type_number(passes(), 2), undo=False,
           check=lambda: (new.passes == 2, "passes %s" % new.passes))
    from PySide6.QtWidgets import QCheckBox, QLineEdit

    def in_row(kind):
        r0 = panel.grid.getItemPosition(panel.grid.indexOf(row()["speed"]))[0]
        for wd in panel.grid_box.findChildren(kind):
            idx = panel.grid.indexOf(wd)
            if idx < 0:
                idx = panel.grid.indexOf(wd.parentWidget())
            if idx >= 0 and panel.grid.getItemPosition(idx)[0] == r0:
                return wd
        raise LookupError(kind)
    s.step("layers: rename", lambda: (s.click(in_row(QLineEdit)), QTest.keyClick(in_row(QLineEdit), Qt.Key_A, Qt.ControlModifier),
                                      QTest.keyClicks(in_row(QLineEdit), "Thin cut"), QTest.keyClick(in_row(QLineEdit), Qt.Key_Return)),
           undo=False, check=lambda: (new.name == "Thin cut", new.name))
    s.colors.append("#00aa55")
    from kerfly.gui.layers_panel import ColorButton
    s.step("layers: colour", lambda: s.click(in_row(ColorButton)), undo=False,
           check=lambda: (new.color.lower() == "#00aa55", new.color))
    s.step("layers: untick (left out of the job)", lambda: s.click(in_row(QCheckBox)), undo=False,
           check=lambda: (not new.enabled, "still on"))
    s.step("layers: tick again", lambda: s.click(in_row(QCheckBox)), undo=False)
    def trash():
        r0 = panel.grid.getItemPosition(panel.grid.indexOf(row()["speed"]))[0]
        s.click(next(b for b in panel.grid_box.findChildren(QToolButton)
                     if b.toolTip().startswith(tr_("Delete this layer")) and panel.grid.indexOf(b) >= 0
                     and panel.grid.getItemPosition(panel.grid.indexOf(b))[0] == r0))
    s.step("layers: delete the layer (its parts go back)", trash,
           check=lambda: (new not in w.layers, "still there"))
    # materials
    s.step("material: choose one", lambda: s.pick(panel.material, index=1), undo=False)
    s.expect_dialog("material library", lambda d: d.accept())
    s.step("Settings → Material library… (opens, OK)", lambda: s.trigger(w.act_materials, via="menu"), change=None, undo=False)
    path = os.path.join(tempfile.mkdtemp(), "materials.json")
    s.files.append(path)
    s.step("Settings → Export material library…", lambda: s.trigger(w.act_export_materials, via="menu"),
           change=False, check=lambda: (os.path.isfile(path), "no file"))
    s.files.append(path)
    s.expect_dialog("import done", lambda d: s.click_dialog_button(d, QMessageBox.Ok))
    s.step("Settings → Import material library…", lambda: s.trigger(w.act_import_materials, via="menu"),
           change=None, undo=False)


def tr_(text):
    from kerfly.i18n import _
    return _(text)


def part_view_and_laser(s):
    """View, laser head, jobs on the stand-in laser."""
    w = s.w
    for mm in ("1 mm", "2 mm", "5 mm", "10 mm"):
        action = next(a for a in w.findChildren(QAction) if a.text() == mm)
        s.step("View → Grid size → %s" % mm, lambda a=action: s.trigger(a, via="menu"), change=False)
    s.step("View → Snap to grid (off)", lambda: s.trigger(w.act_snap, via="menu"), change=False)
    s.step("View → Snap to objects (Ctrl+;)", lambda: s.trigger(w.act_snap_objects, via="key"), change=False)
    s.step("View → Snap to objects again", lambda: s.trigger(w.act_snap_objects, via="menu"), change=False)
    s.step("View → Fit to window", lambda: s.trigger(w.act_fit, via="menu"), change=False)
    s.step("Laser tab", lambda: s.tab(1), change=False)
    s.step("Initialize laser (menu)", lambda: s.trigger(w.act_connect, via="menu"), change=False,
           check=lambda: (w.laser.connected, "not connected"))
    s.step("Home (button)", lambda: s.click(w.btn_home), change=False, check=lambda: (w.head == (0.0, 0.0), w.head))
    from PySide6.QtWidgets import QPushButton
    for name in ("right", "down", "left", "up"):
        tip = tr_({"right": "Move the laser head right by one step", "down": "Move the laser head down by one step",
                   "left": "Move the laser head left by one step", "up": "Move the laser head up by one step"}[name])
        button = next(b for b in w.findChildren(QPushButton) if b.toolTip().startswith(tip))
        s.step("jog %s (arrow button)" % name, lambda b=button: s.click(b), change=False,
               check=lambda: (bool(s.fake.moves), "no move sent"))
    for key, button in zip(("UL", "UR", "CC", "LL", "LR"), w.corner_buttons):
        s.step("head to the design: %s (button)" % key, lambda b=button: s.click(b), change=False)
    for key in ("UL", "UR", "CC", "LL", "LR"):
        s.step("head to the design: %s (menu)" % key, lambda k=key: s.trigger(w.act_corners[k], via="menu"), change=False)
    s.step("Go to X/Y: type and Go", lambda: (s.type_number(w.goto_x, 30), s.type_number(w.goto_y, 20), s.click(w.btn_goto)),
           change=False, check=lambda: (abs(w.head[0] * MM - 30) < 0.1 and abs(w.head[1] * MM + 20) < 0.1, w.head))
    s.step("Laser → Go to X/Y position (Ctrl+Alt+G)", lambda: s.trigger(w.act_goto, via="key"), change=False)
    s.step("Unlock rail (button)", lambda: s.click(w.btn_unlock), change=False)
    s.step("Laser → Unlock rail", lambda: s.trigger(w.act_unlock, via="menu"), change=False)
    s.step("Laser → Unfreeze laser", lambda: s.trigger(w.act_unfreeze, via="menu"), change=False)
    s.step("Home (key)", lambda: s.trigger(w.act_home, via="key"), change=False)
    s.step("Design follows the head: on", lambda: s.click(w.btn_follow_head), change=None, undo=False)
    s.step("Design follows the head: off", lambda: s.trigger(w.act_follow_head, via="menu"), change=None, undo=False)
    s.step("Edit → Place design at the head", lambda: s.trigger(w.act_place_head, via="menu"), change=None)
    s.step("Trace boundary (button)", lambda: (s.click(w.btn_trace), s.wait(lambda: w.worker is None)), change=False)
    s.step("Laser → Trace boundary", lambda: (s.trigger(w.act_trace, via="menu"), s.wait(lambda: w.worker is None)),
           change=False)
    sent = len(s.fake.sent)
    s.step("Start (F9): the job goes to the laser", lambda: (s.trigger(w.act_start, via="key"), s.wait(lambda: w.worker is None)),
           change=False, check=lambda: (len(s.fake.sent) > sent, "nothing sent: %s" % w.statusBar().currentMessage()))

    def pause_resume():
        s.fake.slow = 1000                         # long enough to be paused also on a slow machine
        s.click(w.btn_start)
        s.wait(lambda: "Sending" in w.statusBar().currentMessage(), 20)
        s.click(w.btn_pause)
        s.wait(lambda: w._paused and w.btn_pause.isEnabled(), 30)   # the board confirms the pause
        s.click(w.btn_pause)                                        # the same button resumes
        s.fake.slow = False                                         # and let the job finish
        s.wait(lambda: w.worker is None, 60)
    s.step("Start, Pause, resume", pause_resume, change=False,
           check=lambda: (s.fake.calls.count("pause") >= 2, "calls %s" % s.fake.calls[-5:]))

    def stop():
        s.fake.slow = 1000
        s.click(w.btn_start)
        s.wait(lambda: "Sending" in w.statusBar().currentMessage(), 20)
        s.click(w.btn_stop)
        s.wait(lambda: w.worker is None, 30)
        s.fake.slow = False
    s.step("Start, Stop (button)", stop, change=False, check=lambda: ("e_stop" in s.fake.calls, "no stop"))

    def stop_key():
        s.fake.slow = 1000
        s.fake.calls.clear()
        s.click(w.btn_start)
        s.wait(lambda: "Sending" in w.statusBar().currentMessage(), 20)
        s.trigger(w.act_stop, via="key")
        s.wait(lambda: w.worker is None, 30)
        s.fake.slow = False
    s.step("Start, Stop (Esc)", stop_key, change=False, check=lambda: ("e_stop" in s.fake.calls, "no stop"))
    s.step("Home after the Stop", lambda: s.click(w.btn_home), change=False)
    s.step("Laser → Stop (Esc) when idle", lambda: s.trigger(w.act_stop, via="menu"), change=False)
    egv = os.path.join(tempfile.mkdtemp(), "job.egv")
    s.files.append(egv)
    s.step("File → Save EGV file…", lambda: (s.trigger(w.act_save_egv, via="menu"), s.wait(lambda: w.worker is None)),
           change=False, check=lambda: (os.path.isfile(egv), "no file"))
    s.files.append(egv)
    s.expect_dialog("passes", lambda d: s.click_dialog_button(d, "OK"), optional=True)
    sent = len(s.fake.sent)
    s.step("File → Send EGV file to laser… (clears the bed, as K40 Whisperer)",
           lambda: (s.trigger(w.act_send_egv, via="menu"), s.wait(lambda: w.worker is None)),
           check=lambda: (len(s.fake.sent) > sent, "nothing sent"))
    s.trigger(w.act_undo)                              # the design back on the bed

    def simulate():
        s.trigger(w.act_simulate, via="menu")
        s.settle(10)
        dlg = w._simulation
        if dlg is None or not dlg.isVisible():
            raise RuntimeError("no simulation window")
        dlg.close()
    s.step("View → Simulate job… (opens, close)", simulate, change=False)
    from kerfly.core import udev
    if udev.applies():
        s.expect_dialog("add the rule?", lambda d: s.click_dialog_button(d, QMessageBox.Yes))
        s.expect_dialog("done: plug in again", lambda d: s.click_dialog_button(d, QMessageBox.Ok))
        s.step("Laser → Allow USB access for the laser… (Linux)", lambda: s.trigger(w.act_usb_access, via="menu"),
               change=False, check=lambda: (bool(s.udev_installs), "the rule was not installed"))
    s.step("Laser → Release USB", lambda: s.trigger(w.act_release, via="menu"), change=False,
           check=lambda: (not w.laser.connected, "still connected"))
    s.tab(0)


def part_m3_board(s):
    """Settings: the M3 board; then the power fields of the layers and the test fire."""
    w = s.w

    def choose_m3(dlg):
        board = next(c for c in dlg.findChildren(QComboBox) if c.findText("LASER-M3") >= 0)
        s.pick(board, index=board.findText("LASER-M3"))
        s.click_dialog_button(dlg, tr_("OK") if tr_("OK") != "OK" else "OK")
    s.expect_dialog("settings: board", choose_m3)
    s.step("Settings…: choose the LASER-M3 board, OK", lambda: s.trigger(w.act_settings, via="menu"),
           change=False, undo=False, check=lambda: (w.power_per_stage(), "no power per layer"))
    s.step("Laser tab", lambda: s.tab(1), change=False)
    s.step("connect again", lambda: s.click(w.btn_connect), change=False, check=lambda: (w.laser.connected, ""))
    from PySide6.QtWidgets import QDoubleSpinBox as _D
    from PySide6.QtWidgets import QAbstractSpinBox as _A
    spins = w.test_fire_row.findChildren(_A)
    for sp in spins:
        s.step("test fire: type %s" % sp.suffix().strip(), lambda sp=sp: s.type_number(sp, max(sp.minimum(), 10)),
               change=False)
    s.step("Test fire", lambda: s.click(w.btn_test_fire), change=False,
           check=lambda: ("pulse_laser" in s.fake.calls, s.fake.calls[-3:]))
    s.step("jog step: type 2", lambda: s.type_number(w.jog_step, 2.0), change=False)
    s.step("Design tab", lambda: s.tab(0), change=False)
    panel = w.layers_panel
    power = [r for r in panel.grid_box.findChildren(_D) if r.suffix().strip() == "%"]
    s.step("layers: type a power (M3)", lambda: s.type_number(power[0], 35), undo=False,
           check=lambda: (any(abs(l.power - 0.35) < 1e-6 for l in w.layers), [l.power for l in w.layers]))
    s.covered_widgets.add("layer power")


def part_generators(s):
    """Every generator: its button (toolbar) or menu entry, a number typed into its dialog,
    Insert; the design comes as one undo step."""
    w = s.w
    s.expect_dialog("save first?", lambda d: s.click_dialog_button(d, QMessageBox.Discard), optional=True)
    s.step("File → New project", lambda: s.trigger(w.act_new), undo=False, change=None)
    for n, (key, action) in enumerate(w.act_generators.items()):
        def answer(dlg):
            numbers = [wd for wd in dlg.widgets.values()
                       if isinstance(wd, (QSpinBox, QDoubleSpinBox)) and wd.isEnabled()]
            if numbers:                                  # change the first number, as a user would
                spin = numbers[0]
                value = spin.value() + (spin.singleStep() if spin.value() < spin.maximum() else -spin.singleStep())
                s.type_number(spin, value)
            from PySide6.QtWidgets import QDialogButtonBox
            ok = dlg.findChild(QDialogButtonBox).button(QDialogButtonBox.Ok)   # Insert / Generate stamp
            QTest.mouseClick(ok, Qt.LeftButton)
        s.expect_dialog(key, answer)
        count = len(w.elements)
        assert count == 0, "the bed should be empty before each generator"
        s.step("Generators → %s (%s)" % (action.text().replace("…", ""), "toolbar" if n % 2 == 0 else "menu"),
               lambda a=action, via=("button" if n % 2 == 0 else "menu"): s.trigger(a, via=via),
               check=lambda c=count: (len(w.elements) > c, "%d elements (was %d)" % (len(w.elements), c)))
        s.trigger(w.act_undo)                             # an empty bed for the next one


def part_files_and_help(s):
    w = s.w
    s.files.append(os.path.join(FIX, "shapes.svg"))
    n = len(w.elements)
    s.step("File → Add design… (SVG)", lambda: s.trigger(w.act_add, via="menu"), undo=True,
           check=lambda: (len(w.elements) == n + 1, "%d elements" % len(w.elements)))
    s.step("File → Reload design (F5)", lambda: s.trigger(w.act_reload, via="key"), change=None, undo=False)
    from PySide6.QtWidgets import QPushButton
    def calc_raster():
        rows = [r for r in w.layers_panel.rows.values() if r.get("calc") is not None]
        buttons = [r["calc"] for r in rows if s.on_screen(r["calc"])]
        if not buttons:
            raise RuntimeError("no raster time button (raster layer row) on the screen")
        s.click(buttons[0])
        s.wait(lambda: w.worker is None)
        s.covered_actions.add(id(w.act_calc_time))     # the same command as the button
    s.step("layers: raster time button (calculator)", calc_raster, change=False,
           check=lambda: (not any(s.on_screen(r["calc"]) for r in w.layers_panel.rows.values()
                                  if r.get("calc") is not None), "the time is still unknown"))
    s.files.append(os.path.join(s.tmp, "again.kerfly"))
    s.step("File → Save project as… (again)", lambda: s.trigger(w.act_save_project_as, via="menu"), change=False, undo=False)
    s.step("File → Save project (Ctrl+S)", lambda: s.trigger(w.act_save_project, via="key"), change=False, undo=False)
    s.step("File → Save settings as default", lambda: s.trigger(w.act_save_settings, via="menu"), change=False, undo=False)
    s.files.append(os.path.join(FIX, "shapes.dxf"))
    s.expect_dialog("DXF units", lambda d: s.click_dialog_button(d, "OK"), optional=True)
    s.step("File → Open design… (DXF, replaces)", lambda: s.trigger(w.act_open), undo=False,
           check=lambda: (len(w.elements) == 1, "%d elements" % len(w.elements)))
    s.expect_dialog("settings", lambda d: d.accept())
    s.step("Settings → Settings… (opens, OK)", lambda: s.trigger(w.act_settings, via="menu"), change=False, undo=False)
    s.step("Help → User guide (F1)", lambda: s.trigger(w.act_guide, via="key"), change=False,
           check=lambda: (any("guide" in u for u in s.opened_urls), s.opened_urls))
    report = os.path.join(s.tmp, "report.txt")
    s.files.append(report)
    s.step("Help → Save diagnostic report…", lambda: s.trigger(w.act_report, via="menu"), change=False,
           check=lambda: (os.path.isfile(report), "no report"))
    s.files.append(os.path.join(s.tmp, "report2.txt"))
    s.expect_dialog("what kind", lambda d: s.click_dialog_button(d, tr_("Another problem")))
    s.expect_dialog("form opening", lambda d: s.click_dialog_button(d, QMessageBox.Close))
    s.step("Help → Report a problem on GitHub…", lambda: s.trigger(w.act_report_problem, via="menu"), change=False,
           check=lambda: (any("issues/new" in u for u in s.opened_urls), s.opened_urls[-1:]))
    s.step("Help → Open the log folder", lambda: s.trigger(w.act_log_folder, via="menu"), change=False)

    def check_updates():
        s.trigger(w.act_check_updates)                       # the Updates button of the toolbar
        s.wait(lambda: w.update_bar.isVisible(), 10)
    s.step("Updates (toolbar): a newer version, the bar above the bed", check_updates, change=False,
           check=lambda: (w.update_bar.isVisible() and "99.0" in w.update_bar.text.text(), w.update_bar.text.text()))
    s.step("update bar: See the release", lambda: s.click(w.update_bar.open_button), change=False,
           check=lambda: (s.opened_urls[-1:] == ["https://github.com/cyryllo/Kerfly/releases/tag/v99.0"],
                          s.opened_urls[-1:]))
    s.step("update bar: Skip this version", lambda: s.click(w.update_bar.skip_button), change=False,
           check=lambda: (not w.update_bar.isVisible() and w.values.get("update_skip") == "99.0",
                          w.values.get("update_skip")))
    s.expect_dialog("about", lambda d: d.accept())
    s.step("Help → About Kerfly", lambda: s.trigger(w.act_about, via="menu"), change=False)
    s.expect_dialog("unsaved changes", lambda d: s.click_dialog_button(d, QMessageBox.Discard))
    s.step("File → Quit", lambda: s.trigger(w.act_quit, via="menu"), change=None, undo=False,
           check=lambda: (not w.isVisible(), "the window is still open"))


def coverage(s):
    """Everything a user can use must have been used by the session (ROADMAP: release
    tests, step 3): every command, every options bar field and every control of the
    panels. A new function without its release test fails here."""
    from PySide6.QtWidgets import QDockWidget, QPushButton, QToolBar
    w = s.w
    toggles = {id(t.toggleViewAction()) for t in w.findChildren(QToolBar)} | \
        {id(d.toggleViewAction()) for d in w.findChildren(QDockWidget)}
    gaps = []
    for action in w.findChildren(QAction):
        if id(action) in toggles or action.menu() or action.isSeparator() or not action.text():
            continue
        if id(action) not in s.covered_actions:
            gaps.append("command '%s'" % action.text().replace("&", ""))
    covered_attrs = {attr for _what, attr in s.covered_fields}
    for attr in sorted(s.seen_fields - covered_attrs):
        gaps.append("options bar field '%s'" % attr)
    fixed = dict(("field " + k, sp) for k, sp in w.sel_fields.items())
    fixed.update({"rotation field": w.sel_rotation, "proportions lock": w.sel_lock, "Go to X": w.goto_x,
                  "Go to Y": w.goto_y, "jog step": w.jog_step, "material list": w.layers_panel.material})
    for name in ("btn_connect", "btn_home", "btn_unlock", "btn_follow_head", "btn_start", "btn_pause", "btn_stop",
                 "btn_trace", "btn_goto", "btn_test_fire"):
        fixed[name] = getattr(w, name)
    for n, b in enumerate(w.corner_buttons):
        fixed["corner button %d" % (n + 1)] = b
    for b in w.findChildren(QPushButton):
        if b.toolTip().startswith(tr_("Move the laser head").split(" ")[0]) and "step" in b.toolTip():
            fixed["jog " + b.toolTip()[:40]] = b
    for name, widget in fixed.items():
        if id(widget) not in s.touched:
            gaps.append(name)
    for name in ("element list", "layer speed", "layer passes", "layer kerf", "layer power", "layer name", "layer colour",
                 "layer tick", "layer delete", "layer add"):
        if name not in s.covered_widgets:
            gaps.append(name)
    print("\nCoverage: %d commands, %d options bar fields, %d panel controls; not used: %s" % (
        len(s.covered_actions), len(covered_attrs), len(fixed), ", ".join(gaps) if gaps else "none"))
    for gap in gaps:
        s.fail("coverage", "never used in the release test: %s" % gap)
    return gaps


def main():
    app = QApplication(sys.argv)
    s = Session(app)
    for part in (session, part_edit, part_layers, part_view_and_laser, part_m3_board, part_generators,
                 part_files_and_help):
        try:
            part(s)
        except Exception:
            s.fail(part.__name__, traceback.format_exc())
    coverage(s)
    if s.w.isVisible():
        s.w._dirty = False
        s.w.close()
    print("\n%d steps, %d problems" % (s.steps, len(s.failures)))
    if s.failures:
        print("Release test FAILED")
        return 1
    print("Release test passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
