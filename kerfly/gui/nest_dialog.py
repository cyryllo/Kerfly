"""
Arrange → Nest on the bed: how the parts are laid out (by their rectangles,
fast; or by their real outlines, parts in each other's gaps and holes, with
the sparrow library), the gap between them, whether they may be turned and,
by outlines, how long to search. A sheet is always the laser's bed.

Copyright (C) 2026 Kerfly contributors
Licensed under the GNU General Public License v3 or later. See LICENSE.
"""
import time

from PySide6.QtCore import QThread, QTimer, Signal
from PySide6.QtWidgets import QCheckBox, QDialog, QDoubleSpinBox, QProgressDialog, QSpinBox

from kerfly.core.nesting import outlines_available
from kerfly.gui import theme, widgets
from kerfly.i18n import _

METHODS = ("rectangles", "outlines")


class NestDialog(QDialog):
    def __init__(self, values, bed_mm, count, parent=None):
        super().__init__(parent)
        self.setWindowTitle(_("Nest on the bed"))
        text = widgets.hint(_("The %(n)d selected parts (a group as one part) are laid out on the laser's bed "
                        "(%(w).0f × %(h).0f mm). What does not fit goes on a next sheet: each sheet is a group "
                        "in the element list, sheets 2 and on unticked.")
                            % {"n": count, "w": bed_mm[0], "h": bed_mm[1]})
        can_outline = outlines_available()
        self.method = widgets.Segmented(
            [("rectangles", _("Rectangles"), _("By the parts' rectangles: fast")),
             ("outlines", _("Outlines"), _("By the parts' real outlines: parts go into each other's gaps and the "
                                           "holes cut in them; takes the search time for each sheet"))],
            values.get("method", "rectangles") if can_outline else "rectangles")
        method_tip = _("How the parts are laid out: by their rectangles (fast) or by their real outlines (parts "
                       "in each other's gaps and holes)")
        if not can_outline:
            self.method.buttons["outlines"].setEnabled(False)
            self.method.buttons["outlines"].setToolTip(_("Needs the spyrrow and pyclipper libraries (installed "
                                                         "with Kerfly)"))
        self.gap = QDoubleSpinBox()
        self.gap.setRange(0.0, 50.0)
        self.gap.setDecimals(1)
        self.gap.setSingleStep(0.5)
        self.gap.setSuffix(" mm")
        self.gap.setValue(float(values.get("gap", 2.0)))
        gap_tip = _("Space left between the parts (the laser's kerf and some room)")
        self.gap.setToolTip(gap_tip)
        self.turn = QCheckBox()
        self.turn.setChecked(bool(values.get("turn", True)))
        turn_tip = _("Parts may be turned by 90 degrees where that fits better (off: e.g. for wood grain)")
        self.turn.setToolTip(turn_tip)
        self.seconds = QSpinBox()
        self.seconds.setRange(2, 600)
        self.seconds.setSuffix(" s")
        self.seconds.setValue(int(values.get("seconds", 10)))
        seconds_tip = _("By outlines: how long to look for a tighter layout, for each sheet (longer: tighter)")
        self.seconds.setToolTip(seconds_tip)
        # the dialog pattern: the explanation, the fields, the footer with the named action
        section = widgets.Section()
        section.add_row("squares", _("Method"), method_tip, self.method, beta=True)
        section.add_row("box-padding", _("Gap"), gap_tip, self.gap)
        section.add_row("rotate-clockwise-2", _("Turn by 90°"), turn_tip, self.turn)
        self.seconds_field = section.add_row("clock", _("Search time"), seconds_tip, self.seconds)
        self.method.toggled.connect(self._method_changed)
        self._method_changed(self.method.current())
        body = widgets.DialogBody()
        body.add(text)
        body.add(section)
        body.layout().addStretch(1)
        footer = widgets.DialogFooter(_("Nest"))
        footer.connect(self)
        widgets.dialog_layout(self, body, footer)
        self.setMinimumWidth(theme.DIALOG_SMALL)

    def _method_changed(self, method):
        self.seconds.setEnabled(method == "outlines")

    def values(self):
        return {"method": self.method.current(), "gap": self.gap.value(), "turn": self.turn.isChecked(),
                "seconds": self.seconds.value()}


class NestWorker(QThread):
    """Plans a nesting by outlines in a thread (the window stays alive); the elements are moved afterwards, in
    the window's thread. done(parts, plan, error)."""
    done = Signal(object, object, str)
    sheet = Signal(int)

    def __init__(self, elements, bed_w, bed_h, gap, turn, seconds, parent=None):
        super().__init__(parent)
        self.args = (elements, bed_w, bed_h, gap, turn, seconds)
        self.stopped = False

    def run(self):
        from kerfly.core.nesting import plan_nest_outlines
        try:
            parts, plan = plan_nest_outlines(*self.args, progress=self.sheet.emit, stop=lambda: self.stopped)
            self.done.emit(parts, plan, "")
        except Exception as e:                       # (the library's own errors included)
            self.done.emit(None, None, str(e))


def plan_with_progress(parent, elements, bed_w, bed_h, gap, turn, seconds):
    """Runs a NestWorker with a progress window (the search time of the sheet running; Cancel: nothing moves,
    after the sheet being searched). Returns (parts, plan) or None (cancelled), raises RuntimeError on an
    error."""
    worker = NestWorker(elements, bed_w, bed_h, gap, turn, seconds, parent)
    box = QProgressDialog(_("Looking for a tight layout…"), _("Cancel"), 0, int(seconds) * 10, parent)
    box.setWindowTitle(_("Nest on the bed"))
    box.setMinimumDuration(0)
    box.setAutoClose(False)
    box.setAutoReset(False)
    state = {"start": time.monotonic(), "sheet": 1, "result": None}

    def on_sheet(n):
        state["start"], state["sheet"] = time.monotonic(), n
        box.setLabelText(_("Looking for a tight layout: sheet %d…") % n)

    def tick():
        box.setValue(min(box.maximum(), int((time.monotonic() - state["start"]) * 10)))

    def finished(parts, plan, error):
        state["result"] = (parts, plan, error)
        box.hide()                                   # (close() would count as Cancel)
    timer = QTimer(box)
    timer.timeout.connect(tick)
    timer.start(100)
    worker.sheet.connect(on_sheet)
    worker.done.connect(finished)
    box.canceled.connect(lambda: setattr(worker, "stopped", True))
    worker.start()
    box.exec()
    if state["result"] is None:                      # cancelled: wait for the sheet being searched
        box2 = QProgressDialog(_("Stopping after the sheet being searched…"), None, 0, 0, parent)
        box2.setWindowTitle(_("Nest on the bed"))
        box2.setMinimumDuration(0)
        worker.done.connect(lambda *_a: box2.hide())
        if worker.isRunning():
            box2.exec()
    worker.wait()
    timer.stop()
    parts, plan, error = state["result"] or (None, None, "")
    if error:
        raise RuntimeError(error)
    if plan is None or worker.stopped:
        return None
    return parts, plan
