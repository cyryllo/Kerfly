"""
Kerfly main window.

Copyright (C) 2026 Kerfly contributors
Licensed under the GNU General Public License v3 or later. See LICENSE.
"""
import os

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtCore import QLocale
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtGui import QActionGroup
from PySide6.QtWidgets import (QApplication, QCheckBox, QDockWidget, QDoubleSpinBox, QFileDialog,
                               QGridLayout, QGroupBox, QHBoxLayout, QInputDialog, QLabel,
                               QListWidget, QListWidgetItem, QMainWindow, QMessageBox, QProgressBar,
                               QPushButton, QScrollArea, QSpinBox, QTabWidget, QToolBar, QToolButton,
                               QVBoxLayout, QWidget, QFrame)

from kerfly import __version__
from kerfly.core import config, egvfile, job, loaders
from kerfly.i18n import C_, N_, _, ngettext, tr_message
from kerfly.core.config import is_true
from kerfly.core.design import Design
from kerfly.core.estimate import estimate_times, format_time
from kerfly.core.laser import LaserController, LaserError, clamp_head_position, corner_offset
from kerfly.core.layout import Element, compile_layout
from kerfly.core.shapes import ShapeSpec, build_design
from kerfly.gui import icons
from kerfly.gui.image_dialog import ImageSizeDialog
from kerfly.gui.text_shapes import update_text_spec
from kerfly.gui.tool_options import KIND_NAMES, NEW_KIND_TITLES, ToolOptionsBar
from kerfly.gui.preview import PreviewView
from kerfly.gui.settings_dialog import RASTER_KEYS, RELOAD_KEYS, SettingsDialog
from kerfly.gui.worker import EgvSendWorker, JobWorker, RasterPrepareWorker

IMAGE_PATTERNS = " ".join("*" + e for e in loaders.IMAGE_EXTENSIONS)


def design_filters():
    return ";;".join([_("Design files") + " (*.svg *.dxf *.ngc *.gcode *.nc *.g *.tap %s)" % IMAGE_PATTERNS,
                      _("SVG files") + " (*.svg)", _("DXF files") + " (*.dxf)",
                      _("Images") + " (%s)" % IMAGE_PATTERNS,
                      _("G-code files") + " (*.ngc *.gcode *.nc *.g *.tap)",
                      _("All files") + " (*)"])

# (label, include key, speed key, passes key, power key, operation)
OPERATIONS = [
    (N_("Raster engrave"), "include_Reng", "Reng_feed", "Reng_passes", "Reng_power", job.RASTER_ENG),
    (N_("Vector engrave"), "include_Veng", "Veng_feed", "Veng_passes", "Veng_power", job.VECTOR_ENG),
    (N_("Vector cut"), "include_Vcut", "Vcut_feed", "Vcut_passes", "Vcut_power", job.VECTOR_CUT),
    (N_("G-code"), "include_Gcde", None, "Gcde_passes", "Gcode_power", job.GCODE_CUT),
]


def _num(value, decimals=1):
    """Number formatted for the current language (e.g. 12,5 in Polish)."""
    return QLocale().toString(float(value) + 0.0, "f", decimals)


def _num_text(v):
    return ("%.4f" % v).rstrip("0").rstrip(".")


