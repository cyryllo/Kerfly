"""
Kerfly main window.

Copyright (C) 2026 Kerfly contributors
Licensed under the GNU General Public License v3 or later. See LICENSE.
"""
import os

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (QApplication, QCheckBox, QDockWidget, QDoubleSpinBox, QFileDialog,
                               QGridLayout, QGroupBox, QHBoxLayout, QInputDialog, QLabel,
                               QMainWindow, QMessageBox, QProgressBar, QPushButton, QScrollArea,
                               QSpinBox, QToolBar, QVBoxLayout, QWidget)

from kerfly import __version__
from kerfly.core import config, egvfile, job, loaders
from kerfly.core.config import is_true
from kerfly.core.design import Design
from kerfly.core.estimate import estimate_times, format_time
from kerfly.core.laser import (LaserController, LaserError, clamp_head_position, corner_offset,
                               temporary_offset_target)
from kerfly.gui import icons
from kerfly.gui.preview import PreviewView
from kerfly.gui.settings_dialog import RASTER_KEYS, RELOAD_KEYS, SettingsDialog
from kerfly.gui.worker import EgvSendWorker, JobWorker, RasterPrepareWorker

DESIGN_FILTERS = ("Design files (*.svg *.dxf *.ngc *.gcode *.nc *.g *.tap);;"
                  "SVG files (*.svg);;DXF files (*.dxf);;"
                  "G-code files (*.ngc *.gcode *.nc *.g *.tap);;All files (*)")

# (label, include key, speed key, passes key, power key, operation)
OPERATIONS = [
    ("Raster engrave", "include_Reng", "Reng_feed", "Reng_passes", "Reng_power", job.RASTER_ENG),
    ("Vector engrave", "include_Veng", "Veng_feed", "Veng_passes", "Veng_power", job.VECTOR_ENG),
    ("Vector cut", "include_Vcut", "Vcut_feed", "Vcut_passes", "Vcut_power", job.VECTOR_CUT),
    ("G-code", "include_Gcde", None, "Gcde_passes", "Gcode_power", job.GCODE_CUT),
]


def _num_text(v):
    return ("%.4f" % v).rstrip("0").rstrip(".")


