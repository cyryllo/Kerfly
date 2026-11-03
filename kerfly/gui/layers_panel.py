"""
Layers panel (left side): one row per layer with colour, name, speed, passes,
power (M3 boards) and estimated time; material choice above the list.

Copyright (C) 2026 Kerfly contributors
Licensed under the GNU General Public License v3 or later. See LICENSE.
"""
from PySide6.QtCore import QSize, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QCheckBox, QColorDialog, QComboBox, QDoubleSpinBox, QGridLayout,
                               QHBoxLayout, QLabel, QLineEdit, QMenu, QPushButton, QSpinBox,
                               QToolButton, QVBoxLayout, QWidget)

from kerfly.core.layers import CUT, ENGRAVE, GCODE, RASTER
from kerfly.gui import icons
from kerfly.gui.sizing import fit_spin
from kerfly.i18n import N_, _

KIND_NAMES = {RASTER: N_("Raster engrave"), ENGRAVE: N_("Vector engrave"), CUT: N_("Vector cut"),
              GCODE: N_("G-code")}


def _num_text(v):
    return ("%.4f" % v).rstrip("0").rstrip(".")


class ColorButton(QToolButton):
    def __init__(self, color, parent=None):
        super().__init__(parent)
        self.setFixedSize(18, 18)
        self.set_color(color)
        self.setToolTip(_("Layer colour; click to change"))

    def set_color(self, color):
        self.color = color
        self.setStyleSheet("QToolButton { background: %s; border: 1px solid #555; border-radius: 3px; }" % color)


