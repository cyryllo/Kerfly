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
# as if running from an AppImage on Linux: Settings → Add Kerfly to the applications menu writes here
os.environ["XDG_DATA_HOME"] = tempfile.mkdtemp(prefix="kerfly_release_data_")
if sys.platform.startswith("linux") and not os.environ.get("APPIMAGE"):
    os.environ["APPIMAGE"] = os.path.join(os.environ["HOME"], "Kerfly-test-x86_64.AppImage")
    open(os.environ["APPIMAGE"], "w").close()
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

from dataclasses import replace  # noqa: E402

from kerfly.core import config  # noqa: E402
from kerfly.core.layers import layer_of  # noqa: E402
from kerfly.gui import truth  # noqa: E402
from kerfly.gui.main_window import MainWindow  # noqa: E402
from fakes import FakeGrbl, FakeK40  # noqa: E402

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
                name = s.files.pop(0)
                if kind == "save" and os.path.abspath(name).startswith(os.path.abspath(TESTS_DIR) + os.sep):
                    # answers got out of step: never write over the test files (a report once replaced a fixture)
                    s.fail("dialog", "a save picker was answered with a test file: %s (answers out of step)" % name)
                    return "", ""
                return name, ""
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
        # on X11 QTest moves the real pointer and the server sends that move back a moment later, with no
        # button held: let it arrive before the press, or it lands in the drag and stops it
        self.settle(4, 0.02)
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
        self.settle(4, 0.02)                     # the pointer's move back from X11 first (see drag)
        if double:
            QTest.mouseDClick(self.vp, Qt.LeftButton, mods, p)
        else:
            QTest.mouseClick(self.vp, Qt.LeftButton, mods, p)
        self.settle()

    def tick(self, box):
        """Click the square of a tick box (a wide box's middle is empty space after its text)."""
        from PySide6.QtWidgets import QStyle, QStyleOptionButton
        option = QStyleOptionButton()
        box.initStyleOption(option)
        square = box.style().subElementRect(QStyle.SE_CheckBoxIndicator, option, box)
        if not self.on_screen(box):
            raise RuntimeError("the tick box %r is not on the screen" % box.text())
        QTest.mouseClick(box, Qt.LeftButton, Qt.NoModifier, square.center())
        self.settle()

    def right_click_bed(self, x, y):
        p = self.pos(x, y)
        QTest.mouseMove(self.vp, p)
        self.settle(4, 0.02)                     # the pointer's move back from X11 first (see drag)
        QTest.mouseClick(self.vp, Qt.RightButton, Qt.NoModifier, p)
        self.settle()

    def settings_page(self, dlg, title=None, widget=None):
        """Show a page of Settings by clicking its category in the list on the left (by its title, or the
        page a field is on)."""
        lst = getattr(dlg, "categories", None)
        if lst is None or not lst.isVisible():           # Settings → Lasers…: one page, scrolled to the field
            from PySide6.QtWidgets import QScrollArea
            area = widget.parentWidget()
            while area is not None and not isinstance(area, QScrollArea):
                area = area.parentWidget()
            if area is not None:
                area.ensureWidgetVisible(widget)
            self.settle()
            return
        index = dlg.page_of(widget) if widget is not None else next(
            i for i in range(lst.count()) if lst.item(i).text() == title)
        lst.scrollToItem(lst.item(index))
        QTest.mouseClick(lst.viewport(), Qt.LeftButton, Qt.NoModifier, lst.visualItemRect(lst.item(index)).center())
        self.settle()

    def menu_pick(self, menu, *texts):
        """Click an entry of an open menu, through its submenus (by their texts)."""
        for n, text in enumerate(texts):
            action = next((a for a in menu.actions()
                           if not a.isSeparator() and a.text().replace("&", "") == text), None)   # not a heading
            if action is None:
                raise RuntimeError("the menu has no '%s' (%s)" % (text, [a.text() for a in menu.actions()]))
            r = menu.actionGeometry(action)
            QTest.mouseMove(menu, r.center())
            self.settle(4, 0.08)                         # submenus open after a short hover
            if n < len(texts) - 1:
                if not action.menu().isVisible():
                    QTest.mouseClick(menu, Qt.LeftButton, Qt.NoModifier, r.center())
                    self.settle(4, 0.05)
                menu = action.menu()
            else:
                QTest.mouseClick(menu, Qt.LeftButton, Qt.NoModifier, r.center())
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
            first = len(getattr(widget, "single_line", []))        # a system font (single-line: own step)
            current = widget.currentIndex()
            return widget.itemText(first + 1 if current != first + 1 else first + 2)
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

    def window_answer(self, values=(), press="action", tile=None, text=None):
        """A tool's window (Fill, Living hinge, Offset, Text) answered with real input: a tile clicked, the text
        typed, numbers typed, boxes ticked; then its action button (press "remove": its Remove button,
        "cancel": Cancel)."""
        def answer(dlg):
            from PySide6.QtWidgets import QCheckBox, QDialogButtonBox
            if tile is not None:
                self.click(dlg.tiles.buttons[tile])
            if text is not None:
                field = dlg.fields["text"]
                self.touched.add(id(field))
                QTest.mouseClick(field.viewport(), Qt.LeftButton)
                QTest.keyClick(field, Qt.Key_A, Qt.ControlModifier)
                self.type_chars(field, text)
            for attr, value in values:
                widget = dlg.fields[attr]
                if isinstance(widget, QCheckBox):
                    if widget.isChecked() != bool(value):
                        self.tick(widget)
                elif hasattr(widget, "set_family"):
                    widget.set_family(value)
                else:
                    self.type_number(widget, value)
            self.settle(4, 0.05)
            if press == "remove":
                self.click(dlg.remove_button)
            else:
                box = dlg.findChild(QDialogButtonBox)
                QTest.mouseClick(box.button(QDialogButtonBox.Cancel if press == "cancel" else QDialogButtonBox.Ok),
                                 Qt.LeftButton)
        return answer

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
    # the Text window (its preview, the text, font, size): Insert the text
    s.expect_dialog("the Text window: a text typed, Insert the text", s.window_answer(text="Kerfly"))
    s.step("text tool: click, the Text window, type, Insert the text", text,
           check=lambda: (w.elements[-1].shape.kind == "text" and w.elements[-1].shape.text == "Kerfly",
                          w.elements[-1].shape.text if w.elements[-1].shape else "no text"))

    def edit_text_button():
        s.click(w.tool_options.findChild(QToolButton, "edit_text"))
    s.expect_dialog("the Text window: another text, Apply", s.window_answer(text="Kerfly 1.0 źdźbło"))
    s.step("text: Edit text (options bar), type in the Text window, Apply", edit_text_button,
           check=lambda: (w.elements[-1].shape.text == "Kerfly 1.0 źdźbło", w.elements[-1].shape.text))
    # a single-line font (built in): open strokes engraved once; then the font it had
    from kerfly.core.layers import part_present as _present
    font_before = w.elements[-1].shape.font_family
    op_before = w.elements[-1].shape.operation
    s.expect_dialog("the Text window: Hershey Sans 1-stroke", s.window_answer(
        values=[("font_family", "Hershey Sans 1-stroke")]))
    s.step("text: the single-line font Hershey Sans 1-stroke from the Text window's font list", edit_text_button,
           check=lambda: (w.elements[-1].shape.single_line and not w.elements[-1].shape.closed
                          and _present(w.elements[-1].design, "engrave") and not _present(w.elements[-1].design, "raster"),
                          "%s, %s" % (w.elements[-1].shape.font_family, w.elements[-1].shape.operation)))
    s.expect_dialog("the Text window: its system font", s.window_answer(values=[("font_family", font_before)]))
    s.step("text: back to its system font (Text window)", edit_text_button,
           check=lambda: (w.elements[-1].shape.font_family == font_before, w.elements[-1].shape.font_family))
    if w.elements[-1].shape.operation != op_before:
        # its layer back with the Layer list above the bed (a raster layer is offered again: closed letters)
        from kerfly.core.layers import RASTER as _RASTER
        from kerfly.gui.truth import OPERATION_KIND as _OK
        back_layer = w._default_layer[_OK.get(op_before, _RASTER)]
        s.step("text: the Layer list above the bed, back to %s" % back_layer.name,
               lambda: s.pick(w.layer_assign_box.layout().itemAtPosition(0, 0).widget(), data=back_layer.id),
               check=lambda: (w.elements[-1].shape.operation == op_before, w.elements[-1].shape.operation))

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
    # the side handles: the width alone (right side), the height alone (bottom side), the opposite side stays
    def side_handle(kind, far):
        hs = [h for h in w.preview._handles if h.kind == kind and h.isVisible()]
        if not hs:
            raise RuntimeError("no %s handle" % kind)
        h = max(hs, key=lambda h: h.scenePos().x() if kind == "side_x" else h.scenePos().y())
        return h.scenePos().x(), h.scenePos().y()
    size0 = {}

    def stretch(kind, dx, dy):
        size0["wh"] = tuple(round(v * MM, 1) for v in rect.size)
        size0["lt"] = (rect.bounds[0], rect.bounds[3])
        x0, y0 = side_handle(kind, True)
        s.drag((x0, y0), (x0 + dx, y0 + dy))

    def stretched(dw, dh):
        wh = tuple(round(v * MM, 1) for v in rect.size)
        want = (round(size0["wh"][0] + dw, 1), round(size0["wh"][1] + dh, 1))
        stays = abs(rect.bounds[0] - size0["lt"][0]) < 0.004 and abs(rect.bounds[3] - size0["lt"][1]) < 0.004
        return (abs(wh[0] - want[0]) < 0.6 and abs(wh[1] - want[1]) < 0.6 and stays,
                "size %s, want %s, left/top kept %s" % (wh, want, stays))
    s.step("drag the right side handle 10 mm right: the width alone", lambda: stretch("side_x", 10, 0),
           check=lambda: stretched(10, 0))
    s.step("drag the bottom side handle 6 mm down: the height alone", lambda: stretch("side_y", 0, 6),
           check=lambda: stretched(0, 6))
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

    # Join into a polyline: two lines drawn end to end with the Line tool, both selected, Ctrl+J and the
    # toolbar button: one path
    def two_lines():
        s.trigger(w.tool_actions["line"])
        s.drag((150, 20), (190, 20))
        s.trigger(w.tool_actions["line"])             # (a drawing tool is used once)
        s.drag((190, 60), (190, 20))              # ending on the first one's end (a press there would grab it)
        s.trigger(w.tool_actions["select"])
    s.step("draw two lines end to end (Line tool)", two_lines, undo_steps=2,
           check=lambda: (all(e.shape is not None and e.shape.kind == "line" for e in w.elements[-2:]),
                          "%s" % [e.name for e in w.elements[-2:]]))
    for via in ("key", "button"):
        if via == "button":
            s.trigger(w.act_undo)                    # the two lines again (the step above stays done)

        def join(via=via):
            select_one(w.elements[-2])
            pick_el(w.elements[-1], Qt.ControlModifier)
            s.trigger(w.act_join, via=via)
        n = len(w.elements)
        s.step("Join into a polyline (%s)" % ("Ctrl+J" if via == "key" else "toolbar button"), join,
               check=lambda n=n: (len(w.elements) == n - 1 and w.elements[-1].shape.kind == "path"
                                  and len(w.elements[-1].shape.subpaths) == 1
                                  and len(w.elements[-1].shape.subpaths[0]["nodes"]) == 3,
                                  "%d elements (was %d), last %s; selected %s; status '%s'" % (
                                      len(w.elements), n, w.elements[-1].shape.kind,
                                      [e.name for e in w._selection()], w.statusBar().currentMessage())))
    for _i in range(3):
        s.trigger(w.act_undo)                    # the join undone, the two lines away again

    # Nest on the bed: three more rectangles, select all, the toolbar button, a gap of 3 mm typed, Nest
    def three_rects():
        for a, b in (((150, 20), (230, 60)), ((160, 40), (200, 120)), ((180, 30), (260, 80))):
            s.trigger(w.tool_actions["rectangle"])
            s.drag(a, b)
        s.trigger(w.tool_actions["select"])
    s.step("draw three rectangles over each other", three_rects, undo_steps=3)

    # Apply / Cancel of the options bar (the user's choice 2026-11-20): a rectangle selected, its corner radius
    # typed, Cancel: as it was (no undo step left); typed again, Apply: kept, the buttons greyed out
    def radius_then(button):
        def run():
            w.preview.select_element([w.elements[-1]])
            s.settle()
            s.set_field("corner_radius", 4.0)
            s.click(button)
        return run
    s.step("options bar: corner radius typed, Cancel (as it was)", radius_then(w.btn_bar_cancel), change=False,
           check=lambda: (w.elements[-1].shape.corner_radius == 0.0 and not w.btn_bar_cancel.isEnabled(),
                          (w.elements[-1].shape.corner_radius, w.btn_bar_cancel.isEnabled())))
    s.step("options bar: corner radius typed, Apply (kept)", radius_then(w.btn_bar_apply),
           check=lambda: (w.elements[-1].shape.corner_radius == 4.0 and not w.btn_bar_apply.isEnabled(),
                          (w.elements[-1].shape.corner_radius, w.btn_bar_apply.isEnabled())))
    s.trigger(w.act_undo)                        # the radius back to 0 for the nesting below

    def nest_answer(dlg):
        s.type_number(dlg.gap, 3)
        from PySide6.QtWidgets import QDialogButtonBox
        QTest.mouseClick(dlg.findChild(QDialogButtonBox).button(QDialogButtonBox.Ok), Qt.LeftButton)

    def nested_apart():
        boxes = [(e.bounds[0] * MM, e.bounds[1] * MM, e.bounds[2] * MM, e.bounds[3] * MM) for e in w.elements]
        clash = [(i, j) for i in range(len(boxes)) for j in range(i + 1, len(boxes))
                 if boxes[i][0] < boxes[j][1] + 2.9 and boxes[j][0] < boxes[i][1] + 2.9
                 and boxes[i][2] < boxes[j][3] + 2.9 and boxes[j][2] < boxes[i][3] + 2.9]
        return not clash and w.nest_defaults["gap"] == 3.0, "over each other: %s, gap %s" % (clash, w.nest_defaults)
    s.expect_dialog("nest on the bed", nest_answer)
    s.step("Edit → Select all (Ctrl+A), Nest on the bed (toolbar button), gap 3 mm, Nest",
           lambda: (s.trigger(w.act_select_all, via="key"), s.trigger(w.act_nest, via="button")),
           check=nested_apart)
    s.trigger(w.act_undo)                        # back to the shapes before the nesting

    # one shape selected of three: the dialog asks Selected (1) / All (3); All clicked: all three nested
    def nest_all_answer(dlg):
        s.click(dlg.which.buttons["all"])
        from PySide6.QtWidgets import QDialogButtonBox
        QTest.mouseClick(dlg.findChild(QDialogButtonBox).button(QDialogButtonBox.Ok), Qt.LeftButton)
    s.expect_dialog("nest: all parts", nest_all_answer)
    s.step("one shape selected, Nest on the bed (toolbar button): Parts All (3), Nest",
           lambda: (w.preview.select_element(w.elements[-1:]), s.trigger(w.act_nest, via="button")),
           check=lambda: nested_apart() if w.nest_defaults.get("method") == "rectangles" else (False, "method"))
    s.trigger(w.act_undo)                        # back to the shapes before the nesting

    # the same by the real outlines (sparrow): the Outlines button of Method, 2 s of search typed, Nest; a window
    # shows the search; then back to rectangles for the next time
    from kerfly.core.nesting import outlines_available

    def nest_outlines_answer(dlg):
        s.click(dlg.method.buttons["outlines"])
        s.type_number(dlg.seconds, 2)
        from PySide6.QtWidgets import QDialogButtonBox
        QTest.mouseClick(dlg.findChild(QDialogButtonBox).button(QDialogButtonBox.Ok), Qt.LeftButton)

    def nested_by_outlines():
        # no two shapes closer than the gap of 3 mm by their real outlines: each grown by 1.45 mm, none overlap
        import pyclipper
        from kerfly.core import nesting

        def grown(e):
            areas, lines = nesting._part_paths([e])
            pco = pyclipper.PyclipperOffset()
            pco.AddPaths(areas, pyclipper.JT_ROUND, pyclipper.ET_CLOSEDPOLYGON)
            for line in lines:
                pco.AddPath(line, pyclipper.JT_ROUND, pyclipper.ET_OPENROUND)
            return pco.Execute(1.45 * nesting.CLIP)
        shapes = [grown(e) for e in w.elements]
        clash = []
        for i in range(len(shapes)):
            for j in range(i + 1, len(shapes)):
                pc = pyclipper.Pyclipper()
                pc.AddPaths(shapes[i], pyclipper.PT_SUBJECT, True)
                pc.AddPaths(shapes[j], pyclipper.PT_CLIP, True)
                if sum(abs(pyclipper.Area(q)) for q in pc.Execute(pyclipper.CT_INTERSECTION)) > 1.0:
                    clash.append((i, j))
        d = w.nest_defaults
        return not clash and d["method"] == "outlines" and d["seconds"] == 2, "over each other: %s, %s, %s" % (
            clash, d, w.statusBar().currentMessage())
    def search_window(dlg):
        """The window of the search: it closes by itself when the layout is found (Cancel is not pressed)."""
        t0 = time.time()
        while dlg.isVisible() and time.time() - t0 < 60:
            QApplication.processEvents()
            time.sleep(0.02)
    if outlines_available():
        s.expect_dialog("nest by outlines", nest_outlines_answer)
        s.expect_dialog("nest by outlines: the search window", search_window)
        s.step("Nest on the bed (toolbar button): Method Outlines, search time 2 s, Nest",
               lambda: (s.trigger(w.act_select_all, via="key"), s.trigger(w.act_nest, via="button")),
               check=nested_by_outlines)
        s.trigger(w.act_undo)                    # back to the shapes before the nesting
        w.nest_defaults["method"] = "rectangles"
    for _i in range(3):
        s.trigger(w.act_undo)                    # and the three rectangles away

    # Offset: with a shape selected, Edit → Offset opens the Offset window (Cancel: nothing); the tool with
    # nothing selected: a click on the shape opens it (3 mm, sharp corners, keep: Offset)
    n = len(w.elements)
    base = w.elements[-1]
    s.expect_dialog("the Offset window: Cancel", s.window_answer(press="cancel"))
    s.step("Edit → Offset with a shape selected: the Offset window, Cancel",
           lambda: (select_one(base), s.trigger(w.act_offset, via="menu")), change=False,
           check=lambda: (len(w.elements) == n and w.preview.tool == "select", "tool %s" % w.preview.tool))
    s.expect_dialog("the Offset window: 3 mm, sharp corners, keep, Offset",
                    s.window_answer(values=[("offset_distance", 3.0), ("offset_keep", True)], tile="miter"))
    s.step("Offset tool (right strip), nothing selected: click the shape, the Offset window, Offset",
           lambda: (s.click_bed(1, 1), s.trigger(w.tool_actions["offset"]), s.click_bed(*s.element_at(base))),
           check=lambda: (len(w.elements) == n + 1 and abs((w.elements[-1].size[0] - base.size[0]) * 25.4 - 6.0) < 0.05,
                          "%d elements, %.2f mm wider" % (len(w.elements), (w.elements[-1].size[0] - base.size[0]) * 25.4)))
    s.trigger(w.tool_actions["select"])

    # text on a path: Put text on path (menu), then the tool
    def line_and_text():
        s.trigger(w.tool_actions["line"])
        s.drag((150, 120), (240, 120), mods=Qt.ShiftModifier)
        s.trigger(w.tool_actions["text"])
        s.click_bed(160, 170)
        s.trigger(w.tool_actions["select"])
    s.expect_dialog("the Text window: ON A LINE", s.window_answer(text="ON A LINE"))
    s.step("draw a line and a text", line_and_text, undo_steps=2)
    line, text = w.elements[-2], w.elements[-1]
    s.step("Edit → Put text on path", lambda: (select_one(line), pick_el(text, Qt.ControlModifier),
                                               s.trigger(w.act_text_path, via="menu")),
           check=lambda: (bool(text.shape.text_path), "not on the path"))
    s.every_field("text on a path")

    def tool_click(name, x, y):
        s.drag((1, 1), (2, 2))
        s.trigger(w.tool_actions[name])
        s.click_bed(x, y)
    s.expect_dialog("the Text on a path window: Put the text on the path",
                    s.window_answer(values=[("text_path_distance", 1.0)]))
    s.step("Text on a path tool: click the line, the Text on a path window", lambda: tool_click("textpath", 200, 121),
           check=lambda: (bool(w.elements[-1].shape.text_path), "no text on the line"))
    # fill and hinge tools on a rectangle of their own (the middle of the bed is busy now)
    s.step("draw a rectangle for the fill and the hinge", lambda: put("rectangle", 250, 150, 310, 200))
    b = w.elements[-1]
    s.trigger(w.tool_actions["select"])
    x, y = s.element_at(b)
    s.expect_dialog("the Fill window: Honeycomb, 3 mm, Fill it",
                    s.window_answer(values=[("fill_spacing", 3.0), ("fill_angle", 15.0), ("fill_margin", 1.0)],
                                    tile="honeycomb"))
    s.step("Fill tool: click a rectangle, the Fill window (Honeycomb tile, spacing, angle, margin), Fill it",
           lambda: tool_click("fill", x, y),
           check=lambda: (b.shape.fill_pattern == "honeycomb" and b.shape.fill_spacing == 3.0,
                          "%s %s" % (b.shape.fill_pattern, b.shape.fill_spacing)))
    s.expect_dialog("the Living hinge window: wavy cuts, Cut the hinge",
                    s.window_answer(values=[("hinge_cut", 15.0), ("hinge_gap", 2.0), ("hinge_spacing", 2.0),
                                            ("hinge_margin", 3.0)], tile="wave"))
    s.step("Living hinge tool: click a rectangle, the Living hinge window (Wavy tile, fields), Cut the hinge",
           lambda: tool_click("hinge", x, y),
           check=lambda: (b.shape.hinge_pattern == "wave" and b.shape.hinge_cut == 15.0,
                          "%s %s" % (b.shape.hinge_pattern, b.shape.hinge_cut)))
    s.trigger(w.tool_actions["select"])
    s.step("select the rectangle with the hinge", lambda: select_one(b), change=False)
    s.every_field("rectangle with a hinge")
    # the bar's buttons open the windows of the shape shown: Remove the fill there
    s.expect_dialog("the Fill window: Remove the fill", s.window_answer(press="remove"))
    s.step("options bar: the Fill button, the Fill window, Remove the fill",
           lambda: (select_one(b), s.click(w.tool_options.findChild(QToolButton, "open_fill"))),
           check=lambda: (not b.shape.fill_pattern, b.shape.fill_pattern))
    s.expect_dialog("the Living hinge window: zigzag", s.window_answer(tile="zigzag"))
    s.step("options bar: the Living hinge button, the window, zigzag cuts",
           lambda: (select_one(b), s.click(w.tool_options.findChild(QToolButton, "open_hinge"))),
           check=lambda: (b.shape.hinge_pattern == "zigzag", b.shape.hinge_pattern))
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
            text, key = next((lbl, k) for _sec, acts in NODE_SECTIONS for c, lbl, _i, k, *_r in acts if c == code)
            button = next(b for b in w.tool_options.findChildren(QToolButton)
                          if b.text() == "%s (%s)" % (tr(text), key))      # its key in the caption
            s.click(button)
        s.step("nodes: %s" % label, node_button, change=None)
    # a click on the empty bed ends the node editing: back to Select
    empty = tuple(v * 25.4 - 4.0 for v in config.bed_size_inches(w.values))
    s.step("nodes: click the empty bed (back to Select)", lambda: s.click_bed(*empty), change=False,
           check=lambda: (w.preview.tool == "select" and w.tool_actions["select"].isChecked(),
                          "tool %s" % w.preview.tool))
    if w.preview.tool != "select":
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
    # the right-click menu: another layer, left out of the job and back
    first = [l for l in w.layers if l.kind == "cut"][0]
    shape = w.elements[0]

    def right_menu(*texts):
        s.right_click_bed(x, y)
        s.menu_pick(w._context_menu, *texts)
    s.step("right click on the shape → Layer → the first cut layer",
           lambda: right_menu(tr_("Layer"), first.name or tr_("Vector cut")),
           check=lambda: (layer_of(shape, "cut", w.layers) is first, "layers %s" % shape.layers))
    s.step("right click on the shape → Layer → the new cut layer", lambda: right_menu(tr_("Layer"), new.name),
           check=lambda: (layer_of(shape, "cut", w.layers) is new, "layers %s" % shape.layers))
    s.step("right click on the shape → Leave out of the job", lambda: right_menu(tr_("Leave out of the job")),
           check=lambda: (not shape.visible, "still in the job"))
    s.step("right click on the shape → Leave out of the job (off again)",
           lambda: right_menu(tr_("Leave out of the job")), check=lambda: (shape.visible, "still left out"))
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
    # a material made from the current layers keeps the extra ones too (only the three basic ones were saved)
    extras = lambda: [(l.kind, l.name) for l in w.layers if w._default_layer.get(l.kind) is not l
                      and l.kind in ("cut", "engrave", "raster")]
    want = extras()
    s.expect_dialog("material library: New from current layers, OK",
                    lambda d: (s.click_dialog_button(d, tr_("New from current layers")), d.accept()))
    s.step("Settings → Material library… → New from current layers, OK (the extra layers saved too)",
           lambda: s.trigger(w.act_materials, via="menu"), change=None, undo=False,
           check=lambda: (bool(want) and [(x.kind, x.name) for x in (w.materials[-1].extra_layers or [])] == want,
                          "want %s, saved %s" % (want, w.materials[-1].extra_layers)))
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
    # right click on the empty bed: Move the head here (near a corner of the bed, never under a design)
    bed_w_in, bed_h_in = config.bed_size_inches(w.values)
    spot = (bed_w_in * 25.4 - 4.0, bed_h_in * 25.4 - 4.0)          # scene mm (home in the upper left)

    def head_here():
        s.right_click_bed(*spot)
        s.menu_pick(w._context_menu, tr_("Move the head here"))
    s.step("right click on the empty bed → Move the head here", head_here, change=None,
           check=lambda: (abs(w.head[0] - spot[0] / 25.4) < 0.02 and abs(w.head[1] + spot[1] / 25.4) < 0.02,
                          "head %s, wanted %s" % (w.head, (spot[0] / 25.4, -spot[1] / 25.4))))
    s.step("Unlock rail (button)", lambda: s.click(w.btn_unlock), change=False)
    s.step("Laser → Unlock rail", lambda: s.trigger(w.act_unlock, via="menu"), change=False)
    s.step("Laser → Unfreeze laser", lambda: s.trigger(w.act_unfreeze, via="menu"), change=False)
    s.step("Home (key)", lambda: s.trigger(w.act_home, via="key"), change=False)
    s.step("Design follows the head: on", lambda: s.click(w.btn_follow_head), change=None, undo=False)
    # after a corner button the arrows move the design and the head together, the head keeping its place on
    # the design (it used to jump back to the design's origin corner)
    def place_on_design():
        return (round(w.head[0] - w.origin[0], 3), round(w.head[1] - w.origin[1], 3))
    s.step("head to the design: LR (button), with the design following", lambda: s.click(w.corner_buttons[4]),
           change=False)
    corner_place = place_on_design()
    down = next(b for b in w.findChildren(QPushButton)
                if b.toolTip().startswith(tr_("Move the laser head down by one step")))
    origin_before = w.origin
    s.step("jog down (arrow button): the design goes along, the head stays on its lower right corner",
           lambda: s.click(down), change=None, undo=False,
           check=lambda: (place_on_design() == corner_place and corner_place != (0.0, 0.0)
                          and w.origin[1] < origin_before[1],
                          "head on the design %s, was %s; origin %s, was %s" % (
                              place_on_design(), corner_place, w.origin, origin_before)))
    s.step("head to the design: UL (button): back on the design's origin", lambda: s.click(w.corner_buttons[0]),
           change=False, check=lambda: (place_on_design() == (0.0, 0.0), "%s" % (place_on_design(),)))
    s.step("Design follows the head: off", lambda: s.trigger(w.act_follow_head, via="menu"), change=None, undo=False)
    s.step("Edit → Place design at the head", lambda: s.trigger(w.act_place_head, via="menu"), change=None)
    s.step("Trace boundary (button)", lambda: (s.click(w.btn_trace), s.wait(lambda: w.worker is None)), change=False)
    s.step("Laser → Trace boundary", lambda: (s.trigger(w.act_trace, via="menu"), s.wait(lambda: w.worker is None)),
           change=False)
    # Engrave / Outline / Cut only: switched on in Settings → View, then each kind on its own
    def kind_buttons_on(dlg):
        from PySide6.QtWidgets import QCheckBox, QDialogButtonBox
        s.settings_page(dlg, title=tr_("View"))
        s.settle()
        box = next(c for c in dlg.findChildren(QCheckBox) if c.property("setting_key") == "kind_buttons")
        if not box.isChecked():
            s.tick(box)
        QTest.mouseClick(dlg.findChild(QDialogButtonBox).button(QDialogButtonBox.Ok), Qt.LeftButton)
    s.expect_dialog("settings: kind buttons", kind_buttons_on)
    s.step("Settings → View: Engrave, Outline and Cut buttons next to Start",
           lambda: s.trigger(w.act_settings, via="menu"), change=False, undo=False,
           check=lambda: (w.kind_row.isVisible(), "the buttons are not shown"))
    from kerfly.core.layers import build_layers_job as _blj
    from kerfly.core import job as _job

    def only_kind(kind, via):
        before = len(s.fake.sent)
        if via == "button":
            s.click(w.kind_buttons[kind])
        else:
            s.trigger(w.act_run_kind[kind], via="menu")
        s.wait(lambda: w.worker is None)
        return before

    def sent_is_only(kind, before):
        layers = [replace(l, enabled=l.enabled and l.kind == kind) for l in w.layers]
        try:
            chunks, _o = _blj(w.elements, layers, w.job_settings())
        except _job.NoLaserData:
            return False, "no %s data to compare" % kind
        got = b"".join(bytes(data) for _p, data in s.fake.sent[before:])
        want = b"".join(bytes(c.data) for c in chunks)
        return got == want, "sent %d bytes, only-%s job %d bytes" % (len(got), kind, len(want))
    for kind, via in (("raster", "button"), ("engrave", "menu"), ("cut", "button")):
        if not w.act_run_kind[kind].isEnabled():
            s.fail("%s only" % kind, "nothing of this kind on the bed at this point of the session")
            continue
        mark = {}
        s.step("%s only (%s): only these layers go to the laser" % (kind, via),
               lambda k=kind, v=via, m=mark: m.setdefault("before", only_kind(k, v)), change=False,
               check=lambda k=kind, m=mark: sent_is_only(k, m.get("before", 0)))
    sent = len(s.fake.sent)
    s.step("Start (F9): the job goes to the laser", lambda: (s.trigger(w.act_start, via="key"), s.wait(lambda: w.worker is None)),
           change=False, check=lambda: (len(s.fake.sent) > sent, "nothing sent: %s" % w.statusBar().currentMessage()))

    # Home the head after a job (Settings → Machine): the next piece starts from 0, 0
    def setting_box(key, on):
        def answer(dlg):
            from PySide6.QtWidgets import QCheckBox, QDialogButtonBox
            box = next(c for c in dlg.findChildren(QCheckBox) if c.property("setting_key") == key)
            s.settings_page(dlg, widget=box)
            s.settle()
            if box.isChecked() != on:
                s.tick(box)
            QTest.mouseClick(dlg.findChild(QDialogButtonBox).button(QDialogButtonBox.Ok), Qt.LeftButton)
        return answer
    s.expect_dialog("settings: home after a job", setting_box("post_home_xy", True))
    s.step("Settings → Lasers… (the laser's settings): Home the head after a job", lambda: s.trigger(w.act_profiles, via="menu"),
           change=False, undo=False, check=lambda: (w.values.get("post_home_xy") == "1", w.values.get("post_home_xy")))
    mark_home = {}

    def start_and_home():
        mark_home["calls"] = len(s.fake.calls)
        s.trigger(w.act_start, via="key")
        s.wait(lambda: w.worker is None)
    s.step("Start: after the job the head goes home", start_and_home, change=False,
           check=lambda: ("home_position" in s.fake.calls[mark_home.get("calls", 0):] and w.head == (0.0, 0.0),
                          "calls %s, head %s" % (s.fake.calls[mark_home.get("calls", 0):][-4:], w.head)))
    s.expect_dialog("settings: no home after a job", setting_box("post_home_xy", False))
    s.step("Settings → Lasers… (the laser's settings): Home after a job off again", lambda: s.trigger(w.act_profiles, via="menu"),
           change=False, undo=False, check=lambda: (w.values.get("post_home_xy") == "0", w.values.get("post_home_xy")))

    # the laser's home corner: a picture of the bed with a radio button in each corner; the lower left: Home
    # puts the head there, Place design at the head brings the design's lower left corner to it; then back
    def home_corner(corner):
        def answer(dlg):
            from PySide6.QtWidgets import QDialogButtonBox
            from kerfly.gui.widgets import CornerPicker
            picker = next(c for c in dlg.findChildren(CornerPicker) if c.property("setting_key") == "HomeUR")
            s.settings_page(dlg, widget=picker)
            s.click(picker.buttons[corner])
            QTest.mouseClick(dlg.findChild(QDialogButtonBox).button(QDialogButtonBox.Ok), Qt.LeftButton)
        return answer
    s.expect_dialog("settings: home corner lower left", home_corner("LL"))
    s.step("Settings → Lasers… (the laser's settings): Home corner, the lower left in the picture",
           lambda: s.trigger(w.act_profiles, via="menu"), change=False, undo=False,
           check=lambda: (w.values.get("home_lower") == "1" and w.values.get("HomeUR") == "0",
                          (w.values.get("home_lower"), w.values.get("HomeUR"))))
    s.step("Home (button): the head in the lower left corner", lambda: s.click(w.btn_home), change=False,
           check=lambda: (abs(w.head[1] + config.bed_size_inches(w.values)[1]) < 1e-3 and w.head[0] == 0.0, w.head))

    def lower_left_at_head():
        shown = [e for e in w.elements if e.visible]
        x0, y0 = min(e.bounds[0] for e in shown), min(e.bounds[2] for e in shown)
        return abs(x0 - w.head[0]) < 1e-3 and abs(y0 - w.head[1]) < 1e-3, ((x0, y0), w.head)
    s.step("Edit → Place design at the head: its lower left corner at the head",
           lambda: s.trigger(w.act_place_head, via="menu"), change=None, check=lower_left_at_head)
    s.expect_dialog("settings: home corner upper left", home_corner("UL"))
    s.step("Settings → Lasers… (the laser's settings): Home corner, the upper left again",
           lambda: s.trigger(w.act_profiles, via="menu"), change=False, undo=False,
           check=lambda: (w.values.get("home_lower") == "0", w.values.get("home_lower")))
    s.step("Home (button): the head in the upper left corner again", lambda: s.click(w.btn_home), change=False,
           check=lambda: (w.head == (0.0, 0.0), w.head))

    # Settings → Raster → Dithering method: Atkinson, a job goes to the laser with it; back to Floyd-Steinberg
    def dither_to(code):
        def answer(dlg):
            from PySide6.QtWidgets import QDialogButtonBox
            combo = next(c for c in dlg.findChildren(QComboBox) if c.property("setting_key") == "dither")
            s.settings_page(dlg, widget=combo)
            s.settle()
            if not combo.isEnabled():
                raise RuntimeError("the dithering list is greyed out with halftone on")
            s.pick(combo, data=code)
            QTest.mouseClick(dlg.findChild(QDialogButtonBox).button(QDialogButtonBox.Ok), Qt.LeftButton)
        return answer
    s.expect_dialog("settings: dithering Atkinson", dither_to("atkinson"))
    s.step("Settings (Ctrl+,) → Raster → Dithering method: Atkinson", lambda: s.trigger(w.act_settings, via="key"),
           change=False, undo=False, check=lambda: (w.job_settings().dither == "atkinson", w.values.get("dither")))
    sent_before = {}

    def start_dithered():
        sent_before["n"] = len(s.fake.sent)
        s.trigger(w.act_start, via="key")
        s.wait(lambda: w.worker is None and getattr(w, "_after_job_process", None) is None)
    s.step("Start: the job with Atkinson dots goes to the laser", start_dithered, change=False,
           check=lambda: (len(s.fake.sent) > sent_before.get("n", 0), "nothing sent"))
    if getattr(w, "_job_report", None) is not None:
        w._job_report.close()
    s.expect_dialog("settings: dithering Floyd-Steinberg", dither_to("floyd"))
    s.step("Settings (Ctrl+,) → Raster → Dithering method: back to Floyd-Steinberg",
           lambda: s.trigger(w.act_settings, via="key"), change=False, undo=False,
           check=lambda: (w.job_settings().dither == "floyd", w.values.get("dither")))

    # after a job: the report window (on by default) and a program run after the job, its output in the report
    program_dir = tempfile.mkdtemp(prefix="kerfly_release_after_job_")
    before_marker = os.path.join(program_dir, "exhaust_on.txt")
    if sys.platform == "win32":
        program = os.path.join(program_dir, "after.bat")
        open(program, "w").write("@echo off\r\necho exhaust off\r\n")
        before = os.path.join(program_dir, "before.bat")
        open(before, "w").write('@echo off\r\necho on > "%s"\r\n' % before_marker)
    else:
        program = os.path.join(program_dir, "after.sh")
        open(program, "w").write("#!/bin/sh\necho exhaust off\n")
        before = os.path.join(program_dir, "before.sh")
        open(before, "w").write('#!/bin/sh\necho on > "%s"\n' % before_marker)

    def program_on(dlg):
        from PySide6.QtWidgets import QCheckBox, QDialogButtonBox, QLineEdit
        box = next(c for c in dlg.findChildren(QCheckBox) if c.property("setting_key") == "post_exec")
        s.settings_page(dlg, widget=box)
        s.settle()
        for tick_key, path_key, path in (("pre_exec", "pre_batch_path", before), ("post_exec", "batch_path", program)):
            box = next(c for c in dlg.findChildren(QCheckBox) if c.property("setting_key") == tick_key)
            if not box.isChecked():
                s.tick(box)
            field = next(e for e in dlg.findChildren(QLineEdit)
                         if e.parentWidget() is not None and e.parentWidget().property("setting_key") == path_key)
            if not field.isEnabled():
                raise RuntimeError("the %s field is greyed out with the tick on" % path_key)
            s.click(field)
            QTest.keyClick(field, Qt.Key_A, Qt.ControlModifier)
            QTest.keyClicks(field, path)
        QTest.mouseClick(dlg.findChild(QDialogButtonBox).button(QDialogButtonBox.Ok), Qt.LeftButton)
    s.expect_dialog("settings: run a program after a job", program_on)
    s.step("Settings → Lasers… (the laser's settings): Run a program before and after a job, their paths typed",
           lambda: s.trigger(w.act_profiles, via="menu"), change=False, undo=False,
           check=lambda: (w.values.get("post_exec") == "1" and w.values.get("batch_path") == program
                          and w.values.get("pre_exec") == "1" and w.values.get("pre_batch_path") == before,
                          "%s" % [w.values.get(k) for k in ("pre_exec", "pre_batch_path", "post_exec", "batch_path")]))

    def start_and_report():
        s.trigger(w.act_start, via="key")
        s.wait(lambda: getattr(w, "_before_job_process", None) is None and w.worker is None
               and getattr(w, "_after_job_process", None) is None)
        s.settle()

    def report_text():
        box = getattr(w, "_job_report", None)
        return box.text() if box is not None and box.isVisible() else None
    s.step("Start: the program before the job runs, after the job the report shows the time and the "
           "program's output", start_and_report, change=False,
           check=lambda: (os.path.isfile(before_marker) and report_text() is not None
                          and "exhaust off" in report_text(),
                          "before ran %s, report %r" % (os.path.isfile(before_marker), report_text())))
    s.step("report window: OK closes it", lambda: s.click(w._job_report.button(QMessageBox.Ok)), change=False,
           check=lambda: (report_text() is None, "still open"))

    def program_off(dlg):
        from PySide6.QtWidgets import QCheckBox, QDialogButtonBox
        box = next(c for c in dlg.findChildren(QCheckBox) if c.property("setting_key") == "post_exec")
        s.settings_page(dlg, widget=box)
        s.settle()
        for key in ("pre_exec", "post_exec"):
            box = next(c for c in dlg.findChildren(QCheckBox) if c.property("setting_key") == key)
            if box.isChecked():
                s.tick(box)
        QTest.mouseClick(dlg.findChild(QDialogButtonBox).button(QDialogButtonBox.Ok), Qt.LeftButton)
    s.expect_dialog("settings: no program after a job", program_off)
    s.step("Settings → Lasers… (the laser's settings): Run a program before and after a job off again",
           lambda: s.trigger(w.act_profiles, via="menu"), change=False, undo=False,
           check=lambda: (w.values.get("post_exec") == "0" and w.values.get("pre_exec") == "0",
                          "%s, %s" % (w.values.get("pre_exec"), w.values.get("post_exec"))))

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
    # File → Save G-code (GRBL): toolbar button, the origin chosen and S of full power typed, Save…
    nc = os.path.join(tempfile.mkdtemp(), "job.nc")

    def gcode_answer(dlg):
        from PySide6.QtWidgets import QDialogButtonBox
        s.pick(dlg.origin, index=dlg.origin.findData("design"))
        s.type_number(dlg.s_max, 255)
        QTest.mouseClick(dlg.findChild(QDialogButtonBox).button(QDialogButtonBox.Ok), Qt.LeftButton)

    def gcode_ok():
        if not os.path.isfile(nc):
            return False, "no file"
        with open(nc, encoding="utf-8") as f:
            text = f.read()
        powers = [int(word[1:]) for line in text.splitlines() if line.startswith("G1")
                  for word in line.split() if word.startswith("S")]
        return ("G21" in text and "M4 S0" in text and powers and max(powers) <= 255 and max(powers) > 0
                and w.values["gcode_s_max"] == "255" and w.values["gcode_origin"] == "design",
                "powers %s, values %s" % (sorted(set(powers))[:5], {k: w.values[k] for k in ("gcode_s_max",
                                                                                         "gcode_origin")}))
    s.expect_dialog("save G-code", gcode_answer)
    s.files.append(nc)
    s.step("File → Save G-code… (toolbar button): origin at the design, full power S 255, Save…",
           lambda: s.trigger(w.act_save_gcode, via="button"), change=False, check=gcode_ok)
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
        # its own window (docs/ui-mockups/Simulation): Pause, Next layer, Play, Close with real clicks
        s.click(dlg.play)
        if dlg.timer.isActive():
            raise RuntimeError("Pause did not stop the simulation")
        before = dlg.time
        s.click(dlg.next_layer)
        if not dlg.time > before:
            raise RuntimeError("Next layer did not move on (%.2f -> %.2f s)" % (before, dlg.time))
        s.click(dlg.play)
        if not dlg.timer.isActive():
            raise RuntimeError("Play did not start the simulation")
        from PySide6.QtWidgets import QDialogButtonBox
        s.click(dlg.findChild(QDialogButtonBox).button(QDialogButtonBox.Close))
        s.settle()
        if w._open_simulation() is not None:
            raise RuntimeError("Close did not close the simulation")
    s.step("View → Simulate job… (its own window: Pause, Next layer, Play, Close)", simulate, change=False)
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
        s.click_dialog_button(dlg, tr_("Save"))                 # Settings' action (the dialog pattern)
    s.expect_dialog("settings: board", choose_m3)
    s.step("Settings → Lasers…: choose the LASER-M3 board, OK", lambda: s.trigger(w.act_profiles, via="menu"),
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
    # boundary trace with the laser on, with its own power (Settings → Vector), sent to the M3 board
    def trace_laser(on, percent=None):
        def answer(dlg):
            from PySide6.QtWidgets import QCheckBox, QDialogButtonBox
            box = next(c for c in dlg.findChildren(QCheckBox) if c.property("setting_key") == "trace_w_laser")
            field = next(c for c in dlg.findChildren(_D) if c.property("setting_key") == "Trace_power")
            s.settings_page(dlg, widget=box)
            s.settle()
            if box.isChecked() != on:
                s.tick(box)
            if percent is not None:
                if not field.isEnabled():
                    raise RuntimeError("the trace power field is greyed out with the laser on")
                s.type_number(field, percent)
            QTest.mouseClick(dlg.findChild(QDialogButtonBox).button(QDialogButtonBox.Ok), Qt.LeftButton)
        return answer
    s.expect_dialog("settings: trace with the laser on, 25 %", trace_laser(True, 25))
    s.step("Settings → Lasers…: Boundary trace with laser on, its power 25 %",
           lambda: s.trigger(w.act_profiles, via="menu"), change=False, undo=False,
           check=lambda: (w.values.get("trace_w_laser") == "1" and float(w.values.get("Trace_power")) == 0.25,
                          "%s, %s" % (w.values.get("trace_w_laser"), w.values.get("Trace_power"))))
    mark_trace = {}

    def trace_now():
        mark_trace["sent"] = len(s.fake.sent)
        s.click(w.btn_trace)
        s.wait(lambda: w.worker is None)
    want_power = lambda: 0.25 * float(w.values["max_power"])
    s.step("Trace boundary with the laser on: the board gets the trace power", trace_now, change=False,
           check=lambda: (bool(s.fake.sent[mark_trace.get("sent", 0):]) and all(
               abs(p - want_power()) < 1e-6 for p, _d in s.fake.sent[mark_trace.get("sent", 0):]),
               "powers %s, want %s" % ([p for p, _d in s.fake.sent[mark_trace.get("sent", 0):]], want_power())))
    s.expect_dialog("settings: trace without the laser", trace_laser(False))
    s.step("Settings (Ctrl+,) → Vector: Boundary trace with laser on, off again",
           lambda: s.trigger(w.act_profiles, via="menu"), change=False, undo=False,
           check=lambda: (w.values.get("trace_w_laser") == "0", w.values.get("trace_w_laser")))
    s.step("jog step: type 2", lambda: s.type_number(w.jog_step, 2.0), change=False)
    s.step("Design tab", lambda: s.tab(0), change=False)
    panel = w.layers_panel
    power = [row["power"] for row in panel.rows.values() if "power" in row]
    s.step("layers: type a power (M3)", lambda: s.type_number(power[0], 35), undo=False,
           check=lambda: (any(abs(l.power - 0.35) < 1e-6 for l in w.layers), [l.power for l in w.layers]))
    s.covered_widgets.add("layer power")


def part_grbl(s):
    """A GRBL laser, on a stand-in board on the serial port: Settings → Machine: GRBL; connect (it
    homes to the lower left corner), jog, trace, Start (G92 at the design's corner, the G-code streamed),
    pause and resume, stop; back to the K40."""
    w = s.w
    import kerfly.core.grbl as _grbl

    def open_board(port, baud):
        s.grbl = FakeGrbl()
        return s.grbl
    _grbl.open_serial = open_board
    _grbl.serial_ports = lambda: [("/dev/ttyFAKE0", "GRBL stand-in")]
    from PySide6.QtWidgets import QComboBox as _C, QPushButton

    def machine_to(code):
        def answer(dlg):
            from PySide6.QtWidgets import QDialogButtonBox
            box = next(c for c in dlg.findChildren(_C) if c.property("setting_key") == "machine")
            s.pick(box, index=box.findData(code))
            board = next(c for c in dlg.findChildren(_C) if c.property("setting_key") == "board_name")
            port = next(c for c in dlg.findChildren(_C) if c.property("setting_key") == "grbl_baud")
            # only the chosen machine's fields are shown (a K40's board, a GRBL laser's serial speed)
            if board.isVisible() == (code == "grbl") or port.isVisible() != (code == "grbl"):
                raise RuntimeError("the K40 / GRBL fields are not shown / hidden to match the machine")
            QTest.mouseClick(dlg.findChild(QDialogButtonBox).button(QDialogButtonBox.Ok), Qt.LeftButton)
        return answer
    s.expect_dialog("settings: GRBL machine", machine_to("grbl"))
    s.step("Settings → Lasers… (the laser's settings): GRBL board (serial port), OK", lambda: s.trigger(w.act_profiles, via="menu"),
           change=False, undo=False, check=lambda: (w.is_grbl() and w.values["machine"] == "grbl",
                                                    "machine %s" % w.values.get("machine")))
    s.step("Laser tab", lambda: s.tab(1), change=False)
    bed_h = config.bed_size_inches(w.values)[1]
    s.step("connect the GRBL laser (plug button): homes to the lower left corner",
           lambda: s.click(w.btn_connect), change=False,
           check=lambda: (w.laser.connected and "$H" in s.grbl.lines and abs(w.head[1] + bed_h) < 1e-6,
                          "connected %s, lines %s, head %s" % (w.laser.connected, s.grbl.lines[:3], w.head)))
    right = next(b for b in w.findChildren(QPushButton)
                 if b.toolTip().startswith(tr_("Move the laser head right by one step")))
    s.step("jog right (arrow button): a GRBL jog", lambda: s.click(right), change=False,
           check=lambda: (bool(s.grbl.jogs) and s.grbl.jogs[-1][0] > 0 and s.grbl.jogs[-1][1] == 0,
                          "jogs %s" % s.grbl.jogs[-2:]))
    mark = {}

    def trace():
        mark["n"] = len(s.grbl.lines)
        s.click(w.btn_trace)
        s.wait(lambda: w.worker is None)
    s.step("Trace boundary (button): the rectangle round the design, laser off", trace, change=False,
           check=lambda: ("G92 X0 Y0" in s.grbl.lines[mark["n"]:] and sum(
               1 for l in s.grbl.lines[mark["n"]:] if l.startswith("G1") and "S0" in l) == 4,
               "%s" % s.grbl.lines[mark["n"]:][:8]))

    def start():
        mark["n"] = len(s.grbl.lines)
        s.trigger(w.act_start, via="key")
        s.wait(lambda: w.worker is None, 60)
    s.step("Start (F9): the G-code from the design's corner streamed to GRBL", start, change=False,
           check=lambda: ("G92 X0 Y0" in s.grbl.lines[mark["n"]:] and "M4 S0" in s.grbl.lines[mark["n"]:]
                          and not s.grbl.overflow and any(l.startswith("G1") for l in s.grbl.lines[mark["n"]:]),
                          "%d lines, overflow %s" % (len(s.grbl.lines) - mark["n"], s.grbl.overflow)))

    def pause_resume():
        s.grbl.busy_reports = 400                  # the board works long enough to be paused
        s.click(w.btn_start)
        s.wait(lambda: "GRBL" in w.statusBar().currentMessage(), 20)
        s.click(w.btn_pause)
        s.wait(lambda: w._paused and w.btn_pause.isEnabled(), 30)
        s.click(w.btn_pause)                       # the same button resumes
        s.grbl.busy_reports = 0
        s.grbl._busy = 0
        s.grbl.state = "Idle"
        s.wait(lambda: w.worker is None, 60)
    s.step("Start, Pause (feed hold !), resume (~)", pause_resume, change=False,
           check=lambda: (s.grbl.realtime[-2:] == ["!", "~"], "realtime %s" % s.grbl.realtime[-4:]))

    def stop():
        s.grbl.busy_reports = 400
        s.click(w.btn_start)
        s.wait(lambda: "GRBL" in w.statusBar().currentMessage(), 20)
        s.click(w.btn_stop)
        s.wait(lambda: w.worker is None, 30)
        s.grbl.busy_reports = 0
    s.step("Start, Stop (button): GRBL reset", stop, change=False,
           check=lambda: ("reset" in s.grbl.realtime, "realtime %s" % s.grbl.realtime[-4:]))
    s.step("Unlock (button): $X after the reset", lambda: s.click(w.btn_unlock), change=False,
           check=lambda: (s.grbl.lines[-1] == "$X", s.grbl.lines[-2:]))
    s.expect_dialog("settings: K40 machine", machine_to("k40"))
    s.step("Settings → Lasers… (the laser's settings): K40 again, OK", lambda: s.trigger(w.act_profiles, via="menu"),
           change=False, undo=False, check=lambda: (not w.is_grbl(), "machine %s" % w.values.get("machine")))
    s.step("connect the K40 again", lambda: s.click(w.btn_connect), change=False,
           check=lambda: (w.laser.connected and not w.is_grbl(), ""))
    s.step("Design tab", lambda: s.tab(0), change=False)


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

    # the finger box with dividers (beta): 1 across and 1 along typed in, their parts and slots come
    def box_with_dividers(dlg):
        for key in ("dividers_across", "dividers_along"):
            s.type_number(dlg.widgets[key], 1)
        if not dlg.widgets["sliding"].isChecked():
            s.tick(dlg.widgets["sliding"])
        s.settle(6, 0.05)
        # the 3D tab: clicked, the box turned by a drag, pulled apart, the lid slid out (slider clicked, End)
        bar = dlg.preview_tabs.tabBar()
        if not bar.isVisible() or not bar.isTabVisible(1):
            raise RuntimeError("no 3D tab for a box")
        QTest.mouseClick(bar, Qt.LeftButton, Qt.NoModifier, bar.tabRect(1).center())
        s.settle()
        if dlg.preview_tabs.currentIndex() != 1:
            raise RuntimeError("the 3D tab did not open")
        view = dlg.box3d
        yaw, pitch = view.yaw, view.pitch
        c = view.rect().center()
        s.drag(c, c + QPoint(80, 30), widget=view)
        if view.yaw == yaw or view.pitch == pitch:
            raise RuntimeError("the drag did not turn the box (%s, %s)" % (view.yaw, view.pitch))
        s.tick(dlg.exploded)
        if view.exploded <= 0:
            raise RuntimeError("Pulled apart did not move the parts")
        s.tick(dlg.hidden_edges)
        if view.hidden_edges:
            raise RuntimeError("Hidden edges did not switch the dashed edges off")
        s.click(dlg.lid_slider)
        QTest.keyClick(dlg.lid_slider, Qt.Key_End)
        s.settle()
        if view.lid_out <= 0:
            raise RuntimeError("the slider did not slide the lid out")
        from PySide6.QtWidgets import QDialogButtonBox
        QTest.mouseClick(dlg.findChild(QDialogButtonBox).button(QDialogButtonBox.Ok), Qt.LeftButton)
    s.expect_dialog("finger box with dividers", box_with_dividers)
    s.step("Generators → Finger-joint box with dividers across 1 and along 1 and a sliding lid (beta), 3D tab: "
           "turned, pulled apart, hidden edges off, lid slid out",
           lambda: s.trigger(w.act_generators["finger_box"], via="menu"),
           check=lambda: (any(e.name.startswith(tr_("Divider across")) for e in w.elements)
                          and any(e.name.startswith(tr_("Divider along")) for e in w.elements)
                          and any(e.name == tr_("Upper rail") for e in w.elements),
                          "%s" % sorted({e.name for e in w.elements})))
    s.trigger(w.act_undo)

    # a box too big for one sheet: in the element list one group with a group for each sheet; a sheet's row
    # selects that sheet alone, Space unticks it; a click on the bed takes the whole box, Ungroup one level
    def big_box(dlg):
        for key, value in (("width", 280), ("depth", 190), ("height", 60), ("dividers_across", 1)):
            s.type_number(dlg.widgets[key], value)
        s.settle(6, 0.05)
        from PySide6.QtWidgets import QDialogButtonBox
        QTest.mouseClick(dlg.findChild(QDialogButtonBox).button(QDialogButtonBox.Ok), Qt.LeftButton)
    lst = w.element_list
    s.expect_dialog("big finger box", big_box)
    s.step("Generators → Finger-joint box 280 x 190 x 60 with a divider (several sheets: a group for each sheet "
           "and each part with slots in the element list)", lambda: s.trigger(w.act_generators["finger_box"], via="button"), undo=False,
           check=lambda: (lst.topLevelItemCount() == 1 and lst.topLevelItem(0).childCount() >= 2,
                          "%d rows, %s" % (lst.topLevelItemCount(), [lst.topLevelItem(i).text()
                                                                    for i in range(lst.topLevelItemCount())])))

    def sheet_row(n):
        return lst.topLevelItem(0).child(n - 1)

    def click_row(item):
        lst.scrollToItem(item)                   # scrolled to it first, as one would
        s.settle()
        QTest.mouseClick(lst.viewport(), Qt.LeftButton, Qt.NoModifier, lst.visualItemRect(item).center())
        s.settle()

    def sheet2():
        return [w.elements[n] for n in lst.members(lst.group_of(sheet_row(2)))]
    s.covered_widgets.add("element list groups")
    s.step("element list: click the row of Sheet 2 (that sheet alone is selected)",
           lambda: click_row(sheet_row(2)), change=False,
           check=lambda: ({id(e) for e in w._selection()} == {id(e) for e in sheet2()},
                          "%d selected, sheet 2 has %d" % (len(w._selection()), len(sheet2()))))
    def first_shape(node):                       # the first shape's row inside a group's row
        while lst.row(node) < 0:
            lst.expandItem(node)
            node = node.child(0)
        return node

    def a_part():                                # the row of a part made of several shapes (a group)
        box = lst.topLevelItem(0)
        for k in range(box.childCount()):
            sheet = box.child(k)
            for i in range(sheet.childCount()):
                if lst.row(sheet.child(i)) < 0:
                    lst.expandItem(sheet)
                    return sheet.child(i)
        return None
    s.step("element list: click the row of a part with slots (that part is selected)",
           lambda: (a_part(), s.settle(), click_row(a_part())), change=False,
           check=lambda: (a_part() is not None and {id(e) for e in w._selection()} ==
                          {id(w.elements[n]) for n in lst.members(lst.group_of(a_part()))},
                          "%d selected, part %s" % (len(w._selection()),
                                                   a_part().text() if a_part() is not None else None)))
    s.step("element list: click a shape's row (that shape alone is selected)",
           lambda: click_row(first_shape(sheet_row(1))), change=False,
           check=lambda: (w._selection() == [w.elements[lst.row(first_shape(sheet_row(1)))]],
                          "%d selected" % len(w._selection())))
    s.step("element list: click the row of Sheet 2 again", lambda: click_row(sheet_row(2)), change=False,
           check=lambda: ({id(e) for e in w._selection()} == {id(e) for e in sheet2()},
                          "%d selected, sheet 2 has %d" % (len(w._selection()), len(sheet2()))))
    s.step("element list: Space ticks Sheet 2 (in the job; sheets 2 and on start unticked)",
           lambda: (QTest.keyClick(lst, Qt.Key_Space), s.settle()),
           check=lambda: (all(e.visible for e in sheet2()) and not all(e.visible for e in w.elements),
                          "%s" % [e.visible for e in w.elements]))
    def next_sheet_and_simulate():                       # (sheet 2 was ticked by the step above)
        click_row(sheet_row(1))
        QTest.keyClick(lst, Qt.Key_Space)                # sheet 1 cut: out of the job
        s.settle()
        s.trigger(w.act_simulate, via="key")
        s.settle(6, 0.05)

    def simulating():
        sim = getattr(w, "_simulation", None)
        try:
            shown = sim is not None and sim.isVisible()
        except RuntimeError:
            shown = False
        return (shown and all(e.visible for e in sheet2()) and not any(
            e.visible for e in w.elements if e not in sheet2()),
            "simulation shown %s, %d of %d in the job (sheet 2: %d), status '%s'" % (
                shown, sum(e.visible for e in w.elements), len(w.elements), len(sheet2()),
                w.statusBar().currentMessage()))
    s.step("element list: Space unticks Sheet 1 (Sheet 2 ticked above), Laser → Simulate (Ctrl+Shift+J): sheet 2 "
           "is simulated", next_sheet_and_simulate, check=simulating)
    try:
        w._simulation.close()
    except (AttributeError, RuntimeError):
        pass
    s.settle()
    corner = tuple(v * 25.4 - 4.0 for v in config.bed_size_inches(w.values))
    s.step("click the empty bed, then the box (the whole box is selected)",
           lambda: (s.click_bed(*corner), s.click_bed(*s.element_at(w.elements[0]))), change=False,
           check=lambda: (len(w._selection()) == len(w.elements), "%d of %d selected"
                          % (len(w._selection()), len(w.elements))))
    s.step("Edit → Ungroup (Ctrl+Shift+G): the sheets stay groups", lambda: s.trigger(w.act_ungroup, via="key"),
           check=lambda: (lst.topLevelItemCount() >= 2 and
                          all(lst.topLevelItem(i).text().split(" (")[0] in {tr_("Sheet %d") % n for n in range(1, 20)}
                              for i in range(lst.topLevelItemCount())),
                          "%d rows: %s" % (lst.topLevelItemCount(), [lst.topLevelItem(i).text()
                                                                    for i in range(lst.topLevelItemCount())])))
    s.trigger(w.act_undo)


def part_files_and_help(s):
    w = s.w
    s.files.append(os.path.join(FIX, "shapes.svg"))
    n = len(w.elements)
    s.step("File → Add design… (SVG)", lambda: s.trigger(w.act_add, via="menu"), undo=True,
           check=lambda: (len(w.elements) == n + 1, "%d elements" % len(w.elements)))
    s.step("File → Reload design (F5)", lambda: s.trigger(w.act_reload, via="key"), change=None, undo=False)
    # a picture: Add design (PNG), click it, Trace in its options bar, threshold moved, Trace
    from PIL import Image as _PImage, ImageDraw as _PDraw
    png = os.path.join(s.tmp, "logo.png")
    im = _PImage.new("L", (300, 200), 255)
    _PDraw.Draw(im).ellipse((40, 30, 200, 170), fill=0)
    _PDraw.Draw(im).rectangle((90, 80, 150, 120), fill=255)
    im.save(png, dpi=(150, 150))
    s.files.append(png)
    s.expect_dialog("picture size", lambda d: d.accept())
    n_pic = len(w.elements)
    s.step("File → Add design… (Ctrl+Shift+O, PNG picture)", lambda: s.trigger(w.act_add, via="key"), undo=True,
           check=lambda: (len(w.elements) == n_pic + 1 and w.elements[-1].design.raster.image is not None,
                          "%d elements" % len(w.elements)))
    picture = w.elements[-1]
    s.step("click the picture", lambda: s.click_bed(*s.element_at(picture)), change=False,
           check=lambda: (w.selected is picture, "selected %s" % (w.selected.name if w.selected else None)))

    def trace_it(dlg):
        from PySide6.QtWidgets import QDialogButtonBox
        edit = dlg.threshold_value.lineEdit()           # typed without Enter (Enter would press Trace)
        s.click(edit)
        QTest.keyClick(edit, Qt.Key_A, Qt.ControlModifier)
        QTest.keyClicks(edit, "140")
        s.settle(6, 0.05)
        if dlg.threshold.value() != 140:
            raise RuntimeError("threshold %s" % dlg.threshold.value())
        s.click(dlg.findChild(QDialogButtonBox).button(QDialogButtonBox.Ok))
    s.expect_dialog("trace picture", trace_it)
    s.step("picture options bar: Trace picture, threshold 140, Trace", lambda: s.trigger(w.act_trace_image),
           check=lambda: (w.elements[-1] is not picture and w.elements[-1].shape is not None
                          and w.elements[-1].shape.kind == "path" and len(w.elements[-1].shape.subpaths) == 2
                          and w.elements[-1].shape.closed,
                          "last %s" % (w.elements[-1].shape.kind if w.elements[-1].shape else w.elements[-1].name)))
    # Cut out of a picture: the tool from the strip, a rectangle dragged over the picture with the mouse
    pic_e = picture
    xmin, xmax, ymin, ymax = pic_e.bounds
    left, right = xmin * MM, xmax * MM
    top, bottom = -ymax * MM, -ymin * MM
    if w.job_settings().home_upper_right:
        left, right = w.preview.bed_w_mm - right, w.preview.bed_w_mm - left
    a = (left + (right - left) * 0.2, top + (bottom - top) * 0.15)
    b = (left + (right - left) * 0.7, top + (bottom - top) * 0.85)
    s.step("tool strip: Cut out of a picture", lambda: s.click(next(bt for bt in w.findChildren(QToolButton)
                                                                     if bt.defaultAction() is w.tool_actions["crop"])),
           change=False, undo=False, check=lambda: (w.preview.tool == "crop", w.preview.tool))
    s.step("drag a rectangle over the picture (Alt: no snapping): the piece inside stays",
           lambda: s.drag(a, b, mods=Qt.AltModifier),
           check=lambda: (w.selected is not None and w.selected.design.raster.image is not None
                          and w.selected is not pic_e and abs(w.selected.size[0] * MM - (b[0] - a[0])) < 0.5,
                          "selected %s, width %s" % (w.selected.name if w.selected else None,
                                                     w.selected.size[0] * MM if w.selected else None)))
    s.trigger(w.tool_actions["select"])
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
           check=lambda: (len(w.elements) == 1, "%d elements, files left %s, status %r"
                          % (len(w.elements), s.files, w.statusBar().currentMessage())))
    s.expect_dialog("settings", lambda d: d.accept())
    s.step("Settings → Settings… (opens, OK)", lambda: s.trigger(w.act_settings, via="menu"), change=False, undo=False)
    s.step("Help → User guide (F1)", lambda: s.trigger(w.act_guide, via="key"), change=False,
           check=lambda: (any("guide" in u for u in s.opened_urls), s.opened_urls))

    # Help → Keyboard shortcuts: the window, a search typed into it, Close
    def shortcuts_window():
        s.trigger(w.act_shortcuts, via="menu")
        dlg = getattr(w, "_shortcuts", None)
        if dlg is None or not dlg.isVisible():
            raise RuntimeError("no shortcuts window")
        s.click(dlg.filter)
        QTest.keyClicks(dlg.filter, "F9")
        s.settle()
        found = dlg.rows()
        from PySide6.QtWidgets import QDialogButtonBox
        s.click(dlg.findChild(QDialogButtonBox).button(QDialogButtonBox.Close))
        try:
            closed = not dlg.isVisible()
        except RuntimeError:
            closed = True                          # closed and deleted
        shown.update(rows=found, closed=closed)
    shown = {}
    s.step("Help → Keyboard shortcuts (search F9, Close)", shortcuts_window, change=False,
           check=lambda: (any(k == "F9" for _sec, _c, k in shown.get("rows", [])) and len(shown.get("rows", [])) < 4
                          and shown.get("closed"), "rows %s, closed %s" % (shown.get("rows"), shown.get("closed"))))
    # laser profiles: the Lasers button, New, a name typed in, Use; back with the list of the Laser tab; Delete
    from kerfly.gui.profiles_dialog import ProfilesDialog
    first_laser = w.profiles.current
    first_board = w.values.get("board_name")

    def add_and_use(dlg):
        if not isinstance(dlg, ProfilesDialog):
            raise RuntimeError("not the lasers window: %s" % dlg)
        s.click(dlg.buttons["new"])
        editor = dlg.name_edit                             # New: the name field, its text selected
        if editor.selectedText() != editor.text():
            raise RuntimeError("New did not select the name in the name field")
        s.click(editor)
        QTest.keyClick(editor, Qt.Key_A, Qt.ControlModifier)
        QTest.keyClicks(editor, "Laptop laser")
        QTest.keyClick(editor, Qt.Key_Return)
        s.settle()
        s.click(dlg.buttons["use"])
        s.click(dlg.findChild(QDialogButtonBox).button(QDialogButtonBox.Cancel))
    from PySide6.QtWidgets import QDialogButtonBox

    s.expect_dialog("lasers: New, name, Use", add_and_use)
    s.step("Lasers (Laser tab) → New, type a name, Use: its settings in the window",
           lambda: s.trigger(w.act_profiles),
           change=False, undo=False,
           check=lambda: (w.profiles.current == "Laptop laser" and w.values.get("board_name") == "LASER-M2"
                          and w.profile_box.currentText() == "Laptop laser",
                          "%s, %s" % (w.profiles.current, w.values.get("board_name"))))
    s.tab(1)
    s.step("Laser tab: the laser list back to the first laser", lambda: s.pick(w.profile_box,
                                                                                 index=w.profile_box.findText(first_laser)),
           change=False, undo=False,
           check=lambda: (w.profiles.current == first_laser and w.values.get("board_name") == first_board,
                          "%s, %s" % (w.profiles.current, w.values.get("board_name"))))

    def delete_laptop(dlg):
        dlg.list.setCurrentRow(w.profiles.names().index("Laptop laser"))
        s.settle()

        def yes():                               # the question opens inside this window: answered by a timer
            box = QApplication.activeModalWidget()
            if isinstance(box, QMessageBox):
                s.click_dialog_button(box, QMessageBox.Yes)
            else:
                QTimer.singleShot(100, yes)
        QTimer.singleShot(100, yes)
        s.click(dlg.buttons["delete"])
        s.click(dlg.findChild(QDialogButtonBox).button(QDialogButtonBox.Cancel))     # (a deletion is at once)
    s.expect_dialog("lasers: Delete", delete_laptop)
    s.step("Laser tab: manage lasers → Delete the new one", lambda: s.click(w.btn_profiles), change=False,
           undo=False, check=lambda: ("Laptop laser" not in w.profiles.names() and w.profiles.current == first_laser,
                                      "%s" % w.profiles.names()))
    s.tab(0)

    from kerfly.gui import desktop_entry
    if desktop_entry.applies():
        s.expect_dialog("added to the applications menu", lambda d: s.click_dialog_button(d, QMessageBox.Ok))
        entry = os.path.join(os.environ["XDG_DATA_HOME"], "applications", "kerfly.desktop")
        s.step("Settings → Add Kerfly to the applications menu… (Linux AppImage)",
               lambda: s.trigger(w.act_desktop_entry, via="menu"), change=False,
               check=lambda: (os.path.isfile(entry) and desktop_entry.installed_for() == desktop_entry.appimage_path(),
                              "entry %s" % desktop_entry.installed_for()))
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
        s.trigger(w.act_check_updates, via="menu")           # Help → Check for updates (no toolbar button)
        s.wait(lambda: w.update_bar.isVisible(), 10)
    s.step("Updates (toolbar): a newer version, the bar above the bed", check_updates, change=False,
           check=lambda: (w.update_bar.isVisible() and "99.0" in w.update_bar.text.text(), w.update_bar.text.text()))
    s.step("update bar: See the release", lambda: s.click(w.update_bar.open_button), change=False,
           check=lambda: (s.opened_urls[-1:] == ["https://github.com/cyryllo/Kerfly/releases/tag/v99.0"],
                          s.opened_urls[-1:]))
    s.step("update bar: Skip this version", lambda: s.click(w.update_bar.skip_button), change=False,
           check=lambda: (not w.update_bar.isVisible() and w.values.get("update_skip") == "99.0",
                          w.values.get("update_skip")))
    def about_answer(d):
        # its own window (docs/ui-mockups/About): Report a problem and Check for updates beside Close
        if not (d.report_button.isVisible() and d.updates_button.isVisible()):
            raise RuntimeError("About: no Report a problem / Check for updates buttons")
        d.accept()
    s.expect_dialog("about", about_answer)
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
    for part in (session, part_edit, part_layers, part_view_and_laser, part_m3_board, part_grbl, part_generators,
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
    code = main()
    sys.stdout.flush()
    sys.stderr.flush()
    # out at once: Python's own clean-up of the many windows and dialogs of the session crashed at the end
    # (after the result, in Qt's code), which hid the exit code
    os._exit(code)