class MainWindow(QMainWindow):
    def __init__(self, values):
        super().__init__()
        self.values = values
        self.elements = []              # design elements placed on the bed
        self.selected = None            # selected element
        self._compiled = None           # cached (design, origin) compiled from the elements
        self._undo = []                 # layout snapshots for undo / redo
        self._redo = []
        self.design_file = ""           # last file opened (start folder for file dialogs)
        self.laser = LaserController()
        self.head = (0.0, 0.0)          # laser head position on the bed, inches (y <= 0)
        self.worker = None
        self._paused = False
        self._unit_widgets = []         # (spinbox, kind, key, sign) to update when units change

        self.setWindowTitle(_("Kerfly %s") % __version__)
        self.resize(1200, 780)
        self.preview = PreviewView()
        self.tool_options = ToolOptionsBar()
        self.tool_options.changed.connect(self._tool_options_changed)
        central = QWidget()
        central_layout = QVBoxLayout(central)
        central_layout.setContentsMargins(0, 0, 0, 0)
        central_layout.setSpacing(0)
        central_layout.addWidget(self.tool_options)
        central_layout.addWidget(self.preview, 1)
        self.setCentralWidget(central)
        self.shape_defaults = {kind: ShapeSpec(kind=kind, operation="fill" if kind == "text" else "cut",
                                               text=_("Text"))
                               for kind in ("rectangle", "ellipse", "polygon", "line", "text")}
        self.preview.signals.drawn.connect(self._preview_drawn)
        self.preview.signals.selected.connect(self._preview_selected)
        self.preview.signals.moved.connect(self._preview_moved)
        self.preview.signals.scaled.connect(self._preview_scaled)
        self.preview.signals.rotated.connect(self._preview_rotated)
        self.preview.signals.nudged.connect(self._preview_nudged)
        self._build_actions()
        self._build_tool_strip()
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
        self.act_open = self._action(_("&Open design\u2026"), self.open_design, "Ctrl+O",
                                     _("Open a file, replacing everything on the bed"))
        self.act_reload = self._action(_("&Reload design"), self.reload_design, "F5")
        self.act_add = self._action(_("&Add design…"), self.add_design, "Ctrl+Shift+O",
                                    _("Add another file to the laser bed"))
        self.act_delete = self._action(_("&Delete element"), self.delete_selected, "Delete")
        self.act_delete.setShortcutContext(Qt.WidgetWithChildrenShortcut)   # only in the bed view
        self.preview.addAction(self.act_delete)
        self.act_undo = self._action(_("&Undo"), self.undo, "Ctrl+Z")
        self.act_redo = self._action(_("&Redo"), self.redo, "Ctrl+Shift+Z")
        self.act_duplicate = self._action(_("D&uplicate element"), self.duplicate_selected, "Ctrl+D")
        self.act_center = self._action(_("&Centre on the bed"), self.center_on_bed, "Ctrl+E",
                                       _("Centre the selected element, or the whole design, on the bed"))
        self.act_snap = self._action(_("&Snap to grid"), self.toggle_snap, "Ctrl+'")
        self.act_snap.setCheckable(True)
        self.act_snap.setChecked(self._grid_mm() > 0)
        self.grid_actions = QActionGroup(self)
        for mm in (1, 2, 5, 10):
            a = self._action(_("%d mm") % mm, lambda _c=False, g=mm: self.set_grid(g))
            a.setCheckable(True)
            a.setChecked(abs(self._grid_size_choice() - mm) < 1e-9)
            self.grid_actions.addAction(a)
        self.act_rot_left = self._action(_("Rotate 90° counter-clockwise"),
                                         lambda: self.rotate_selected(90), "Ctrl+L")
        self.act_rot_right = self._action(_("Rotate 90° clockwise"),
                                          lambda: self.rotate_selected(-90), "Ctrl+R")
        self.act_place_head = self._action(_("Place design at the &head"), self.place_at_head, "Ctrl+H",
                                           _("Move all elements so the design starts at the laser head"))
        self.act_save_egv = self._action(_("Save &EGV file\u2026"), self.save_egv, "Ctrl+Shift+E",
                                         _("Write the selected operations to an EGV file"))
        self.act_send_egv = self._action(_("Send EGV file to laser\u2026"), self.send_egv_file, None,
                                         _("Send an existing EGV file to the laser"))
        self.act_save_settings = self._action(_("Save settings as default"), self.save_settings, "Ctrl+S")
        self.act_goto = self._action(_("&Go to X/Y position"), self.goto_position, "Ctrl+G")
        self.act_corners = {}
        for key, text, sc in (("UL", N_("Upper left corner"), "Ctrl+7"),
                              ("UR", N_("Upper right corner"), "Ctrl+9"),
                              ("CC", N_("Centre"), "Ctrl+5"), ("LL", N_("Lower left corner"), "Ctrl+1"),
                              ("LR", N_("Lower right corner"), "Ctrl+3")):
            self.act_corners[key] = self._action(_(text), lambda _checked=False, k=key: self.move_to_corner(k), sc)
        self.act_calc_time = self._action(_("Calculate raster time"), self.calculate_raster_time)
        self.act_quit = self._action(_("&Quit"), self.close, "Ctrl+Q")
        self.act_connect = self._action(_("&Initialize laser"), self.connect_laser, "Ctrl+I")
        self.act_release = self._action(_("Release USB"), self.release_laser)
        self.act_home = self._action(_("&Home"), self.home, "Home")
        self.act_unlock = self._action(_("&Unlock rail"), self.unlock)
        self.act_unfreeze = self._action(_("Un&freeze laser"), self.unfreeze)
        self.act_fit = self._action(_("&Fit to window"), lambda: self.preview.fit_all(), "Ctrl+0")
        self.act_settings = self._action(_("&Settings\u2026"), self.edit_settings, "Ctrl+,")
        self.act_about = self._action(_("&About Kerfly"), self.about)

        mb = self.menuBar()
        m = mb.addMenu(_("&File"))
        for a in (self.act_open, self.act_add, self.act_reload, None, self.act_save_egv,
                  self.act_send_egv, None, self.act_save_settings, None, self.act_quit):
            m.addSeparator() if a is None else m.addAction(a)
        m = mb.addMenu(_("&Edit"))
        for a in (self.act_undo, self.act_redo, None, self.act_duplicate, self.act_delete, None,
                  self.act_rot_left, self.act_rot_right, None, self.act_center, self.act_place_head):
            m.addSeparator() if a is None else m.addAction(a)
        m = mb.addMenu(_("&Laser"))
        self.laser_menu = m
        for a in (self.act_connect, self.act_release, None, self.act_home, self.act_unlock,
                  self.act_unfreeze, None, self.act_goto):
            m.addSeparator() if a is None else m.addAction(a)
        sub = m.addMenu(_("Move head to design"))
        for a in self.act_corners.values():
            sub.addAction(a)
        m = mb.addMenu(_("&View"))
        m.addAction(self.act_fit)
        m.addSeparator()
        m.addAction(self.act_snap)
        sub = m.addMenu(_("Grid size"))
        for a in self.grid_actions.actions():
            sub.addAction(a)
        m = mb.addMenu(_("&Settings"))
        m.addAction(self.act_settings)
        m = mb.addMenu(_("&Help"))
        m.addAction(self.act_about)

        self._build_toolbar()

    def _build_toolbar(self):
        """Toolbar in labelled groups, like the MeerK40t ribbon. Machine control
        (connect, home, start, stop, ...) is in the left panel, not here."""
        self.act_start = self._action(_("Start"), lambda: self.start_job(), "F9",
                                      _("Start the selected operations"))
        self.act_stop = self._action(_("Stop"), self.stop_job, "Esc", _("Pause or stop the running job"))
        self.act_stop.setEnabled(False)
        self.act_trace = self._action(_("Trace boundary"), lambda: self.start_job(trace=True), None,
                                      _("Move around the outline of the design"))
        self.laser_menu.addSeparator()
        for a in (self.act_trace, self.act_start, self.act_stop):
            self.laser_menu.addAction(a)
        self.act_trace.setIcon(icons.trace_icon())
        self.act_start.setIcon(icons.tabler("player-play", "#2e7d32"))
        self.act_stop.setIcon(icons.tabler("player-stop", "#c62828"))

        groups = [
            (C_("toolbar group", "File"), [
                (self.act_open, "folder-open", C_("toolbar", "Open")),
                (self.act_add, "file-plus", C_("toolbar", "Add")),
                (self.act_reload, "refresh", C_("toolbar", "Reload")),
                (self.act_save_egv, "device-floppy", C_("toolbar", "Save EGV")),
            ]),
            (C_("toolbar group", "Edit"), [
                (self.act_undo, "arrow-back-up", C_("toolbar", "Undo")),
                (self.act_redo, "arrow-forward-up", C_("toolbar", "Redo")),
                (self.act_duplicate, "copy", C_("toolbar", "Duplicate")),
                (self.act_delete, "trash", C_("toolbar", "Delete")),
            ]),
            (C_("toolbar group", "Arrange"), [
                (self.act_rot_left, "rotate-2", C_("toolbar", "Rotate left")),
                (self.act_rot_right, "rotate-clockwise-2", C_("toolbar", "Rotate right")),
                (self.act_center, "focus-centered", C_("toolbar", "Centre")),
                (self.act_place_head, "current-location", C_("toolbar", "To head")),
            ]),
            (C_("toolbar group", "View"), [
                (self.act_fit, "zoom-scan", C_("toolbar", "Fit")),
                (self.act_snap, "grid-dots", C_("toolbar", "Grid")),
                (self.act_settings, "settings", C_("toolbar", "Settings")),
            ]),
        ]
        tb = QToolBar(_("Main toolbar"))
        tb.setObjectName("main_toolbar")
        tb.setMovable(False)
        for i, (title, entries) in enumerate(groups):
            if i:
                line = QFrame()
                line.setFrameShape(QFrame.VLine)
                line.setObjectName("ribbon_separator")
                tb.addWidget(line)
            group = QWidget()
            v = QVBoxLayout(group)
            v.setContentsMargins(4, 2, 4, 0)
            v.setSpacing(0)
            row = QHBoxLayout()
            row.setSpacing(1)
            for action, icon, short in entries:
                action.setIcon(icons.tabler(icon))
                action.setIconText(short)
                if not action.toolTip() or action.toolTip() == action.iconText():
                    action.setToolTip(action.text().replace("&", ""))
                button = QToolButton()
                button.setDefaultAction(action)
                button.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
                button.setIconSize(QSize(24, 24))
                button.setAutoRaise(True)
                button.setFixedHeight(62)        # same height for one- and two-line labels
                row.addWidget(button, 0, Qt.AlignTop)
            v.addLayout(row)
            caption = QLabel(title)
            caption.setObjectName("ribbon_caption")
            caption.setAlignment(Qt.AlignHCenter)
            v.addWidget(caption)
            tb.addWidget(group)
        self.addToolBar(tb)

    def _build_tool_strip(self):
        """Vertical strip of drawing tools on the right of the bed view (like LightBurn's)."""
        strip = QToolBar(_("Drawing tools"))
        strip.setObjectName("tool_strip")
        strip.setMovable(False)
        strip.setOrientation(Qt.Vertical)
        strip.setIconSize(QSize(24, 24))
        strip.setToolButtonStyle(Qt.ToolButtonIconOnly)
        self.tool_group = QActionGroup(self)
        self.tool_actions = {}
        tools = [("select", "pointer", N_("Select and move"), "S"),
                 ("rectangle", "square", N_("Rectangle"), "R"),
                 ("ellipse", "circle", N_("Ellipse"), "E"),
                 ("polygon", "hexagon", N_("Polygon"), "P"),
                 ("line", "line", N_("Line"), "L"),
                 ("text", "typography", N_("Text"), "T")]
        for key, icon, name, shortcut in tools:
            act = QAction(icons.tabler(icon), _(name), self)
            act.setCheckable(True)
            act.setShortcut(QKeySequence(shortcut))
            act.setShortcutContext(Qt.WidgetWithChildrenShortcut)    # only while the bed view has focus
            act.setToolTip("%s (%s)" % (_(name), shortcut))
            act.triggered.connect(lambda _c=False, k=key: self.set_tool(k))
            self.tool_group.addAction(act)
            self.preview.addAction(act)
            strip.addAction(act)
            self.tool_actions[key] = act
        self.tool_actions["select"].setChecked(True)
        self.addToolBar(Qt.RightToolBarArea, strip)

    def set_tool(self, tool):
        self.preview.set_tool(tool)
        self.tool_actions[tool].setChecked(True)
        if tool != "select":
            self.preview.setFocus()
        self._update_tool_options()

    def _update_tool_options(self, force=False):
        e = self.selected
        if e is not None and e.shape is not None:
            if not force and getattr(self, "_options_target", None) == "selected" \
                    and getattr(self, "_options_element", None) is e:
                return                   # already shown; rebuilding would interrupt typing
            self._options_target, self._options_element = "selected", e
            self.tool_options.show_spec(e.shape, "%s:" % e.name)
        elif self.preview.tool != "select":
            self._options_target, self._options_element = self.preview.tool, None
            self.tool_options.show_spec(self.shape_defaults[self.preview.tool],
                                        _(NEW_KIND_TITLES[self.preview.tool]))
        else:
            self._options_target, self._options_element = None, None
            self.tool_options.show_hint()

    def _tool_options_changed(self, spec):
        target = getattr(self, "_options_target", None)
        if target == "selected" and self.selected is not None and self.selected.shape is not None:
            self._apply_shape(self.selected, spec)
        elif target in self.shape_defaults:
            self.shape_defaults[target] = spec

    def _apply_shape(self, element, spec):
        """Rebuild a drawn element from a changed spec, keeping its top-left corner."""
        self._checkpoint()
        if spec.kind == "text":
            update_text_spec(spec)
        x, y = element.x, element.y
        element.shape = spec
        element.design = build_design(spec)
        element.x, element.y = x, y
        self._keep_on_bed(element)
        self._layout_changed()

    def _preview_drawn(self, tool, start, end, shift):
        """A shape was drawn in the bed view (scene mm, y down)."""
        if tool == "cancel":
            self.set_tool("select")
            return
        spec = self.shape_defaults[tool].copy()
        dx, dy = end.x() - start.x(), end.y() - start.y()
        clicked = abs(dx) < 0.5 and abs(dy) < 0.5
        if tool == "text":
            update_text_spec(spec)
            left, top = start.x(), start.y()
        elif tool == "line":
            if clicked:
                dx, dy = 20.0, 0.0
            if shift:                                    # 0 / 45 / 90 degree steps
                import math
                angle = round(math.atan2(dy, dx) / (math.pi / 4)) * (math.pi / 4)
                length = math.hypot(dx, dy)
                dx, dy = length * math.cos(angle), length * math.sin(angle)
            spec.width, spec.height = dx, dy
            left, top = min(start.x(), start.x() + dx), min(start.y(), start.y() + dy)
        else:
            if clicked:
                dx, dy = 20.0, 20.0
            if shift:
                side = max(abs(dx), abs(dy))
                dx, dy = (side if dx >= 0 else -side), (side if dy >= 0 else -side)
            spec.width, spec.height = abs(dx), abs(dy)
            left, top = min(start.x(), start.x() + dx), min(start.y(), start.y() + dy)
        design = build_design(spec)
        xmin, xmax, ymin, ymax = design.bounds
        if xmax - xmin <= 0 and ymax - ymin <= 0:
            self.status(_("Nothing to draw."), error=True)
            return
        self._checkpoint()
        element = Element(design, name=_(KIND_NAMES[tool]), shape=spec)
        bed_w, bed_h = config.bed_size_inches(self.values)
        width_in = xmax - xmin
        if self.job_settings().home_upper_right:
            element.x = bed_w - left / 25.4 - width_in
        else:
            element.x = left / 25.4
        element.y = -top / 25.4
        self._keep_on_bed(element)
        self.elements.append(element)
        self.selected = element
        self._compiled = None
        self.set_tool("select")
        self._layout_changed()

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
        self.tabs = QTabWidget()
        design_page, laser_page = QWidget(), QWidget()
        design_layout = QVBoxLayout(design_page)
        laser_layout = QVBoxLayout(laser_page)
        for lay in (design_layout, laser_layout):
            lay.setContentsMargins(4, 6, 4, 4)
        self.tabs.addTab(design_page, _("Design"))
        self.tabs.addTab(laser_page, _("Laser"))
        layout.addWidget(self.tabs)

        # --- design info and element list
        box = QGroupBox()
        v = QVBoxLayout(box)
        self.design_label = QLabel(_("No design loaded"))
        self.design_label.setWordWrap(True)
        v.addWidget(self.design_label)
        self.element_list = QListWidget()
        self.element_list.setMaximumHeight(96)
        self.element_list.setToolTip(_("Untick an element to leave it out of the job"))
        self.element_list.itemChanged.connect(self._element_item_changed)
        self.element_list.currentRowChanged.connect(self._element_row_selected)
        v.addWidget(self.element_list)
        design_layout.addWidget(box)

        # --- selected element
        self.selection_box = QGroupBox(_("Selected element"))
        g = QGridLayout(self.selection_box)
        self.sel_name = QLabel()
        self.sel_name.setWordWrap(True)
        g.addWidget(self.sel_name, 0, 0, 1, 4)
        self.sel_fields = {}
        for i, (key, label) in enumerate((("x", N_("X")), ("y", N_("Y")), ("w", N_("W")), ("h", N_("H")))):
            spin = QDoubleSpinBox()
            spin.setRange(-10000.0 if key in "xy" else 0.01, 10000.0)
            spin.setDecimals(2)
            spin.setFixedWidth(104)
            spin.setKeyboardTracking(False)          # apply on Enter / focus out, not per digit
            spin.valueChanged.connect(lambda _v, k=key: self._selection_field_changed(k))
            g.addWidget(QLabel(_(label)), 1 + i // 2, (i % 2) * 2)
            g.addWidget(spin, 1 + i // 2, (i % 2) * 2 + 1)
            self.sel_fields[key] = spin
        self.sel_fields["y"].setToolTip(_("Distance down from home"))
        g.setColumnStretch(4, 1)          # keep label/field pairs together on the left
        g.setHorizontalSpacing(8)
        self.sel_lock = QCheckBox(_("Keep proportions"))
        self.sel_lock.setChecked(True)
        g.addWidget(self.sel_lock, 3, 0, 1, 4)
        row = QHBoxLayout()
        row.addWidget(QLabel(_("Rotation")))
        self.sel_rotation = QDoubleSpinBox()
        self.sel_rotation.setRange(-360.0, 360.0)
        self.sel_rotation.setDecimals(1)
        self.sel_rotation.setSuffix("\u00b0")
        self.sel_rotation.setFixedWidth(84)
        self.sel_rotation.setKeyboardTracking(False)
        self.sel_rotation.setToolTip(_("Counter-clockwise. You can also drag the round handle above "
                                       "the element (hold Shift for 15\u00b0 steps)."))
        self.sel_rotation.valueChanged.connect(lambda _v: self._selection_field_changed("rotation"))
        row.addWidget(self.sel_rotation)
        for text, angle, tip in (("\u27f2", 90, N_("Rotate 90\u00b0 counter-clockwise")),
                                 ("\u27f3", -90, N_("Rotate 90\u00b0 clockwise"))):
            b = QPushButton(text)
            b.setFixedWidth(36)
            b.setToolTip(_(tip))
            b.clicked.connect(lambda _c=False, a=angle: self.rotate_selected(a))
            row.addWidget(b)
        row.addStretch(1)
        b = QPushButton(_("Delete"))
        b.clicked.connect(self.delete_selected)
        row.addWidget(b)
        g.addLayout(row, 4, 0, 1, 4)
        design_layout.addWidget(self.selection_box)
        design_layout.addStretch(1)

        # --- laser
        box = QGroupBox()
        v = QVBoxLayout(box)
        self.laser_label = QLabel()
        v.addWidget(self.laser_label)
        row = QHBoxLayout()
        self.btn_connect = QPushButton(_("Initialize"))
        self.btn_connect.clicked.connect(self.connect_laser)
        row.addWidget(self.btn_connect)
        b = QPushButton(_("Home"))
        b.clicked.connect(self.home)
        row.addWidget(b)
        b = QPushButton(_("Unlock"))
        b.clicked.connect(self.unlock)
        row.addWidget(b)
        v.addLayout(row)

        # jog pad: arrows move the design origin; corners/centre move the head
        # to that point of the design (the design stays where it is)
        grid = QGridLayout()
        grid.setSpacing(4)
        arrows = {(0, 1): ("up", 0, 1, "Ctrl+Up", N_("Move the laser head up by one step")),
                  (-1, 0): ("left", 1, 0, "Ctrl+Left", N_("Move the laser head left by one step")),
                  (1, 0): ("right", 1, 2, "Ctrl+Right", N_("Move the laser head right by one step")),
                  (0, -1): ("down", 2, 1, "Ctrl+Down", N_("Move the laser head down by one step"))}
        for d, (name, r, c, sc, tip) in arrows.items():
            b = QPushButton()
            b.setIcon(icons.arrow_icon(name))
            b.setIconSize(QSize(34, 34))
            b.setFixedSize(64, 56)
            b.setToolTip("%s (%s)" % (_(tip), sc))
            b.clicked.connect(lambda _checked=False, d=d: self.jog(*d))
            grid.addWidget(b, r, c)
            act = QAction(self)
            act.setShortcut(QKeySequence(sc))
            act.triggered.connect(lambda _checked=False, d=d: self.jog(*d))
            self.addAction(act)
        self.corner_buttons = []
        corners = (("UL", 0, 0, N_("Move the head to the upper left corner of the design"), "Ctrl+7"),
                   ("UR", 0, 2, N_("Move the head to the upper right corner of the design"), "Ctrl+9"),
                   ("CC", 1, 1, N_("Move the head to the centre of the design"), "Ctrl+5"),
                   ("LL", 2, 0, N_("Move the head to the lower left corner of the design"), "Ctrl+1"),
                   ("LR", 2, 2, N_("Move the head to the lower right corner of the design"), "Ctrl+3"))
        for key, r, c, tip, sc in corners:
            b = QPushButton()
            b.setIcon(icons.centre_icon() if key == "CC" else icons.corner_icon(key))
            b.setIconSize(QSize(34, 34))
            b.setFixedSize(64, 56)
            b.setToolTip("%s (%s).\n%s" % (_(tip), sc, _("The design does not move.")))
            b.clicked.connect(lambda _checked=False, k=key: self.move_to_corner(k))
            grid.addWidget(b, r, c)
            self.corner_buttons.append(b)
        pad = QHBoxLayout()
        pad.addStretch(1)
        pad.addLayout(grid)
        pad.addStretch(1)
        v.addLayout(pad)

        self.jog_step = self._spin("jog_step", "len", 0.01, 1000, 2)
        self.jog_step.setToolTip(_("Distance moved by one arrow click"))
        self.jog_step.setFixedWidth(110)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(QLabel(_("Step:")))
        row.addWidget(self.jog_step)
        row.addStretch(1)
        v.addLayout(row)
        self.head_label = QLabel()
        self.head_label.setAlignment(Qt.AlignHCenter)
        v.addWidget(self.head_label)

        # go to an absolute position (from home)
        row = QHBoxLayout()
        row.addWidget(QLabel(_("Go to X")))
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
        self.goto_y.setToolTip(_("Distance down from home"))
        row.addWidget(self.goto_x)
        row.addSpacing(6)
        row.addWidget(QLabel(_("Y")))
        row.addWidget(self.goto_y)
        row.addStretch(1)
        self.btn_goto = QPushButton(_("Go"))
        self.btn_goto.setToolTip(_("Home the head, then move to X/Y (Ctrl+G)"))
        self.btn_goto.clicked.connect(self.goto_position)
        row.addWidget(self.btn_goto)
        v.addLayout(row)

        # test fire (M3 boards)
        self.test_fire_row = QWidget()
        row = QHBoxLayout(self.test_fire_row)
        row.setContentsMargins(0, 0, 0, 0)
        self.btn_test_fire = QPushButton(_("Test fire"))
        self.btn_test_fire.setToolTip(_("Fire the laser briefly (M3 boards)"))
        self.btn_test_fire.clicked.connect(self.test_fire)
        row.addWidget(self.btn_test_fire)
        row.addWidget(self._spin("test_power", "power", 0, 100, 0))
        t = self._spin("test_time", "int", 0, 1000)
        t.setSuffix(" ms")
        t.setFixedWidth(80)
        row.addWidget(t)
        row.addStretch(1)
        v.addWidget(self.test_fire_row)
        laser_layout.addWidget(box)
        laser_layout.addStretch(1)

        # --- operations
        box = QGroupBox(_("Operations"))
        g = QGridLayout(box)
        self.speed_header = QLabel()
        for col, text in enumerate(("", None, N_("Passes"), N_("Power"), N_("Time"))):
            if text is None:
                g.addWidget(self.speed_header, 0, col)
            elif text:
                lbl = QLabel(_(text))
                g.addWidget(lbl, 0, col)
                if text == "Power":
                    self.power_header = lbl
        self.power_widgets = {}
        self.time_labels = {}
        self.include_checks = {}
        self.op_rows = {}          # operation -> widgets of its row
        for row, (label, inc, feed, passes, power, op) in enumerate(OPERATIONS, start=1):
            cb = QCheckBox(_(label))
            cb.setChecked(is_true(self.values.get(inc, "1")))
            cb.toggled.connect(lambda on, k=inc: (self._set_value(k, "1" if on else "0"),
                                                  self.refresh_preview()))
            self.include_checks[op] = cb
            g.addWidget(cb, row, 0)
            widgets = [cb]
            if feed:
                widgets.append(self._spin(feed, "speed", 0.1, 10000))
                widgets[-1].setToolTip(_("Speed"))
                g.addWidget(widgets[-1], row, 1)
            elif op == job.GCODE_CUT:
                cb.setToolTip(_("Paths from a G-code file; speeds come from the file (F words)"))
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
        self.no_ops_label = QLabel(_("Open a design to see its operations."))
        self.no_ops_label.setStyleSheet("color:#757575;")
        g.addWidget(self.no_ops_label, len(OPERATIONS) + 1, 0, 1, 5)
        row = QHBoxLayout()
        self.total_time_label = QLabel()
        row.addWidget(self.total_time_label, 1)
        self.btn_calc_time = QPushButton(_("Calculate raster time"))
        self.btn_calc_time.setToolTip(_("Prepare the raster now to estimate its engraving time"))
        self.btn_calc_time.clicked.connect(self.calculate_raster_time)
        row.addWidget(self.btn_calc_time)
        g.addLayout(row, len(OPERATIONS) + 2, 0, 1, 5)
        layout.addWidget(box)

        # --- run: one compact row
        run = QWidget()
        row = QHBoxLayout(run)
        row.setContentsMargins(0, 4, 0, 0)
        row.setSpacing(6)
        self.btn_trace = QPushButton()
        self.btn_trace.setIcon(icons.trace_icon())
        self.btn_trace.setIconSize(QSize(26, 26))
        self.btn_trace.setFixedSize(46, 46)
        self.btn_trace.setToolTip(_("Trace boundary: move the head around the outline of the design "
                                    "(laser off unless set in Settings), to check where it will be cut"))
        self.btn_trace.clicked.connect(lambda: self.start_job(trace=True))
        row.addWidget(self.btn_trace)
        self.btn_start = QPushButton(_("Start"))
        self.btn_start.setObjectName("start")
        self.btn_start.setFixedHeight(46)
        self.btn_start.setIcon(icons.tabler("player-play", "#ffffff"))
        self.btn_start.setIconSize(QSize(22, 22))
        self.btn_start.setToolTip(_("Start the selected operations") + " (F9)")
        self.btn_start.clicked.connect(lambda: self.start_job())
        row.addWidget(self.btn_start, 1)
        self.btn_pause = QPushButton()
        self.btn_pause.setObjectName("pause")
        self.btn_pause.setIcon(icons.tabler("player-pause"))
        self.btn_pause.setIconSize(QSize(24, 24))
        self.btn_pause.setFixedSize(46, 46)
        self.btn_pause.setToolTip(_("Pause the laser; press again to resume"))
        self.btn_pause.setEnabled(False)
        self.btn_pause.clicked.connect(self.pause_job)
        row.addWidget(self.btn_pause)
        self.btn_stop = QPushButton(_("Stop"))
        self.btn_stop.setObjectName("stop")
        self.btn_stop.setFixedSize(104, 46)
        self.btn_stop.setIcon(icons.tabler("player-stop", "#ffffff"))
        self.btn_stop.setIconSize(QSize(22, 22))
        self.btn_stop.setToolTip(_("Stop the job now") + " (Esc)")
        self.btn_stop.setEnabled(False)
        self.btn_stop.clicked.connect(self.stop_job)
        row.addWidget(self.btn_stop)
        layout.addWidget(run)
        layout.addStretch(1)

        scroll = QScrollArea()
        scroll.setWidget(panel)
        scroll.setWidgetResizable(True)
        self.panel_scroll = scroll
        dock = QDockWidget(_("Job"), self)
        dock.setObjectName("job_dock")
        dock.setFeatures(QDockWidget.NoDockWidgetFeatures)
        dock.setWidget(scroll)
        self.addDockWidget(Qt.LeftDockWidgetArea, dock)
        for key in ("x", "y", "w", "h"):
            self._unit_widgets.append((self.sel_fields[key], "len", None, 1.0))
        self._update_unit_suffixes()

    def _build_status(self):
        self.progress = QProgressBar()
        self.progress.setMaximumWidth(220)
        self.progress.setRange(0, 0)
        self.progress.hide()
        self.statusBar().addPermanentWidget(self.progress)
        self.statusBar().showMessage(_("Ready"))

    # ------------------------------------------------------------ state
    # ------------------------------------------------------------ elements
    @property
    def design(self):
        """The elements compiled into one design (cached until they change)."""
        if self._compiled is None:
            design, origin = compile_layout(self.elements)
            self._compiled = (design or Design(), origin or (0.0, 0.0))
        return self._compiled[0]

    @property
    def origin(self):
        """Bed position where the job starts (top-left of all elements)."""
        self.design
        return self._compiled[1]

    def _layout_changed(self):
        self._compiled = None
        self._update_design_label()
        self._update_power_visibility()
        self.refresh_preview()

    def _units_per_inch(self):
        return 25.4 if self.values.get("units", "mm") == "mm" else 1.0

    def _layout_fits_bed(self):
        if not self.elements:
            return True
        bed_w, bed_h = config.bed_size_inches(self.values)
        xmin = min(e.bounds[0] for e in self.elements)
        xmax = max(e.bounds[1] for e in self.elements)
        ymin = min(e.bounds[2] for e in self.elements)
        ymax = max(e.bounds[3] for e in self.elements)
        tol = 0.002
        return xmin >= -tol and xmax <= bed_w + tol and ymax <= tol and ymin >= -bed_h - tol

    def _keep_on_bed(self, element):
        """Nudge an element back onto the bed if it fits there."""
        bed_w, bed_h = config.bed_size_inches(self.values)
        w, h = element.size
        if w <= bed_w:
            element.x = min(max(element.x, 0.0), bed_w - w)
        if h <= bed_h:
            element.y = max(min(element.y, 0.0), -bed_h + h)

    # ---- undo / redo: snapshots of the element list and placements ----
    def _snapshot(self):
        return (list(self.elements),
                [(e.placement(), e.design, e.shape.copy() if e.shape is not None else None)
                 for e in self.elements],
                self.selected)

    def _checkpoint(self):
        """Call before changing the layout."""
        self._undo.append(self._snapshot())
        del self._undo[:-100]
        self._redo.clear()

    def _restore(self, snap):
        elements, states, selected = snap
        self.elements = list(elements)
        for e, (placement, design, shape) in zip(self.elements, states):
            e.set_placement(placement)
            e.design = design
            e.shape = shape
        self.selected = selected if selected in self.elements else None
        self._compiled = None
        self._layout_changed()
        self._update_tool_options(force=True)

    def undo(self):
        if self._undo and self.worker is None:
            self._redo.append(self._snapshot())
            self._restore(self._undo.pop())

    def redo(self):
        if self._redo and self.worker is None:
            self._undo.append(self._snapshot())
            self._restore(self._redo.pop())

    # ---- grid ----
    def _grid_mm(self):
        try:
            return max(0.0, float(self.values.get("grid_mm", "0") or 0))
        except ValueError:
            return 0.0

    def _grid_size_choice(self):
        return self._grid_mm() or getattr(self, "_last_grid", 5.0)

    def toggle_snap(self, checked):
        self.values["grid_mm"] = _num_text(self._grid_size_choice()) if checked else "0"
        self.refresh_preview()

    def set_grid(self, mm):
        self._last_grid = float(mm)
        self.values["grid_mm"] = _num_text(mm)
        self.act_snap.setChecked(True)
        self.refresh_preview()

    def _snap(self, element):
        g = self._grid_mm() / 25.4
        if g > 0:
            element.x = round(element.x / g) * g
            element.y = round(element.y / g) * g

    # ---- element list ----
    def _update_element_list(self):
        lst = self.element_list
        lst.blockSignals(True)
        lst.clear()
        for e in self.elements:
            item = QListWidgetItem(e.name)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked if e.visible else Qt.Unchecked)
            lst.addItem(item)
        if self.selected in self.elements:
            lst.setCurrentRow(self.elements.index(self.selected))
        lst.blockSignals(False)
        lst.setVisible(len(self.elements) > 1)

    def _element_item_changed(self, item):
        row = self.element_list.row(item)
        if 0 <= row < len(self.elements):
            visible = item.checkState() == Qt.Checked
            if self.elements[row].visible != visible:
                self._checkpoint()
                self.elements[row].visible = visible
                self._layout_changed()

    def _element_row_selected(self, row):
        if 0 <= row < len(self.elements):
            self.selected = self.elements[row]
            self.preview.select_element(self.selected)
            self._update_selection_panel()
            self._update_tool_options()

    # ---- more editing commands ----
    def duplicate_selected(self):
        if self.selected is None or self.worker is not None:
            return
        self._checkpoint()
        e = self.selected.copy()
        e.x += 5 / 25.4
        e.y -= 5 / 25.4
        self._keep_on_bed(e)
        self.elements.append(e)
        self.selected = e
        self._layout_changed()

    def center_on_bed(self):
        """Centre the selected element, or all elements together, on the bed."""
        if not self.elements or self.worker is not None:
            return
        bed_w, bed_h = config.bed_size_inches(self.values)
        self._checkpoint()
        if self.selected is not None:
            self.selected.set_centre(bed_w / 2.0, -bed_h / 2.0)
        else:
            xmin = min(e.bounds[0] for e in self.elements)
            xmax = max(e.bounds[1] for e in self.elements)
            ymin = min(e.bounds[2] for e in self.elements)
            ymax = max(e.bounds[3] for e in self.elements)
            dx = bed_w / 2.0 - (xmin + xmax) / 2.0
            dy = -bed_h / 2.0 - (ymin + ymax) / 2.0
            for e in self.elements:
                e.x += dx
                e.y += dy
        self._layout_changed()

    def _preview_nudged(self, element, dx_mm, dy_mm):
        """Arrow keys in the bed view: move the selected element (screen directions)."""
        if self.worker is not None:
            return
        self._checkpoint()
        sign = -1 if self.job_settings().home_upper_right else 1
        element.x += sign * dx_mm / 25.4
        element.y += dy_mm / 25.4
        self._keep_on_bed(element)
        self._layout_changed()

    def _preview_selected(self, element):
        self.selected = element
        self._update_selection_panel()
        self._update_tool_options()
        lst = self.element_list
        lst.blockSignals(True)
        lst.setCurrentRow(self.elements.index(element) if element in self.elements else -1)
        lst.blockSignals(False)

    def _preview_moved(self, element, dx, dy):
        self._checkpoint()
        element.x += dx
        element.y += dy
        self._snap(element)
        self._keep_on_bed(element)
        self._layout_changed()

    def _preview_scaled(self, element, factor):
        self._checkpoint()
        cx, cy = element.centre
        element.scale_x *= factor
        element.scale_y *= factor
        element.set_centre(cx, cy)
        self._keep_on_bed(element)
        self._layout_changed()

    def _preview_rotated(self, element, degrees):
        self._rotate(element, degrees)

    def _rotate(self, element, degrees):
        self._checkpoint()
        cx, cy = element.centre
        element.rotation = (element.rotation + degrees) % 360
        if abs(element.rotation - round(element.rotation)) < 1e-6:
            element.rotation = float(round(element.rotation)) % 360
        element.set_centre(cx, cy)
        self._keep_on_bed(element)
        self._layout_changed()

    def rotate_selected(self, degrees):
        if self.selected is not None and self.worker is None:
            self._rotate(self.selected, degrees)

    def delete_selected(self):
        if self.selected is None or self.worker is not None:
            return
        self._checkpoint()
        self.elements.remove(self.selected)
        self.selected = None
        self._layout_changed()

    def place_at_head(self):
        """Move all elements together so the design's top-left is at the laser head."""
        if not self.elements or self.worker is not None:
            return
        ox, oy = self.origin
        self._checkpoint()
        for e in self.elements:
            e.x += self.head[0] - ox
            e.y += self.head[1] - oy
        self._layout_changed()

    def _update_selection_panel(self):
        e = self.selected
        self.selection_box.setEnabled(e is not None)
        k = self._units_per_inch()
        values = {"x": 0.0, "y": 0.0, "w": 0.0, "h": 0.0}
        rotation = 0.0
        if e is not None:
            w, h = e.size
            values = {"x": e.x * k, "y": -e.y * k, "w": w * k, "h": h * k}
            rotation = e.rotation if e.rotation <= 180 else e.rotation - 360
            self.sel_name.setText("<b>%s</b>" % e.name)
        else:
            self.sel_name.setText(_("Click an element on the bed to select it."))
        for key, spin in self.sel_fields.items():
            spin.blockSignals(True)
            spin.setValue(values[key])
            spin.blockSignals(False)
        self.sel_rotation.blockSignals(True)
        self.sel_rotation.setValue(rotation)
        self.sel_rotation.blockSignals(False)

    def _selection_field_changed(self, key):
        e = self.selected
        if e is None:
            return
        k = self._units_per_inch()
        if key != "rotation":
            self._checkpoint()
        if key == "x":
            e.x = self.sel_fields["x"].value() / k
        elif key == "y":
            e.y = -self.sel_fields["y"].value() / k
        elif key in ("w", "h"):
            w, h = e.size
            new_w = self.sel_fields["w"].value() / k
            new_h = self.sel_fields["h"].value() / k
            if self.sel_lock.isChecked() and w > 0 and h > 0:
                factor = new_w / w if key == "w" else new_h / h
                new_w, new_h = w * factor, h * factor
            x, y = e.x, e.y                      # keep the top-left corner
            e.set_size(new_w, new_h)
            e.x, e.y = x, y
            self._keep_on_bed(e)
        elif key == "rotation":
            self._rotate(e, self.sel_rotation.value() - (e.rotation if e.rotation <= 180 else e.rotation - 360))
            return
        self._layout_changed()

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
            if unknown and total == 0:
                text = "?"
            else:
                text = format_time(total) + (_(" + raster") if unknown else "")
            self.total_time_label.setText(_("Estimated total: <b>%s</b>") % text)
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
        has = {job.RASTER_ENG: False, job.VECTOR_ENG: False, job.VECTOR_CUT: False, job.GCODE_CUT: False}
        for e in self.elements:
            d = e.design
            has[job.RASTER_ENG] |= d.raster.image is not None
            has[job.VECTOR_ENG] |= bool(d.vector_engrave.ecoords)
            has[job.VECTOR_CUT] |= bool(d.vector_cut.ecoords)
            has[job.GCODE_CUT] |= bool(d.gcode.ecoords)
        return has

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
        self.speed_header.setText(_("Speed (%s)") % speed)
        for w, kind, _key, _sign in self._unit_widgets:
            w.setSuffix(" " + (units if kind == "len" else speed))

    def _reload_spin_values(self):
        """Re-read unit-dependent fields after the units changed."""
        for w, kind, key, sign in self._unit_widgets:
            if key is None:
                continue
            w.blockSignals(True)
            try:
                w.setValue(max(w.minimum(), sign * float(self.values[key])))
            except (KeyError, ValueError):
                pass
            w.blockSignals(False)

    def _update_laser_state(self):
        if self.laser.connected:
            self.laser_label.setText(_("<b style='color:#2e7d32'>Connected</b> (%s)")
                                     % self.values.get("board_name"))
            self.btn_connect.setText(_("Re-initialize"))
        else:
            self.laser_label.setText(_("<b style='color:#c62828'>Not connected</b>"))
            self.btn_connect.setText(_("Initialize"))
        x, y = self.head
        scale = 25.4 if self.values.get("units") == "mm" else 1.0
        self.head_label.setText(_("Head: X %s  Y %s %s") % (_num(x * scale), _num(-y * scale),
                                                            self.values.get("units")))

    def set_busy(self, busy):
        for w in [self.btn_start, self.btn_trace, self.btn_connect, self.btn_goto,
                  self.btn_test_fire, self.btn_calc_time, self.selection_box] + self.corner_buttons:
            w.setEnabled(not busy)
        for a in [self.act_open, self.act_reload, self.act_save_egv, self.act_send_egv,
                  self.act_connect, self.act_release, self.act_home, self.act_unlock,
                  self.act_settings, self.act_goto, self.act_calc_time, self.act_add, self.act_delete,
                  self.act_rot_left, self.act_rot_right, self.act_place_head, self.act_undo,
                  self.act_redo, self.act_duplicate, self.act_center] + list(self.act_corners.values()):
            a.setEnabled(not busy)
        self.btn_stop.setEnabled(busy)
        self.act_stop.setEnabled(busy)
        for a in self.tool_actions.values():
            a.setEnabled(not busy)
        self.tool_options.setEnabled(not busy)
        self.act_start.setEnabled(not busy)
        self.act_trace.setEnabled(not busy)
        self.progress.setVisible(busy)

    def status(self, message, error=False):
        self.statusBar().setStyleSheet("color:#c62828;" if error else "")
        self.statusBar().showMessage(tr_message(message))

    def refresh_preview(self, fit=False):
        try:
            settings = self.job_settings()
        except ValueError as e:
            self.status(str(e), error=True)
            return
        if self.selected not in self.elements:
            self.selected = None
        self.preview.show_layout(self.elements, self.selected, settings, self.values, self.head, fit=fit,
                                 grid_mm=self._grid_mm())
        self._update_element_list()
        self.act_undo.setEnabled(bool(self._undo))
        self.act_redo.setEnabled(bool(self._redo))
        self._update_laser_state()
        self._update_selection_panel()
        self._update_times()

    # ------------------------------------------------------------ design files
    def open_design(self, add=False):
        start = os.path.dirname(self.design_file or self.values.get("designfile", "")) or os.path.expanduser("~")
        title = _("Add design") if add else _("Open design")
        name, _unused = QFileDialog.getOpenFileName(self, title, start, design_filters())
        if name:
            self.load_design(name, add=add)

    def add_design(self):
        self.open_design(add=True)

    def reload_design(self):
        """Reload every element's file, keeping its placement."""
        if not self.elements:
            self.open_design()
            return
        self._checkpoint()
        for e in list(self.elements):
            if e.shape is not None:
                e.design = build_design(e.shape)
                continue
            design = self._load_file(e.source_file, e.load_options)
            if design is None:
                return
            e.design = design
        self._layout_changed()
        self.status(_("Reloaded"))

    def _ask_dxf_units(self):
        unit, ok = QInputDialog.getItem(self, _("DXF units"),
                                        _("The DXF file does not say which units it uses.\nUnits:"),
                                        loaders.DXF_UNITS, loaders.DXF_UNITS.index("Millimeters"),
                                        False)
        return unit if ok else None

    def _ask_svg_scale(self, svg_size, viewbox, inkscape_version):
        q = loaders.SvgScale(svg_size, viewbox, inkscape_version)
        w, h = q.size_mm(q.default_pxpi)
        pxpi, ok = QInputDialog.getDouble(
            self, _("SVG import scale"),
            _("The SVG file does not define its physical size.\n"
            "Pixels per inch (Inkscape 0.92+: 96, older Inkscape: 90, Illustrator: 72).\n"
            "At %g px/in the design is %.1f x %.1f mm.") % (q.default_pxpi, w, h),
            q.default_pxpi, 1.0, 10000.0, 2)
        return q.result(pxpi) if ok else None

    def _ask_image_dpi(self, filename):
        """Ask for the physical size of a bitmap; returns its dpi or None if cancelled."""
        try:
            width, height, file_dpi = loaders.read_image_info(filename)
        except Exception as e:
            QMessageBox.critical(self, _("Could not open design"), tr_message(str(e)))
            return None
        dlg = ImageSizeDialog(width, height, file_dpi, self.values.get("units", "mm"), self)
        if not dlg.exec():
            return None
        return dlg.result_dpi()

    def _load_file(self, filename, options):
        """Load a file into a new Design. options may hold {"dpi": ...} for images.
        Returns the design, or None if loading failed or was cancelled."""
        ext = os.path.splitext(filename)[1].lower()
        design = Design()
        QApplication.setOverrideCursor(Qt.WaitCursor)
        self.status(_("Opening %s") % filename)
        QApplication.processEvents()

        def progress(msg):
            self.status(msg)
            QApplication.processEvents()
        reduced = is_true(self.values.get("reduced_mem", "0"))
        try:
            if ext == ".svg":
                warnings = loaders.load_svg(
                    filename, design,
                    inkscape_path=self.values.get("inkscape_path", ""),
                    inkscape_timeout_s=float(self.values.get("ink_timeout", 3)) * 60.0,
                    reduced_memory=reduced, ask_pxpi=self._ask_svg_scale, progress=progress)
            elif ext == ".dxf":
                warnings = loaders.load_dxf(filename, design, ask_units=self._ask_dxf_units)
            elif ext in loaders.IMAGE_EXTENSIONS:
                warnings = loaders.load_image(filename, design, options["dpi"], reduced_memory=reduced)
            else:
                warnings = loaders.load_gcode(filename, design)
        except loaders.LoadCancelled:
            QApplication.restoreOverrideCursor()
            self.status(_("Loading cancelled"))
            return None
        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.status(_("Could not open %s") % os.path.basename(filename), error=True)
            QMessageBox.critical(self, _("Could not open design"), tr_message(str(e)))
            return None
        QApplication.restoreOverrideCursor()
        for w in warnings:
            QMessageBox.warning(self, _("Design import"), tr_message(w))
        return design

    def load_design(self, filename, add=False):
        """Open a file as a new element at the laser head; replaces all elements unless add."""
        options = {}
        if os.path.splitext(filename)[1].lower() in loaders.IMAGE_EXTENSIONS:
            dpi = self._ask_image_dpi(filename)
            if dpi is None:
                self.status(_("Loading cancelled"))
                return
            options["dpi"] = dpi
        design = self._load_file(filename, options)
        if design is None:
            return
        self._checkpoint()
        is_gcode = bool(design.gcode.ecoords)
        if not add or is_gcode or any(e.design.gcode.ecoords for e in self.elements):
            self.elements = []         # G-code files are not combined with other designs
        element = Element(design, name=os.path.basename(filename), source_file=filename,
                          load_options=options)
        element.x, element.y = self.head
        self._keep_on_bed(element)
        self.elements.append(element)
        self.selected = element
        self.design_file = filename
        self.values["designfile"] = filename
        self._compiled = None
        self._update_design_label()
        self._update_power_visibility()
        self.refresh_preview(fit=not add)
        self.status(_("Opened %s") % filename)
        if not self._layout_fits_bed():
            self.status(_("The design does not fit on the laser bed at this position."), error=True)

    def _update_design_label(self):
        if not self.elements:
            self.design_label.setText(_("No design loaded"))
            return
        parts = []
        has = self._design_has()
        for op, text in ((job.RASTER_ENG, _("raster")), (job.VECTOR_ENG, _("vector engrave")),
                         (job.VECTOR_CUT, _("vector cut")), (job.GCODE_CUT, _("g-code"))):
            if has[op]:
                parts.append(text)
        xmin = min(e.bounds[0] for e in self.elements)
        xmax = max(e.bounds[1] for e in self.elements)
        ymin = min(e.bounds[2] for e in self.elements)
        ymax = max(e.bounds[3] for e in self.elements)
        title = self.elements[0].name if len(self.elements) == 1 else \
            ngettext("%d element", "%d elements", len(self.elements)) % len(self.elements)
        text = "<b>%s</b><br>%s<br>%s" % (
            title, _("%s \u00d7 %s mm") % (_num((xmax - xmin) * 25.4), _num((ymax - ymin) * 25.4)),
            ", ".join(parts) or _("empty"))
        if not self._layout_fits_bed():
            text += "<br><b style='color:#c62828'>%s</b>" % _("Outside the laser bed!")
        self.design_label.setText(text)

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
        if "language" in changed:
            QMessageBox.information(self, _("Language"),
                                    _("The new language will be used after restarting Kerfly."))
        if changed & RASTER_KEYS:
            for e in self.elements:
                e.design.raster.reset_path()
            self._compiled = None
        if changed & RELOAD_KEYS and self.elements:
            self.reload_design()
        self.refresh_preview()
        self.status(_("Settings changed (use File → Save settings as default to keep them)"))

    def save_settings(self):
        path = config.user_config_path()
        try:
            config.write_settings_file(path, self.values, "0.71 (Kerfly %s)" % __version__)
        except OSError as e:
            self.status(_("Could not save settings: %s") % e, error=True)
            return
        self.status(_("Settings saved to %s") % path)

    # ------------------------------------------------------------ laser
    def _laser_call(self, func, ok_message):
        if not self.laser.connected:
            self.status(_("Laser is not initialized."), error=True)
            return False
        try:
            func()
        except Exception as e:
            self.status(str(e), error=True)
            return False
        self.status(ok_message)
        return True

    def connect_laser(self):
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            self.laser.connect(init_home=is_true(self.values.get("init_home", "1")))
            self.head = (0.0, 0.0)
            self.status(_("Laser initialized"))
        except LaserError as e:
            self.status(str(e), error=True)
        except Exception as e:
            self.status(_("Unknown USB error: %s") % e, error=True)
        finally:
            QApplication.restoreOverrideCursor()
        self.refresh_preview()

    def release_laser(self):
        try:
            self.laser.release()
            self.status(_("USB released"))
        except Exception as e:
            self.status(str(e), error=True)
        self._update_laser_state()

    def home(self):
        if self.laser.connected and not self._laser_call(self.laser.home, _("Homed")):
            return
        self.head = (0.0, 0.0)
        self.refresh_preview()

    def unlock(self):
        self._laser_call(self.laser.unlock, _("Rail unlocked"))

    def unfreeze(self):
        self._laser_call(self.laser.unfreeze, _("Unfreeze complete"))

    def jog(self, dirx, diry):
        """Move by one jog step in the given direction (+y = up)."""
        try:
            step = float(self.values["jog_step"])
        except ValueError as e:
            self.status(str(e), error=True)
            return
        self.move_by(dirx * step, diry * step)

    def move_by(self, dx_units, dy_units):
        """Move the laser head by (dx, dy) in the current units (+y = up, +x = right on screen)."""
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
        x, y = clamp_head_position(self.head[0], self.head[1], dx, dy, bed_w, bed_h)
        self.move_head_to(x, y)

    def move_head_to(self, x, y):
        """Move the laser head to a bed position (inches, y <= 0). Returns True on success."""
        try:
            settings = self.job_settings()
        except ValueError as e:
            self.status(str(e), error=True)
            return False
        dx = round((x - self.head[0]) * 1000.0)
        dy = round((y - self.head[1]) * 1000.0)
        if self.laser.connected and (dx or dy):
            try:
                self.laser.rapid_move(dx, dy, settings, self.send_options())
            except Exception as e:
                self.status(_("Rapid move failed: %s") % e, error=True)
                return False
        self.head = (self.head[0] + dx / 1000.0, self.head[1] + dy / 1000.0)
        self.refresh_preview()
        return True

    def move_to_corner(self, corner):
        """Move the head to a corner or the centre of the design (the design stays)."""
        if self.worker is not None or not self.elements:
            return
        try:
            settings = self.job_settings()
            bed_w, bed_h = config.bed_size_inches(self.values)
        except ValueError as e:
            self.status(str(e), error=True)
            return
        bounds = self.design.get_bounds(settings.rotate)
        ox, oy = self.origin
        offset = corner_offset(corner, bounds, settings.home_upper_right, (ox, oy), bed_w, bed_h)
        if offset is None:
            self.status(_("That corner of the design is outside the laser bed."), error=True)
            return
        x, y = clamp_head_position(ox, oy, offset[0] / 1000.0, offset[1] / 1000.0, bed_w, bed_h)
        self.move_head_to(x, y)

    def goto_position(self):
        """Home, then move to the X/Y set in the panel (distance from home, Y downwards)."""
        if self.worker is not None:
            return
        x, y = self.goto_x.value(), self.goto_y.value()
        if self.laser.connected and not self._laser_call(self.laser.home, _("Homed")):
            return
        self.head = (0.0, 0.0)
        self.move_by(x, -y)

    def test_fire(self):
        if not self.laser.connected:
            self.status(_("Laser is not initialized."), error=True)
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
                         _("Test fire: %.0f%% for %d ms") % (power, ms))

    def calculate_raster_time(self):
        if self.worker is not None or self.design.raster.image is None:
            return
        try:
            settings = self.job_settings()
        except ValueError as e:
            self.status(str(e), error=True)
            return
        self._run_worker(RasterPrepareWorker(self.design, settings, parent=self),
                         _("Preparing raster…"))

    def send_egv_file(self):
        if self.worker is not None:
            return
        if not self.laser.connected:
            self.status(_("Laser is not initialized."), error=True)
            return
        start = os.path.dirname(self.design_file) or os.path.expanduser("~")
        name, _unused = QFileDialog.getOpenFileName(self, _("Send EGV file"), start,
                                              _("EGV files (*.egv *.EGV);;All files (*)"))
        if not name:
            return
        try:
            egv = egvfile.read_egv_file(name)
            settings = self.job_settings()
            send_options = self.send_options()
        except (OSError, ValueError) as e:
            self.status(_("Could not read %s: %s") % (os.path.basename(name), e), error=True)
            return
        passes = 1
        if not egv.has_end_position:
            passes, ok = QInputDialog.getInt(self, _("Send EGV file"), _("Number of passes:"), 1, 1, 100)
            if not ok:
                return
        # the loaded design is not what is being cut: clear it, as K40 Whisperer does
        self._checkpoint()
        self.elements = []
        self.selected = None
        self.design_file = name
        self._layout_changed()
        self._run_worker(EgvSendWorker(egv, passes, self.laser, settings, send_options, parent=self),
                         _("Sending %s…") % os.path.basename(name))

    # ------------------------------------------------------------ jobs
    def selected_operation(self):
        d = self.design
        has = {job.RASTER_ENG: d.raster.image is not None, job.VECTOR_ENG: bool(d.vector_engrave.ecoords),
               job.VECTOR_CUT: bool(d.vector_cut.ecoords), job.GCODE_CUT: bool(d.gcode.ecoords)}
        ops = [op for *_row, op in OPERATIONS if self.include_checks[op].isChecked() and has[op]]
        return "+".join(ops)

    def start_job(self, output_file=None, trace=False):
        if self.worker is not None:
            return
        op = job.TRACE_ENG if trace else self.selected_operation()
        if not op:
            self.status(_("Nothing to do: load a design and select at least one operation."), error=True)
            return
        if output_file is None and not self.laser.connected:
            self.status(_("Laser is not initialized."), error=True)
            return
        try:
            settings = self.job_settings()
            send_options = self.send_options()
        except ValueError as e:
            self.status(str(e), error=True)
            return
        if not self._layout_fits_bed():
            self.status(_("The design does not fit on the laser bed at this position."), error=True)
            return
        if output_file is None and self.head != self.origin:
            # the job starts where the head is: first move it to the design
            if not self.move_head_to(*self.origin):
                return
        self._run_worker(JobWorker(self.design, settings, op,
                                   laser=None if output_file else self.laser,
                                   output_file=output_file, send_options=send_options,
                                   parent=self), _("Preparing job\u2026"))

    def _run_worker(self, worker, message):
        self.worker = worker
        self._set_paused(False)
        worker.progress.connect(self.status)
        worker.paused.connect(self._job_paused)
        worker.finished_job.connect(self._job_finished)
        self.set_busy(True)
        self.status(message)
        worker.start()

    def save_egv(self):
        base = os.path.splitext(self.design_file)[0] if self.design_file else os.path.expanduser("~/out")
        name, _unused = QFileDialog.getSaveFileName(self, _("Save EGV file"), base + ".EGV", _("EGV files (*.EGV *.egv)"))
        if name:
            self.start_job(output_file=name)

    def stop_job(self):
        if self.worker is not None:
            self.status(_("Stopping\u2026"))
            self.worker.request_stop()

    def pause_job(self):
        """Pause the running laser job, or resume it if it is paused."""
        if self.worker is None or self.worker.laser is None:
            return
        if self._paused:
            self.worker.resume()
            self._set_paused(False)
            self.status(_("Resumed"))
        else:
            self.btn_pause.setEnabled(False)          # until the board confirms the pause
            self.status(_("Pausing\u2026"))
            self.worker.request_pause()

    def _job_paused(self):
        self._set_paused(True)
        self.status(_("Paused. Press the pause button again to continue, or Stop to end the job."))

    def _set_paused(self, paused):
        self._paused = paused
        self.btn_pause.setEnabled(self.worker is not None and self.worker.laser is not None)
        self.btn_pause.setIcon(icons.tabler("player-play" if paused else "player-pause",
                                            "#2e7d32" if paused else "#2b2f36"))
        self.btn_pause.setToolTip(_("Resume the job") if paused else _("Pause the laser; press again to resume"))

    def _job_finished(self, ok, message):
        was_laser_job = isinstance(self.worker, (JobWorker, EgvSendWorker)) and self.worker.laser is not None
        self.worker.wait()
        self.worker = None
        self._set_paused(False)
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
            self, _("About Kerfly"),
            _("<h3>Kerfly %s</h3>"
            "<p>Laser cutter control software for K40 lasers with Lihuiyu M2 Nano boards.</p>"
            "<p>Based on <a href='https://www.scorchworks.com/K40whisperer/k40whisperer.html'>"
            "K40 Whisperer</a> by Scorch.</p>"
            "<p>Free software under the GNU General Public License v3 or later.<br>"
            "<a href='https://github.com/cyryllo/Kerfly'>github.com/cyryllo/Kerfly</a></p>") % __version__)

    def closeEvent(self, event):
        if self.worker is not None:
            if QMessageBox.question(self, _("Job running"),
                                    _("A job is running. Stop it and quit?")) != QMessageBox.Yes:
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
