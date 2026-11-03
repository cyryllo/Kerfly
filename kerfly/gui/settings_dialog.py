"""
Settings dialog, built from a declarative list of fields.

Copyright (C) 2026 Kerfly contributors
Licensed under the GNU General Public License v3 or later. See LICENSE.
"""
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox,
                               QFileDialog, QFormLayout, QHBoxLayout, QLineEdit, QPushButton,
                               QSpinBox, QTabWidget, QVBoxLayout, QWidget)

from kerfly.core.config import BOARD_NAMES, is_true

# (key, label, kind, options). kinds: bool, float, int, choice, path
TABS = [
    ("Machine", [
        ("board_name", "Controller board", "choice", BOARD_NAMES),
        ("units", "Units", "choice", ["mm", "in"]),
        ("LaserXsize", "Bed width", "float", (1, 5000, 1, "len")),
        ("LaserYsize", "Bed height", "float", (1, 5000, 1, "len")),
        ("HomeUR", "Home is in the upper right corner", "bool", None),
        ("init_home", "Home the head when initializing", "bool", None),
        ("post_home", "Unlock rail after a job", "bool", None),
        ("post_beep", "Beep after a job", "bool", None),
        ("LaserXscale", "X scale factor", "float", (0.5, 2, 4, None)),
        ("LaserYscale", "Y scale factor", "float", (0.5, 2, 4, None)),
        ("show_power", "M3 board: set power per operation", "bool", None),
        ("max_power", "M3 board: maximum power (%)", "float", (0, 100, 1, None)),
    ]),
    ("Raster", [
        ("halftone", "Halftone (dither) grayscale images", "bool", None),
        ("ht_size", "Halftone resolution (dpi)", "choice", ["1000", "500", "333", "250", "200", "167", "143", "125"]),
        ("negate", "Invert raster colors", "bool", None),
        ("mirror", "Mirror design", "bool", None),
        ("rotate", "Rotate design 90°", "bool", None),
        ("engraveUP", "Engrave bottom to top", "bool", None),
        ("rast_step", "Scan line step (in)", "float", (0.001, 0.063, 3, None)),
        ("bezier_M1", "Levels curve slope, dark end", "float", (0, 10, 2, None)),
        ("bezier_M2", "Levels curve slope, light end", "float", (0, 10, 2, None)),
        ("bezier_weight", "Levels curve weight", "float", (0, 10, 2, None)),
    ]),
    ("Vector", [
        ("inside_first", "Cut inside shapes first", "bool", None),
        ("trace_w_laser", "Boundary trace with laser on", "bool", None),
        ("trace_gap", "Boundary trace gap", "float", (0, 100, 1, "len")),
        ("trace_speed", "Boundary trace speed", "float", (0.1, 1000, 1, "speed")),
    ]),
    ("Rotary", [
        ("rotary", "Rotary attachment in use", "bool", None),
        ("LaserRscale", "Rotary scale factor", "float", (0.01, 100, 4, None)),
        ("rapid_feed", "Rotary rapid speed (0 = default)", "float", (0, 1000, 1, "speed")),
    ]),
    ("Advanced", [
        ("inkscape_path", "Inkscape executable", "path", None),
        ("ink_timeout", "Inkscape timeout (minutes)", "float", (0.1, 60, 1, None)),
        ("reduced_mem", "Reduced memory use (500 dpi raster)", "bool", None),
        ("pre_pr_crc", "Prepare USB data before sending", "bool", None),
        ("wait", "Wait for the laser to finish", "bool", None),
        ("t_timeout", "USB timeout (ms)", "int", (10, 10000)),
        ("n_timeouts", "USB retries", "int", (1, 1000)),
    ]),
]

# settings whose change invalidates the computed raster lines / path order
RASTER_KEYS = {"halftone", "ht_size", "negate", "mirror", "rotate", "rast_step", "bezier_M1",
               "bezier_M2", "bezier_weight", "LaserXscale", "LaserYscale", "LaserRscale", "rotary"}
RELOAD_KEYS = {"inside_first", "reduced_mem"}


class SettingsDialog(QDialog):
    def __init__(self, values, parent=None, tab=0):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.values = dict(values)
        self._getters = {}
        units = self.values.get("units", "mm")
        len_unit = units
        speed_unit = "mm/s" if units == "mm" else "in/min"

        tabs = QTabWidget()
        for title, fields in TABS:
            page = QWidget()
            form = QFormLayout(page)
            for key, label, kind, opt in fields:
                widget, getter = self._make_field(key, kind, opt, len_unit, speed_unit)
                form.addRow(label, widget)
                self._getters[key] = getter
            tabs.addTab(page, title)
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
            edit.setPlaceholderText("found automatically")
            browse = QPushButton("Browse…")

            def pick():
                name, _ = QFileDialog.getOpenFileName(self, "Inkscape executable", edit.text())
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
