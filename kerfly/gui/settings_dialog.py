"""
Settings dialog, built from a declarative list of fields.

Copyright (C) 2026 Kerfly contributors
Licensed under the GNU General Public License v3 or later. See LICENSE.
"""
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox,
                               QFileDialog, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
                               QSpinBox, QTabWidget, QVBoxLayout, QWidget)

from kerfly.core.config import BOARD_NAMES, is_true
from kerfly.i18n import LANGUAGES, N_, _

# (key, label, kind, options). kinds: bool, float, int, choice, path
TABS = [
    (N_("Machine"), [
        ("board_name", N_("Controller board"), "choice", BOARD_NAMES),
        ("units", N_("Units"), "choice", ["mm", "in"]),
        ("LaserXsize", N_("Bed width"), "float", (1, 5000, 1, "len")),
        ("LaserYsize", N_("Bed height"), "float", (1, 5000, 1, "len")),
        ("HomeUR", N_("Home is in the upper right corner"), "bool", None),
        ("init_home", N_("Home the head when initializing"), "bool", None),
        ("post_home", N_("Unlock rail after a job"), "bool", None),
        ("post_beep", N_("Beep after a job"), "bool", None),
        ("LaserXscale", N_("X scale factor"), "float", (0.5, 2, 4, None)),
        ("LaserYscale", N_("Y scale factor"), "float", (0.5, 2, 4, None)),
        ("show_power", N_("M3 board: set power per operation"), "bool", None),
        ("max_power", N_("M3 board: maximum power (%)"), "float", (0, 100, 1, None)),
    ]),
    (N_("Raster"), [
        ("halftone", N_("Halftone (dither) grayscale images"), "bool", None),
        ("ht_size", N_("Halftone resolution (dpi)"), "choice", ["1000", "500", "333", "250", "200", "167", "143", "125"]),
        ("negate", N_("Invert raster colors"), "bool", None),
        ("mirror", N_("Mirror design"), "bool", None),
        ("rotate", N_("Rotate design 90°"), "bool", None),
        ("engraveUP", N_("Engrave bottom to top"), "bool", None),
        ("rast_step", N_("Scan line step (in)"), "float", (0.001, 0.063, 3, None)),
        ("bezier_M1", N_("Levels curve slope, dark end"), "float", (0, 10, 2, None)),
        ("bezier_M2", N_("Levels curve slope, light end"), "float", (0, 10, 2, None)),
        ("bezier_weight", N_("Levels curve weight"), "float", (0, 10, 2, None)),
    ]),
    (N_("Vector"), [
        ("inside_first", N_("Cut inside shapes first"), "bool", None),
        ("trace_w_laser", N_("Boundary trace with laser on"), "bool", None),
        ("trace_rect", N_("Boundary trace as a rectangle (off: along the outline of the design)"), "bool", None),
        ("trace_gap", N_("Boundary trace gap"), "float", (0, 100, 1, "len")),
        ("trace_speed", N_("Boundary trace speed"), "float", (0.1, 1000, 1, "speed")),
    ]),
    (N_("View"), [
        ("grid_mm", N_("Snap grid (mm, 0 = off)"), "float", (0, 100, 1, None)),
        ("snap_objects", N_("Snap to other objects"), "bool", None),
        ("follow_head", N_("The design follows the laser head"), "bool", None),
    ]),
    (N_("Rotary"), [
        ("rotary", N_("Rotary attachment in use"), "bool", None),
        ("LaserRscale", N_("Rotary scale factor"), "float", (0.01, 100, 4, None)),
        ("rapid_feed", N_("Rotary rapid speed (0 = default)"), "float", (0, 1000, 1, "speed")),
    ]),
    (N_("Advanced"), [
        ("language", N_("Language (applies after restart)"), "language", None),
        ("use_inkscape", N_("Use Inkscape for SVG files when installed (otherwise built-in)"), "bool", None),
        ("inkscape_path", N_("Inkscape executable"), "path", None),
        ("ink_timeout", N_("Inkscape timeout (minutes)"), "float", (0.1, 60, 1, None)),
        ("reduced_mem", N_("Reduced memory use (500 dpi raster)"), "bool", None),
        ("pre_pr_crc", N_("Prepare USB data before sending"), "bool", None),
        ("wait", N_("Wait for the laser to finish"), "bool", None),
        ("t_timeout", N_("USB timeout (ms)"), "int", (10, 10000)),
        ("n_timeouts", N_("USB retries"), "int", (1, 1000)),
    ]),
]