class MainWindow(QMainWindow):
    def __init__(self, values):
        super().__init__()
        self.values = values
        self.design = Design()
        self.design_file = ""
        self.laser = LaserController()
        self.head = (0.0, 0.0)          # design origin at the laser head, inches (y <= 0)
        self.head_offset = (0, 0)       # temporary head offset from the origin, mils
        self.worker = None
        self._unit_widgets = []         # (spinbox, kind, key, sign) to update when units change

        self.setWindowTitle("Kerfly %s" % __version__)
        self.resize(1200, 780)
        self.preview = PreviewView()
        self.setCentralWidget(self.preview)
        self._build_actions()
        self._build_panel()
        self._build_status()
        self._update_power_visibility()
        self._update_laser_state()
        self.refresh_preview(fit=True)

    # ------------------------------------------------------------ UI setup
    def _action(self, text, slot, shortcut=None, tip=None):
        act = QAction(text, self)
        act.triggered.connect(slot)
        if shortcut:
            act.setShortcut(QKeySequence(shortcut))
        if tip:
            act.setStatusTip(tip)
        return act

    def _build_actions(self):
        self.act_open = self._action("&Open design\u2026", self.open_design, "Ctrl+O")
        self.act_reload = self._action("&Reload design", self.reload_design, "F5")
        self.act_save_egv = self._action("Save &EGV file\u2026", self.save_egv, "Ctrl+E",
                                         "Write the selected operations to an EGV file")
        self.act_send_egv = self._action("Send EGV file to laser\u2026", self.send_egv_file, None,
                                         "Send an existing EGV file to the laser")
        self.act_save_settings = self._action("Save settings as default", self.save_settings, "Ctrl+S")
        self.act_goto = self._action("&Go to X/Y position", self.goto_position, "Ctrl+G")
        self.act_corners = {}
        for key, text, sc in (("UL", "Upper left", "Ctrl+7"), ("UR", "Upper right", "Ctrl+9"),
                              ("CC", "Centre", "Ctrl+5"), ("LL", "Lower left", "Ctrl+1"),
                              ("LR", "Lower right", "Ctrl+3")):
            self.act_corners[key] = self._action(text, lambda _=False, k=key: self.move_to_corner(k), sc)
        self.act_calc_time = self._action("Calculate raster time", self.calculate_raster_time)
        self.act_quit = self._action("&Quit", self.close, "Ctrl+Q")
        self.act_connect = self._action("&Initialize laser", self.connect_laser, "Ctrl+I")
        self.act_release = self._action("Release USB", self.release_laser)
        self.act_home = self._action("&Home", self.home, "Home")
        self.act_unlock = self._action("&Unlock rail", self.unlock)
        self.act_unfreeze = self._action("Un&freeze laser", self.unfreeze)
        self.act_fit = self._action("&Fit to window", lambda: self.preview.fit_all(), "Ctrl+0")
        self.act_settings = self._action("&Settings\u2026", self.edit_settings, "Ctrl+,")
        self.act_about = self._action("&About Kerfly", self.about)

        mb = self.menuBar()
        m = mb.addMenu("&File")
        for a in (self.act_open, self.act_reload, None, self.act_save_egv, self.act_send_egv, None,
                  self.act_save_settings, None, self.act_quit):
            m.addSeparator() if a is None else m.addAction(a)
        m = mb.addMenu("&Laser")
        for a in (self.act_connect, self.act_release, None, self.act_home, self.act_unlock,
                  self.act_unfreeze, None, self.act_goto):
            m.addSeparator() if a is None else m.addAction(a)
        sub = m.addMenu("Move head to design")
        for a in self.act_corners.values():
            sub.addAction(a)
        m = mb.addMenu("&View")
        m.addAction(self.act_fit)
        m = mb.addMenu("&Settings")
        m.addAction(self.act_settings)
        m = mb.addMenu("&Help")
        m.addAction(self.act_about)

        tb = QToolBar("Main")
        tb.setMovable(False)
        tb.setToolButtonStyle(Qt.ToolButtonTextOnly)
        for a in (self.act_open, self.act_reload, None, self.act_connect, self.act_home,
                  self.act_unlock, None, self.act_fit, self.act_settings):
            tb.addSeparator() if a is None else tb.addAction(a)
        self.addToolBar(tb)

    def _spin(self, key, kind, lo, hi, decimals=1):
        if kind == "int":
            w = QSpinBox()
            w.setRange(int(lo), int(hi))
            w.setValue(int(float(self.values.get(key) or 1)))
            w.valueChanged.connect(lambda v: self._set_value(key, str(v)))
        else:
            w = QDoubleSpinBox()
            w.setRange(lo, hi)
            w.setDecimals(decimals)
            if kind == "power":
                w.setSuffix(" %")
                w.setValue(float(self.values.get(key) or 0) * 100.0)
                w.valueChanged.connect(lambda v: self._set_value(key, _num_text(v / 100.0)))
            else:
                w.setValue(float(self.values.get(key) or 0))
                w.valueChanged.connect(lambda v: self._set_value(key, _num_text(v)))
                self._unit_widgets.append((w, kind, key, 1.0))
        # compact columns in the operations table
        widths = {"int": 58, "power": 72, "speed": 112}
        if kind in widths:
            w.setFixedWidth(widths[kind])
        return w

    def _build_panel(self):
        panel = QWidget()
        layout = QVBoxLayout(panel)

        # --- design info
        box = QGroupBox("Design")
        v = QVBoxLayout(box)
        self.design_label = QLabel("No design loaded")
        self.design_label.setWordWrap(True)
        v.addWidget(self.design_label)
        row = QHBoxLayout()
        b = QPushButton("Open\u2026")
        b.clicked.connect(self.open_design)
        row.addWidget(b)
        b = QPushButton("Reload")
        b.clicked.connect(self.reload_design)
        row.addWidget(b)
        v.addLayout(row)
        layout.addWidget(box)

        # --- laser
        box = QGroupBox("Laser")
        v = QVBoxLayout(box)
        self.laser_label = QLabel()
        v.addWidget(self.laser_label)
        row = QHBoxLayout()
        self.btn_connect = QPushButton("Initialize")
        self.btn_connect.clicked.connect(self.connect_laser)
        row.addWidget(self.btn_connect)
        b = QPushButton("Home")
        b.clicked.connect(self.home)
        row.addWidget(b)
        b = QPushButton("Unlock")
        b.clicked.connect(self.unlock)
        row.addWidget(b)
        v.addLayout(row)

        # jog pad: arrows move the design origin; corners/centre move the head
        # to that point of the design (the design stays where it is)
        grid = QGridLayout()
        grid.setSpacing(4)
        arrows = {(0, 1): ("up", 0, 1, "Ctrl+Up"), (-1, 0): ("left", 1, 0, "Ctrl+Left"),
                  (1, 0): ("right", 1, 2, "Ctrl+Right"), (0, -1): ("down", 2, 1, "Ctrl+Down")}
        for d, (name, r, c, sc) in arrows.items():
            b = QPushButton()
            b.setIcon(icons.arrow_icon(name))
            b.setIconSize(QSize(34, 34))
            b.setFixedSize(64, 56)
            b.setToolTip("Move the head and design %s by one step (%s)" % (name, sc))
            b.clicked.connect(lambda _=False, d=d: self.jog(*d))
            grid.addWidget(b, r, c)
            act = QAction(self)
            act.setShortcut(QKeySequence(sc))
            act.triggered.connect(lambda _=False, d=d: self.jog(*d))
            self.addAction(act)
        self.corner_buttons = []
        corners = (("UL", 0, 0, "upper left corner", "Ctrl+7"), ("UR", 0, 2, "upper right corner", "Ctrl+9"),
                   ("CC", 1, 1, "centre", "Ctrl+5"), ("LL", 2, 0, "lower left corner", "Ctrl+1"),
                   ("LR", 2, 2, "lower right corner", "Ctrl+3"))
        for key, r, c, tip, sc in corners:
            b = QPushButton()
            b.setIcon(icons.centre_icon() if key == "CC" else icons.corner_icon(key))
            b.setIconSize(QSize(34, 34))
            b.setFixedSize(64, 56)
            b.setToolTip("Move the head to the %s of the design (%s).\n"
                         "The design does not move." % (tip, sc))
            b.clicked.connect(lambda _=False, k=key: self.move_to_corner(k))
            grid.addWidget(b, r, c)
            self.corner_buttons.append(b)
        pad = QHBoxLayout()
        pad.addStretch(1)
        pad.addLayout(grid)
        pad.addStretch(1)
        v.addLayout(pad)

        self.jog_step = self._spin("jog_step", "len", 0.01, 1000, 2)
        self.jog_step.setToolTip("Distance moved by one arrow click")
        self.jog_step.setFixedWidth(110)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(QLabel("Step:"))
        row.addWidget(self.jog_step)
        row.addStretch(1)
        v.addLayout(row)
        self.head_label = QLabel()
        self.head_label.setAlignment(Qt.AlignHCenter)
        v.addWidget(self.head_label)

        # go to an absolute position (from home)
        row = QHBoxLayout()
        row.addWidget(QLabel("Go to X"))
        self.goto_x = QDoubleSpinBox()
        self.goto_y = QDoubleSpinBox()
        for w, key, sign in ((self.goto_x, "gotoX", 1.0), (self.goto_y, "gotoY", -1.0)):
            w.setRange(0.0, 10000.0)
            w.setDecimals(2)
            w.setFixedWidth(92)
            self._unit_widgets.append((w, "len", key, sign))
        try:
            self.goto_x.setValue(float(self.values.get("gotoX") or 0))
            self.goto_y.setValue(max(0.0, -float(self.values.get("gotoY") or 0)))
        except ValueError:
            pass
        self.goto_x.valueChanged.connect(lambda v: self._set_value("gotoX", _num_text(v)))
        # gotoY is stored like K40 Whisperer (up is positive); shown as distance down
        self.goto_y.valueChanged.connect(lambda v: self._set_value("gotoY", _num_text(-v)))
        self.goto_y.setToolTip("Distance down from home")
        row.addWidget(self.goto_x)
        row.addSpacing(6)
        row.addWidget(QLabel("Y"))
        row.addWidget(self.goto_y)
        row.addStretch(1)
        self.btn_goto = QPushButton("Go")
        self.btn_goto.setToolTip("Home the head, then move to X/Y (Ctrl+G)")
        self.btn_goto.clicked.connect(self.goto_position)
        row.addWidget(self.btn_goto)
        v.addLayout(row)

        # test fire (M3 boards)
        self.test_fire_row = QWidget()
        row = QHBoxLayout(self.test_fire_row)
        row.setContentsMargins(0, 0, 0, 0)
        self.btn_test_fire = QPushButton("Test fire")
        self.btn_test_fire.setToolTip("Fire the laser briefly (M3 boards)")
        self.btn_test_fire.clicked.connect(self.test_fire)
        row.addWidget(self.btn_test_fire)
        row.addWidget(self._spin("test_power", "power", 0, 100, 0))
        t = self._spin("test_time", "int", 0, 1000)
        t.setSuffix(" ms")
        t.setFixedWidth(80)
        row.addWidget(t)
        row.addStretch(1)
        v.addWidget(self.test_fire_row)
        layout.addWidget(box)

        # --- operations
        box = QGroupBox("Operations")
        g = QGridLayout(box)
        self.speed_header = QLabel()
        for col, text in enumerate(("", None, "Passes", "Power", "Time")):
            if text is None:
                g.addWidget(self.speed_header, 0, col)
            elif text:
                lbl = QLabel(text)
                g.addWidget(lbl, 0, col)
                if text == "Power":
                    self.power_header = lbl
        self.power_widgets = {}
        self.time_labels = {}
        self.include_checks = {}
        self.op_rows = {}          # operation -> widgets of its row
        for row, (label, inc, feed, passes, power, op) in enumerate(OPERATIONS, start=1):
            cb = QCheckBox(label)
            cb.setChecked(is_true(self.values.get(inc, "1")))
            cb.toggled.connect(lambda on, k=inc: (self._set_value(k, "1" if on else "0"),
                                                  self.refresh_preview()))
            self.include_checks[op] = cb
            g.addWidget(cb, row, 0)
            widgets = [cb]
            if feed:
                widgets.append(self._spin(feed, "speed", 0.1, 10000))
                widgets[-1].setToolTip("Speed")
                g.addWidget(widgets[-1], row, 1)
            elif op == job.GCODE_CUT:
                cb.setToolTip("Paths from a G-code file; speeds come from the file (F words)")
            widgets.append(self._spin(passes, "int", 1, 100))
            g.addWidget(widgets[-1], row, 2)
            pw = self._spin(power, "power", 0, 100, 0)
            g.addWidget(pw, row, 3)
            self.power_widgets[op] = pw
            tl = QLabel("")
            tl.setMinimumWidth(52)
            g.addWidget(tl, row, 4)
            self.time_labels[op] = tl
            widgets.append(tl)
            self.op_rows[op] = widgets
        self.no_ops_label = QLabel("Open a design to see its operations.")
        self.no_ops_label.setStyleSheet("color:#757575;")
        g.addWidget(self.no_ops_label, len(OPERATIONS) + 1, 0, 1, 5)
        row = QHBoxLayout()
        self.total_time_label = QLabel()
        row.addWidget(self.total_time_label, 1)
        self.btn_calc_time = QPushButton("Calculate raster time")
        self.btn_calc_time.setToolTip("Prepare the raster now to estimate its engraving time")
        self.btn_calc_time.clicked.connect(self.calculate_raster_time)
        row.addWidget(self.btn_calc_time)
        g.addLayout(row, len(OPERATIONS) + 2, 0, 1, 5)
        layout.addWidget(box)

        # --- run
        box = QGroupBox("Run")
        v = QVBoxLayout(box)
        self.btn_start = QPushButton("Start selected operations")
        self.btn_start.setObjectName("start")
        self.btn_start.setMinimumHeight(40)
        self.btn_start.clicked.connect(lambda: self.start_job())
        v.addWidget(self.btn_start)
        row = QHBoxLayout()
        self.btn_trace = QPushButton("Trace boundary")
        self.btn_trace.setToolTip("Move around the outline of the design")
        self.btn_trace.clicked.connect(lambda: self.start_job(trace=True))
        row.addWidget(self.btn_trace)
        self.btn_egv = QPushButton("Save EGV\u2026")
        self.btn_egv.clicked.connect(self.save_egv)
        row.addWidget(self.btn_egv)
        v.addLayout(row)
        self.btn_stop = QPushButton("Stop")
        self.btn_stop.setObjectName("stop")
        self.btn_stop.setMinimumHeight(34)
        self.btn_stop.setEnabled(False)
        self.btn_stop.clicked.connect(self.stop_job)
        v.addWidget(self.btn_stop)
        layout.addWidget(box)
        layout.addStretch(1)

        scroll = QScrollArea()
        scroll.setWidget(panel)
        scroll.setWidgetResizable(True)
        self.panel_scroll = scroll
        dock = QDockWidget("Job", self)
        dock.setObjectName("job_dock")
        dock.setFeatures(QDockWidget.NoDockWidgetFeatures)
        dock.setWidget(scroll)
        self.addDockWidget(Qt.LeftDockWidgetArea, dock)
        self._update_unit_suffixes()

    def _build_status(self):
        self.progress = QProgressBar()
        self.progress.setMaximumWidth(220)
        self.progress.setRange(0, 0)
        self.progress.hide()
        self.statusBar().addPermanentWidget(self.progress)
        self.statusBar().showMessage("Ready")

    # ------------------------------------------------------------ state
    def _set_value(self, key, val):
        self.values[key] = val
        if key.endswith("_feed") or key.endswith("_passes") or key == "Gcde_passes":
            self._update_times()

    def _update_times(self):
        if not hasattr(self, "total_time_label"):
            return
        has = self._design_has()
        try:
            times = estimate_times(self.design, self.job_settings())
        except (ValueError, ZeroDivisionError):
            times = {}
        total, unknown = 0.0, False
        for op, label in self.time_labels.items():
            t = times.get(op)
            label.setText(format_time(t) if has[op] else "")
            if has[op] and self.include_checks[op].isChecked():
                if t is None:
                    unknown = True
                else:
                    total += t
        raster_unknown = has[job.RASTER_ENG] and times.get(job.RASTER_ENG) is None
        self.btn_calc_time.setVisible(raster_unknown)
        if any(has.values()):
            self.total_time_label.setText("Estimated total: <b>%s%s</b>"
                                          % (format_time(total), " + raster" if unknown else ""))
        else:
            self.total_time_label.setText("")

    def power_per_stage(self):
        return (self.values.get("board_name") == "LASER-M3"
                and is_true(self.values.get("show_power", "1")))

    def job_settings(self):
        return config.job_settings_from_values(self.values, power_per_stage=self.power_per_stage())

    def send_options(self):
        v = self.values
        return dict(pre_process_crc=is_true(v["pre_pr_crc"]), wait_for_laser=is_true(v["wait"]),
                    timeout_ms=float(v["t_timeout"]), n_timeouts=float(v["n_timeouts"]))

    def _design_has(self):
        d = self.design
        return {job.RASTER_ENG: d.raster.image is not None,
                job.VECTOR_ENG: bool(d.vector_engrave.ecoords),
                job.VECTOR_CUT: bool(d.vector_cut.ecoords),
                job.GCODE_CUT: bool(d.gcode.ecoords)}

    def _update_power_visibility(self):
        """Show the rows that apply to the loaded design: the G-code row only
        for G-code files, other rows greyed out when the design has no such data.
        The power column is shown only for M3 boards with power control."""
        show_power = self.power_per_stage()
        has = self._design_has()
        gcode_file = has[job.GCODE_CUT]
        self.power_header.setVisible(show_power)
        self.speed_header.setVisible(not gcode_file)
        self.test_fire_row.setVisible(self.values.get("board_name") == "LASER-M3"
                                      and is_true(self.values.get("show_test", "1")))
        for op, widgets in self.op_rows.items():
            visible = gcode_file if op == job.GCODE_CUT else not gcode_file
            for w in widgets:
                w.setVisible(visible)
                w.setEnabled(has[op])
            self.power_widgets[op].setVisible(visible and show_power)
            self.power_widgets[op].setEnabled(has[op])
        self.no_ops_label.setVisible(not any(has.values()))
        self._update_times()
        self._fit_panel_width()

    def _fit_panel_width(self):
        """Make the job panel exactly as wide as its contents need, and the
        window tall enough to show the whole panel."""
        scroll = getattr(self, "panel_scroll", None)
        if scroll is None:
            return
        panel = scroll.widget()
        panel.adjustSize()
        width = panel.sizeHint().width() + scroll.verticalScrollBar().sizeHint().width() + 4
        scroll.setMinimumWidth(max(300, width))
        if self.isVisible():
            QTimer.singleShot(0, self._fit_window_height)

    def _fit_window_height(self):
        """Grow the window so the whole job panel fits without scrolling
        (limited to the screen; the panel scrolls on small screens)."""
        scroll = self.panel_scroll
        panel = scroll.widget()
        chrome = self.height() - scroll.viewport().height()   # menus, toolbar, dock title, status bar
        needed = chrome + panel.sizeHint().height() + 2
        screen = self.screen().availableGeometry() if self.screen() else None
        if screen is not None:
            frame = self.frameGeometry().height() - self.geometry().height()
            needed = min(needed, screen.height() - max(frame, 0))
        if self.height() < needed:
            self.resize(self.width(), needed)
            if screen is not None and self.frameGeometry().bottom() > screen.bottom():
                self.move(self.x(), max(screen.top(), screen.bottom() - self.frameGeometry().height()))

    def showEvent(self, event):
        super().showEvent(event)
        if not getattr(self, "_shown_once", False):
            self._shown_once = True
            QTimer.singleShot(0, self._fit_window_height)

    def _update_unit_suffixes(self):
        units = self.values.get("units", "mm")
        speed = "mm/s" if units == "mm" else "in/min"
        self.speed_header.setText("Speed (%s)" % speed)
        for w, kind, _, _ in self._unit_widgets:
            w.setSuffix(" " + (units if kind == "len" else speed))

    def _reload_spin_values(self):
        """Re-read unit-dependent fields after the units changed."""
        for w, kind, key, sign in self._unit_widgets:
            w.blockSignals(True)
            try:
                w.setValue(max(w.minimum(), sign * float(self.values[key])))
            except (KeyError, ValueError):
                pass
            w.blockSignals(False)

    def _update_laser_state(self):
        if self.laser.connected:
            self.laser_label.setText("<b style='color:#2e7d32'>Connected</b> (%s)"
                                     % self.values.get("board_name"))
            self.btn_connect.setText("Re-initialize")
        else:
            self.laser_label.setText("<b style='color:#c62828'>Not connected</b>")
            self.btn_connect.setText("Initialize")
        x = self.head[0] + self.head_offset[0] / 1000.0
        y = self.head[1] + self.head_offset[1] / 1000.0
        scale = 25.4 if self.values.get("units") == "mm" else 1.0
        self.head_label.setText("Head: X %.1f  Y %.1f %s" % (x * scale + 0.0, -y * scale + 0.0,
                                                              self.values.get("units")))

    def set_busy(self, busy):
        for w in [self.btn_start, self.btn_trace, self.btn_egv, self.btn_connect, self.btn_goto,
                  self.btn_test_fire, self.btn_calc_time] + self.corner_buttons:
            w.setEnabled(not busy)
        for a in [self.act_open, self.act_reload, self.act_save_egv, self.act_send_egv,
                  self.act_connect, self.act_release, self.act_home, self.act_unlock,
                  self.act_settings, self.act_goto, self.act_calc_time] + list(self.act_corners.values()):
            a.setEnabled(not busy)
        self.btn_stop.setEnabled(busy)
        self.progress.setVisible(busy)

    def status(self, message, error=False):
        self.statusBar().setStyleSheet("color:#c62828;" if error else "")
        self.statusBar().showMessage(message)

    def refresh_preview(self, fit=False):
        try:
            settings = self.job_settings()
        except ValueError as e:
            self.status(str(e), error=True)
            return
        self.preview.show_design(self.design, settings, self.values, self.head, fit=fit,
                                 head_offset=(self.head_offset[0] / 1000.0,
                                              self.head_offset[1] / 1000.0))
        self._update_laser_state()
        self._update_times()

    # ------------------------------------------------------------ design files
    def open_design(self):
        start = os.path.dirname(self.design_file or self.values.get("designfile", "")) or os.path.expanduser("~")
        name, _ = QFileDialog.getOpenFileName(self, "Open design", start, DESIGN_FILTERS)
        if name:
            self.load_design(name)

    def reload_design(self):
        if self.design_file:
            self.load_design(self.design_file)
        else:
            self.open_design()

    def _ask_dxf_units(self):
        unit, ok = QInputDialog.getItem(self, "DXF units",
                                        "The DXF file does not say which units it uses.\nUnits:",
                                        loaders.DXF_UNITS, loaders.DXF_UNITS.index("Millimeters"),
                                        False)
        return unit if ok else None

    def _ask_svg_scale(self, svg_size, viewbox, inkscape_version):
        q = loaders.SvgScale(svg_size, viewbox, inkscape_version)
        w, h = q.size_mm(q.default_pxpi)
        pxpi, ok = QInputDialog.getDouble(
            self, "SVG import scale",
            "The SVG file does not define its physical size.\n"
            "Pixels per inch (Inkscape 0.92+: 96, older Inkscape: 90, Illustrator: 72).\n"
            "At %g px/in the design is %.1f x %.1f mm." % (q.default_pxpi, w, h),
            q.default_pxpi, 1.0, 10000.0, 2)
        return q.result(pxpi) if ok else None

    def load_design(self, filename):
        ext = os.path.splitext(filename)[1].lower()
        QApplication.setOverrideCursor(Qt.WaitCursor)
        self.status("Opening %s" % filename)
        QApplication.processEvents()

        def progress(msg):
            self.status(msg)
            QApplication.processEvents()
        try:
            if ext == ".svg":
                warnings = loaders.load_svg(
                    filename, self.design,
                    inkscape_path=self.values.get("inkscape_path", ""),
                    inkscape_timeout_s=float(self.values.get("ink_timeout", 3)) * 60.0,
                    reduced_memory=is_true(self.values.get("reduced_mem", "0")),
                    ask_pxpi=self._ask_svg_scale, progress=progress)
            elif ext == ".dxf":
                warnings = loaders.load_dxf(filename, self.design, ask_units=self._ask_dxf_units)
            else:
                warnings = loaders.load_gcode(filename, self.design)
        except loaders.LoadCancelled:
            QApplication.restoreOverrideCursor()
            self.status("Loading cancelled")
            self.refresh_preview()
            return
        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.status("Could not open %s" % os.path.basename(filename), error=True)
            QMessageBox.critical(self, "Could not open design", str(e))
            self.refresh_preview()
            return
        QApplication.restoreOverrideCursor()
        self.design_file = filename
        self.values["designfile"] = filename
        self._update_design_label()
        self._update_power_visibility()
        self.refresh_preview(fit=True)
        self.status("Opened %s" % filename)
        for w in warnings:
            QMessageBox.warning(self, "Design import", w)

    def _update_design_label(self):
        d = self.design
        xmin, xmax, ymin, ymax = d.bounds
        parts = []
        if d.raster.image is not None:
            parts.append("raster")
        if d.vector_engrave.ecoords:
            parts.append("vector engrave")
        if d.vector_cut.ecoords:
            parts.append("vector cut")
        if d.gcode.ecoords:
            parts.append("g-code")
        self.design_label.setText("<b>%s</b><br>%.1f × %.1f mm<br>%s" % (
            os.path.basename(self.design_file), (xmax - xmin) * 25.4, (ymax - ymin) * 25.4,
            ", ".join(parts) or "empty"))

    # ------------------------------------------------------------ settings
    def edit_settings(self):
        dlg = SettingsDialog(self.values, self)
        if not dlg.exec():
            return
        new, changed = dlg.result_values()
        if not changed:
            return
        if "units" in changed:
            old = dict(new)
            old["units"] = self.values["units"]
            new = config.convert_units(old, new["units"])
        self.values.clear()
        self.values.update(new)
        self._reload_spin_values()
        self._update_unit_suffixes()
        self._update_power_visibility()
        if changed & RASTER_KEYS:
            self.design.raster.reset_path()
        if changed & RELOAD_KEYS and self.design_file:
            self.load_design(self.design_file)
        self.refresh_preview()
        self.status("Settings changed (use File → Save settings as default to keep them)")

    def save_settings(self):
        path = config.user_config_path()
        try:
            config.write_settings_file(path, self.values, "0.71 (Kerfly %s)" % __version__)
        except OSError as e:
            self.status("Could not save settings: %s" % e, error=True)
            return
        self.status("Settings saved to %s" % path)

    # ------------------------------------------------------------ laser
    def _laser_call(self, func, ok_message):
        if not self.laser.connected:
            self.status("Laser is not initialized.", error=True)
            return False
        try:
            func()
        except Exception as e:
            self.status("%s" % e, error=True)
            return False
        self.status(ok_message)
        return True

    def connect_laser(self):
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            self.laser.connect(init_home=is_true(self.values.get("init_home", "1")))
            self.head = (0.0, 0.0)
            self.head_offset = (0, 0)
            self.status("Laser initialized")
        except LaserError as e:
            self.status(str(e), error=True)
        except Exception as e:
            self.status("Unknown USB error: %s" % e, error=True)
        finally:
            QApplication.restoreOverrideCursor()
        self.refresh_preview()

    def release_laser(self):
        try:
            self.laser.release()
            self.status("USB released")
        except Exception as e:
            self.status(str(e), error=True)
        self._update_laser_state()

    def home(self):
        if self.laser.connected and not self._laser_call(self.laser.home, "Homed"):
            return
        self.head = (0.0, 0.0)
        self.head_offset = (0, 0)
        self.refresh_preview()

    def unlock(self):
        self._laser_call(self.laser.unlock, "Rail unlocked")

    def unfreeze(self):
        self._laser_call(self.laser.unfreeze, "Unfreeze complete")

    def jog(self, dirx, diry):
        """Move by one jog step in the given direction (+y = up)."""
        try:
            step = float(self.values["jog_step"])
        except ValueError as e:
            self.status(str(e), error=True)
            return
        self.move_by(dirx * step, diry * step)

    def move_by(self, dx_units, dy_units):
        """Move the design origin and head by (dx, dy) in the current units (+y = up)."""
        if self.worker is not None:
            return
        try:
            settings = self.job_settings()
            bed_w, bed_h = config.bed_size_inches(self.values)
        except ValueError as e:
            self.status(str(e), error=True)
            return
        f = 1.0 if self.values.get("units") == "in" else 1 / 25.4
        dx = round(dx_units * f, 3)
        dy = round(dy_units * f, 3)
        if settings.home_upper_right:
            dx = -dx
        xmin, xmax, ymin, ymax = self.design.origin_bounds(settings)
        x, y = clamp_head_position(self.head[0], self.head[1], dx, dy, bed_w, bed_h,
                                   xmax - xmin, ymax - ymin,
                                   offset=(self.head_offset[0] / 1000.0, self.head_offset[1] / 1000.0))
        if self.laser.connected:
            try:
                self.laser.rapid_move((x - self.head[0]) * 1000.0, (y - self.head[1]) * 1000.0,
                                      settings, self.send_options())
            except Exception as e:
                self.status("Rapid move failed: %s" % e, error=True)
                return
        self.head = (x, y)
        self.refresh_preview()

    def move_head_temporary(self, offset_mils):
        """Move the head to origin + offset (mils) without moving the design origin."""
        try:
            settings = self.job_settings()
            bed_w, bed_h = config.bed_size_inches(self.values)
        except ValueError as e:
            self.status(str(e), error=True)
            return False
        if settings.input_csys and self.design.raster.image is None:
            target = (0, 0)
        else:
            target = temporary_offset_target(self.head, offset_mils, bed_w, bed_h)
        dx = target[0] - self.head_offset[0]
        dy = target[1] - self.head_offset[1]
        if self.laser.connected and (dx or dy):
            try:
                self.laser.rapid_move(dx, dy, settings, self.send_options())
            except Exception as e:
                self.status("Rapid move failed: %s" % e, error=True)
                return False
        self.head_offset = target
        self.refresh_preview()
        return True

    def move_to_corner(self, corner):
        if self.worker is not None:
            return
        try:
            settings = self.job_settings()
            bed_w, bed_h = config.bed_size_inches(self.values)
        except ValueError as e:
            self.status(str(e), error=True)
            return
        bounds = self.design.get_bounds(settings.rotate)
        offset = corner_offset(corner, bounds, settings.home_upper_right, self.head, bed_w, bed_h)
        if offset is None:
            self.status("That corner of the design is outside the laser bed.", error=True)
            return
        self.move_head_temporary(offset)

    def goto_position(self):
        """Home, then move to the X/Y set in the panel (distance from home, Y downwards)."""
        if self.worker is not None:
            return
        x, y = self.goto_x.value(), self.goto_y.value()
        if self.laser.connected and not self._laser_call(self.laser.home, "Homed"):
            return
        self.head = (0.0, 0.0)
        self.head_offset = (0, 0)
        self.move_by(x, -y)

    def test_fire(self):
        if not self.laser.connected:
            self.status("Laser is not initialized.", error=True)
            return
        try:
            ms = int(float(self.values["test_time"]))
            if ms > 1000:
                ms = 0
            fraction = float(self.values["test_power"])
            if fraction > 1:
                fraction = 0
            power = fraction * float(self.values["max_power"])
        except ValueError as e:
            self.status(str(e), error=True)
            return
        self._laser_call(lambda: self.laser.test_fire(power, ms),
                         "Test fire: %.0f%% for %d ms" % (power, ms))

    def calculate_raster_time(self):
        if self.worker is not None or self.design.raster.image is None:
            return
        try:
            settings = self.job_settings()
        except ValueError as e:
            self.status(str(e), error=True)
            return
        self._run_worker(RasterPrepareWorker(self.design, settings, parent=self),
                         "Preparing raster…")

    def send_egv_file(self):
        if self.worker is not None:
            return
        if not self.laser.connected:
            self.status("Laser is not initialized.", error=True)
            return
        start = os.path.dirname(self.design_file) or os.path.expanduser("~")
        name, _ = QFileDialog.getOpenFileName(self, "Send EGV file", start,
                                              "EGV files (*.egv *.EGV);;All files (*)")
        if not name:
            return
        try:
            egv = egvfile.read_egv_file(name)
            settings = self.job_settings()
            send_options = self.send_options()
        except (OSError, ValueError) as e:
            self.status("Could not read %s: %s" % (os.path.basename(name), e), error=True)
            return
        passes = 1
        if not egv.has_end_position:
            passes, ok = QInputDialog.getInt(self, "Send EGV file", "Number of passes:", 1, 1, 100)
            if not ok:
                return
        if self.head_offset != (0, 0) and not self.move_head_temporary((0, 0)):
            return
        # the loaded design is not what is being cut: clear it, as K40 Whisperer does
        self.design.reset()
        self.design_file = name
        self._update_design_label()
        self._update_power_visibility()
        self.refresh_preview()
        self._run_worker(EgvSendWorker(egv, passes, self.laser, settings, send_options, parent=self),
                         "Sending %s…" % os.path.basename(name))

    # ------------------------------------------------------------ jobs
    def selected_operation(self):
        d = self.design
        has = {job.RASTER_ENG: d.raster.image is not None, job.VECTOR_ENG: bool(d.vector_engrave.ecoords),
               job.VECTOR_CUT: bool(d.vector_cut.ecoords), job.GCODE_CUT: bool(d.gcode.ecoords)}
        ops = [op for _, _, _, _, _, op in OPERATIONS if self.include_checks[op].isChecked() and has[op]]
        return "+".join(ops)

    def start_job(self, output_file=None, trace=False):
        if self.worker is not None:
            return
        op = job.TRACE_ENG if trace else self.selected_operation()
        if not op:
            self.status("Nothing to do: load a design and select at least one operation.", error=True)
            return
        if output_file is None and not self.laser.connected:
            self.status("Laser is not initialized.", error=True)
            return
        try:
            settings = self.job_settings()
            send_options = self.send_options()
        except ValueError as e:
            self.status(str(e), error=True)
            return
        if output_file is None and self.head_offset != (0, 0):
            # the job starts at the design origin: bring the head back first
            if not self.move_head_temporary((0, 0)):
                return
        self._run_worker(JobWorker(self.design, settings, op,
                                   laser=None if output_file else self.laser,
                                   output_file=output_file, send_options=send_options,
                                   parent=self), "Preparing job\u2026")

    def _run_worker(self, worker, message):
        self.worker = worker
        worker.progress.connect(self.status)
        worker.paused.connect(self._job_paused)
        worker.finished_job.connect(self._job_finished)
        self.set_busy(True)
        self.status(message)
        worker.start()

    def save_egv(self):
        base = os.path.splitext(self.design_file)[0] if self.design_file else os.path.expanduser("~/out")
        name, _ = QFileDialog.getSaveFileName(self, "Save EGV file", base + ".EGV", "EGV files (*.EGV *.egv)")
        if name:
            self.start_job(output_file=name)

    def stop_job(self):
        if self.worker is not None:
            self.status("Stopping\u2026")
            self.worker.request_stop()

    def _job_paused(self):
        answer = QMessageBox.question(
            self, "Laser paused", "The laser is paused.\n\nResume the job?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
        if answer == QMessageBox.Yes:
            self.worker.pause.resume()
            self.status("Resumed")
        else:
            self.worker.pause.terminate()

    def _job_finished(self, ok, message):
        was_laser_job = isinstance(self.worker, (JobWorker, EgvSendWorker)) and self.worker.laser is not None
        self.worker.wait()
        self.worker = None
        self.set_busy(False)
        self.status(message, error=not ok)
        if was_laser_job and self.laser.connected:
            if is_true(self.values.get("post_home", "0")):
                try:
                    self.laser.unlock()
                except Exception:
                    pass
            if is_true(self.values.get("post_beep", "0")):
                QApplication.beep()
        self.refresh_preview()

    # ------------------------------------------------------------ misc
    def about(self):
        QMessageBox.about(
            self, "About Kerfly",
            "<h3>Kerfly %s</h3>"
            "<p>Laser cutter control software for K40 lasers with Lihuiyu M2 Nano boards.</p>"
            "<p>Based on <a href='https://www.scorchworks.com/K40whisperer/k40whisperer.html'>"
            "K40 Whisperer</a> by Scorch.</p>"
            "<p>Free software under the GNU General Public License v3 or later.<br>"
            "<a href='https://github.com/cyryllo/Kerfly'>github.com/cyryllo/Kerfly</a></p>" % __version__)

    def closeEvent(self, event):
        if self.worker is not None:
            if QMessageBox.question(self, "Job running",
                                    "A job is running. Stop it and quit?") != QMessageBox.Yes:
                event.ignore()
                return
            self.worker.stop[0] = True
            self.worker.pause.terminate()
            self.worker.wait(5000)
        try:
            self.laser.release()
        except Exception:
            pass
        event.accept()