class LayersPanel(QWidget):
    """Signals: changed(layer) when a layer's settings change; structure_changed()
    when layers are added, removed, renamed or recoloured; material_chosen(index);
    manage_materials(); calc_raster()."""
    changed = Signal(object)
    structure_changed = Signal()
    material_chosen = Signal(int)
    manage_materials = Signal()
    add_layer = Signal(str)
    remove_layer = Signal(object)
    calc_raster = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(4)
        top = QHBoxLayout()
        top.addWidget(QLabel(_("Material:")))
        self.material = QComboBox()
        self.material.setToolTip(_("Choose a material to set the speed, passes and power of all layers"))
        self.material.activated.connect(self._material_activated)
        top.addWidget(self.material, 1)
        manage = QToolButton()
        manage.setIcon(icons.tabler("book"))
        manage.setIconSize(QSize(18, 18))
        manage.setToolTip(_("Material library: add, edit and delete materials"))
        manage.clicked.connect(self.manage_materials.emit)
        top.addWidget(manage)
        v.addLayout(top)
        self.grid_box = QWidget()
        self.grid = QGridLayout(self.grid_box)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setHorizontalSpacing(4)
        self.grid.setVerticalSpacing(3)
        v.addWidget(self.grid_box)
        bottom = QHBoxLayout()
        self.total_label = QLabel()
        bottom.addWidget(self.total_label, 1)
        self.add_button = QToolButton()
        self.add_button.setIcon(icons.tabler("plus"))
        self.add_button.setIconSize(QSize(18, 18))
        self.add_button.setToolTip(_("Add a layer"))
        self.add_button.setPopupMode(QToolButton.InstantPopup)
        menu = QMenu(self.add_button)
        for kind in (CUT, ENGRAVE, RASTER):
            menu.addAction(_(KIND_NAMES[kind]), lambda k=kind: self.add_layer.emit(k))
        self.add_button.setMenu(menu)
        bottom.addWidget(self.add_button)
        v.addLayout(bottom)
        self.rows = {}
        self.speed_unit = "mm/s"
        self.show_power = False

    # ---- materials --------------------------------------------------------
    def set_materials(self, names, current=-1):
        self.material.blockSignals(True)
        self.material.clear()
        self.material.addItem(_("(own settings)"))
        for n in names:
            self.material.addItem(n)
        self.material.setCurrentIndex(current + 1)
        self.material.blockSignals(False)

    def _material_activated(self, index):
        if index > 0:
            self.material_chosen.emit(index - 1)

    def clear_material(self):
        self.material.setCurrentIndex(0)

    # ---- rows ----------------------------------------------------------------
    def rebuild(self, layers, has_data, removable, speed_unit, show_power, gcode_file):
        """has_data(layer) -> bool; removable(layer) -> bool."""
        self.speed_unit = speed_unit
        self.show_power = show_power
        while self.grid.count():
            w = self.grid.takeAt(0).widget()
            if w is not None:
                w.hide()
                w.setParent(None)
                w.deleteLater()
        headers = ["", "", _("Speed (%s)") % speed_unit, _("Passes"), _("Power") if show_power else "", _("Time"), ""]
        for col, text in enumerate(headers):
            if text:
                self.grid.addWidget(QLabel(text), 0, col)
        self.rows = {}
        row = 1
        for layer in layers:
            if layer.kind == GCODE and not gcode_file:
                continue
            if layer.kind != GCODE and gcode_file:
                continue
            data = has_data(layer)
            if not data and not removable(layer):
                continue                        # default layer with nothing on it: hide
            self._add_row(row, layer, data, removable(layer))
            row += 1
        if row == 1:
            hint = QLabel(_("Open a design to see its layers."))
            hint.setStyleSheet("color:#757575;")
            self.grid.addWidget(hint, 1, 0, 1, 7)
        self.add_button.setEnabled(not gcode_file)

    def _add_row(self, row, layer, has_data, removable):
        widgets = {}
        cb = QCheckBox()
        cb.setChecked(layer.enabled)
        cb.setToolTip(_("Include this layer in the job"))
        cb.toggled.connect(lambda on, l=layer: self._set(l, "enabled", on))
        self.grid.addWidget(cb, row, 0)
        name_box = QWidget()
        h = QHBoxLayout(name_box)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(4)
        color = ColorButton(layer.color)
        color.clicked.connect(lambda _c=False, l=layer, b=color: self._pick_color(l, b))
        h.addWidget(color)
        name = QLineEdit(layer.name)
        name.setFrame(False)
        name.setObjectName("layer_name")
        fm = name.fontMetrics()
        name.setMinimumWidth(max(fm.horizontalAdvance(layer.name), fm.horizontalAdvance(_("Raster engrave"))) + 12)
        name.setToolTip(_("Layer name; click to rename"))
        name.editingFinished.connect(lambda l=layer, e=name: self._rename(l, e.text()))
        h.addWidget(name, 1)
        self.grid.addWidget(name_box, row, 1)
        if layer.kind != GCODE:
            speed = QDoubleSpinBox()
            speed.setRange(0.1, 10000)
            speed.setDecimals(1)
            speed.setSuffix(" " + self.speed_unit)
            speed.setValue(layer.speed)
            fit_spin(speed, 9999.9)
            speed.setKeyboardTracking(False)
            speed.valueChanged.connect(lambda v, l=layer: self._set(l, "speed", v))
            self.grid.addWidget(speed, row, 2)
            widgets["speed"] = speed
        else:
            name.setToolTip(_("Paths from a G-code file; speeds come from the file (F words)"))
        passes = QSpinBox()
        passes.setRange(1, 100)
        passes.setValue(layer.passes)
        fit_spin(passes, 100)
        passes.setKeyboardTracking(False)
        passes.valueChanged.connect(lambda v, l=layer: self._set(l, "passes", v))
        self.grid.addWidget(passes, row, 3)
        if self.show_power:
            power = QDoubleSpinBox()
            power.setRange(0, 100)
            power.setDecimals(0)
            power.setSuffix(" %")
            power.setValue(layer.power * 100.0)
            fit_spin(power, 100)
            power.setKeyboardTracking(False)
            power.valueChanged.connect(lambda v, l=layer: self._set(l, "power", v / 100.0))
            self.grid.addWidget(power, row, 4)
        time_cell = QWidget()
        th = QHBoxLayout(time_cell)
        th.setContentsMargins(0, 0, 0, 0)
        th.setSpacing(0)
        time_label = QLabel("")
        th.addWidget(time_label)
        calc = None
        if layer.kind == RASTER:
            calc = QPushButton()
            calc.setIcon(icons.tabler("calculator"))
            calc.setIconSize(QSize(18, 18))
            calc.setFixedSize(28, 28)
            calc.setToolTip(_("Calculate raster time: prepare the raster now to estimate its engraving time"))
            calc.clicked.connect(self.calc_raster.emit)
            calc.hide()
            th.addWidget(calc)
        th.addStretch(1)
        time_cell.setMinimumWidth(max(60, time_label.fontMetrics().horizontalAdvance("0:00:00") + 10))
        self.grid.addWidget(time_cell, row, 5)
        if removable:
            rm = QToolButton()
            rm.setIcon(icons.tabler("trash", "#c62828"))
            rm.setIconSize(QSize(16, 16))
            rm.setAutoRaise(True)
            rm.setToolTip(_("Delete this layer (its parts go back to the default layer)"))
            rm.clicked.connect(lambda _c=False, l=layer: self.remove_layer.emit(l))
            self.grid.addWidget(rm, row, 6)
        for w in (cb, name_box, passes):
            w.setEnabled(has_data or removable)
        self.rows[layer.id] = {"time": time_label, "calc": calc, **widgets}

    def set_times(self, times, format_time):
        """times: {layer.id: seconds or None}."""
        for layer_id, row in self.rows.items():
            t = times.get(layer_id, 0)
            unknown = layer_id in times and t is None
            row["time"].setText("" if unknown or layer_id not in times else format_time(t))
            row["time"].setVisible(not unknown)
            if row["calc"] is not None:
                row["calc"].setVisible(unknown)

    def set_speed(self, layer, speed):
        row = self.rows.get(layer.id)
        if row and "speed" in row:
            row["speed"].blockSignals(True)
            row["speed"].setValue(speed)
            row["speed"].blockSignals(False)

    # ---- edits ----------------------------------------------------------------
    def _set(self, layer, attr, value):
        setattr(layer, attr, value)
        if attr in ("speed", "passes", "power"):
            self.clear_material()
        self.changed.emit(layer)

    def _rename(self, layer, text):
        text = text.strip()
        if text and text != layer.name:
            layer.name = text
            self.structure_changed.emit()

    def _pick_color(self, layer, button):
        c = QColorDialog.getColor(QColor(layer.color), self, _("Layer colour"))
        if c.isValid():
            layer.color = c.name()
            button.set_color(layer.color)
            self.structure_changed.emit()