# settings whose change invalidates the computed raster lines / path order
RASTER_KEYS = {"halftone", "ht_size", "negate", "mirror", "rotate", "rast_step", "bezier_M1",
               "bezier_M2", "bezier_weight", "LaserXscale", "LaserYscale", "LaserRscale", "rotary"}
RELOAD_KEYS = {"inside_first", "reduced_mem", "use_inkscape"}


class SettingsDialog(QDialog):
    def __init__(self, values, parent=None, tab=0):
        super().__init__(parent)
        self.setWindowTitle(_("Settings"))
        self.values = dict(values)
        self._getters = {}
        units = self.values.get("units", "mm")
        len_unit = units
        speed_unit = "mm/s" if units == "mm" else "in/min"

        tabs = QTabWidget()
        fm = self.fontMetrics()
        # one label column width for every tab, so fields line up when switching tabs
        label_width = max(fm.horizontalAdvance(_(label)) for _t, fields in TABS
                          for _k, label, kind, _o in fields if kind != "bool") + 12
        for title, fields in TABS:
            page = QWidget()
            grid = QGridLayout(page)
            grid.setColumnMinimumWidth(0, label_width)
            grid.setColumnStretch(2, 1)
            grid.setHorizontalSpacing(8)
            for row, (key, label, kind, opt) in enumerate(fields):
                widget, getter = self._make_field(key, kind, opt, len_unit, speed_unit)
                if kind == "bool":
                    widget.setText(_(label))          # the text sits right next to the box
                    grid.addWidget(widget, row, 0, 1, 3)
                else:
                    grid.addWidget(QLabel(_(label)), row, 0)
                    span = 2 if kind == "path" else 1
                    grid.addWidget(widget, row, 1, 1, span)
                self._getters[key] = getter
            grid.setRowStretch(len(fields), 1)
            tabs.addTab(page, _(title))
        tabs.setCurrentIndex(tab)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addWidget(tabs)
        layout.addWidget(buttons)

    def _make_field(self, key, kind, opt, len_unit, speed_unit):
        value = self.values.get(key, "")
        if kind == "bool":
            w = QCheckBox()
            w.setChecked(is_true(value))
            return w, lambda: "1" if w.isChecked() else "0"
        if kind == "language":
            w = QComboBox()
            w.addItem(_("System default"), "")
            for code, name in LANGUAGES.items():
                w.addItem(name, code)
            index = w.findData(value)
            w.setCurrentIndex(max(0, index))
            return w, lambda: w.currentData()
        if kind == "choice":
            w = QComboBox()
            w.addItems(opt)
            if value not in opt:
                w.addItem(str(value))
            w.setCurrentText(str(value))
            return w, w.currentText
        if kind == "int":
            w = QSpinBox()
            w.setRange(*opt)
            w.setValue(int(float(value or 0)))
            return w, lambda: str(w.value())
        if kind == "float":
            lo, hi, decimals, unit = opt
            w = QDoubleSpinBox()
            w.setRange(lo, hi)
            w.setDecimals(decimals)
            if unit == "len":
                w.setSuffix(" " + len_unit)
            elif unit == "speed":
                w.setSuffix(" " + speed_unit)
            try:
                w.setValue(float(value))
            except ValueError:
                pass
            return w, lambda: ("%." + str(decimals) + "f") % w.value()
        if kind == "path":
            box = QWidget()
            row = QHBoxLayout(box)
            row.setContentsMargins(0, 0, 0, 0)
            edit = QLineEdit(str(value))
            edit.setPlaceholderText(_("found automatically"))
            edit.setMinimumWidth(edit.fontMetrics().averageCharWidth() * 36)
            browse = QPushButton(_("Browse…"))

            def pick():
                name, _unused = QFileDialog.getOpenFileName(self, _("Inkscape executable"), edit.text())
                if name:
                    edit.setText(name)
            browse.clicked.connect(pick)
            row.addWidget(edit)
            row.addWidget(browse)
            return box, edit.text
        raise ValueError(kind)

    def result_values(self):
        """(new values, set of changed keys)."""
        new = dict(self.values)
        changed = set()
        for key, getter in self._getters.items():
            val = getter()
            if str(self.values.get(key, "")) != val:
                # numeric fields: ignore pure formatting differences
                try:
                    if float(self.values.get(key, "nan")) == float(val):
                        continue
                except ValueError:
                    pass
                new[key] = val
                changed.add(key)
        return new, changed
