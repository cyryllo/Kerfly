"""
Material library dialog: list of materials on the left, the selected
material's cut / outline engrave / raster settings on the right.

Copyright (C) 2026 Kerfly contributors
Licensed under the GNU General Public License v3 or later. See LICENSE.
"""
import copy

from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout, QGridLayout,
                               QGroupBox, QHBoxLayout, QLabel, QLineEdit, QListWidget, QPlainTextEdit,
                               QPushButton, QSpinBox, QVBoxLayout, QWidget)

from kerfly.core.materials import KINDS, Material, OperationSettings
from kerfly.i18n import N_, _

KIND_TITLES = {"cut": N_("Cut"), "engrave": N_("Engrave outline"), "raster": N_("Raster engrave")}


class MaterialsDialog(QDialog):
    def __init__(self, materials, current_layers=None, units="mm", parent=None):
        """current_layers: {kind: OperationSettings} of the job, for 'Save current settings'."""
        super().__init__(parent)
        self.setWindowTitle(_("Material library"))
        self.materials = copy.deepcopy(materials)
        self.current_layers = current_layers or {}
        self._loading = False

        self.list = QListWidget()
        self.list.setMinimumWidth(190)
        self.list.currentRowChanged.connect(self._show)
        left = QVBoxLayout()
        left.addWidget(self.list, 1)
        row = QHBoxLayout()
        for text, slot in ((N_("New"), self._new), (N_("Duplicate"), self._duplicate), (N_("Delete"), self._delete)):
            b = QPushButton(_(text))
            b.clicked.connect(slot)
            row.addWidget(b)
        left.addLayout(row)
        save_current = QPushButton(_("New from current layers"))
        save_current.setToolTip(_("Create a material from the speed, passes and power of the current layers"))
        save_current.clicked.connect(self._from_current)
        save_current.setEnabled(bool(self.current_layers))
        left.addWidget(save_current)

        self.editor = QWidget()
        form = QVBoxLayout(self.editor)
        top = QFormLayout()
        self.name = QLineEdit()
        self.name.textEdited.connect(self._store)
        top.addRow(_("Name:"), self.name)
        self.thickness = QDoubleSpinBox()
        self.thickness.setRange(0, 1000)
        self.thickness.setDecimals(1)
        self.thickness.setSuffix(" mm")
        self.thickness.valueChanged.connect(self._store)
        top.addRow(_("Thickness:"), self.thickness)
        form.addLayout(top)
        self.fields = {}
        for kind in KINDS:
            box = QGroupBox(_(KIND_TITLES[kind]))
            g = QGridLayout(box)
            speed = QDoubleSpinBox()
            speed.setRange(0, 10000)
            speed.setDecimals(1)
            speed.setSuffix(" mm/s")
            passes = QSpinBox()
            passes.setRange(1, 100)
            power = QDoubleSpinBox()
            power.setRange(0, 100)
            power.setDecimals(0)
            power.setSuffix(" %")
            power.setToolTip(_("Used with M3 boards (power per layer)"))
            for w in (speed, passes, power):
                w.valueChanged.connect(self._store)
            g.addWidget(QLabel(_("Speed:")), 0, 0)
            g.addWidget(speed, 0, 1)
            g.addWidget(QLabel(_("Passes:")), 0, 2)
            g.addWidget(passes, 0, 3)
            g.addWidget(QLabel(_("Power:")), 0, 4)
            g.addWidget(power, 0, 5)
            self.fields[kind] = (speed, passes, power)
            form.addWidget(box)
        self.notes = QPlainTextEdit()
        self.notes.setFixedHeight(54)
        self.notes.setPlaceholderText(_("Notes (e.g. supplier, lens, air assist)"))
        self.notes.textChanged.connect(self._store)
        form.addWidget(self.notes)
        if units == "in":
            hint = QLabel(_("Speeds are stored in mm/s and converted to in/min for the layers."))
            hint.setStyleSheet("color:#6b7280;")
            form.addWidget(hint)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        main = QHBoxLayout()
        main.addLayout(left)
        main.addWidget(self.editor, 1)
        outer = QVBoxLayout(self)
        outer.addLayout(main)
        outer.addWidget(buttons)
        self._refresh_list(0)

    # ---- list ---------------------------------------------------------------
    def _refresh_list(self, select):
        self.list.blockSignals(True)
        self.list.clear()
        for m in self.materials:
            self.list.addItem(m.name + (" (%g mm)" % m.thickness_mm if m.thickness_mm else ""))
        self.list.blockSignals(False)
        if self.materials:
            self.list.setCurrentRow(max(0, min(select, len(self.materials) - 1)))
        self._show(self.list.currentRow())

    def _show(self, row):
        self.editor.setEnabled(0 <= row < len(self.materials))
        if not (0 <= row < len(self.materials)):
            return
        m = self.materials[row]
        self._loading = True
        self.name.setText(m.name)
        self.thickness.setValue(m.thickness_mm)
        for kind, (speed, passes, power) in self.fields.items():
            s = m.settings.get(kind) or OperationSettings()
            speed.setValue(s.speed)
            passes.setValue(s.passes)
            power.setValue(s.power * 100)
        self.notes.setPlainText(m.notes)
        self._loading = False

    def _store(self, *args):
        row = self.list.currentRow()
        if self._loading or not (0 <= row < len(self.materials)):
            return
        m = self.materials[row]
        m.name = self.name.text().strip() or _("Material")
        m.thickness_mm = self.thickness.value()
        m.notes = self.notes.toPlainText()
        for kind, (speed, passes, power) in self.fields.items():
            m.settings[kind] = OperationSettings(speed.value(), passes.value(), power.value() / 100.0)
        item = self.list.item(row)
        item.setText(m.name + (" (%g mm)" % m.thickness_mm if m.thickness_mm else ""))

    def _new(self):
        self.materials.append(Material(_("New material"), 3.0, "",
                                       {k: OperationSettings() for k in KINDS}))
        self._refresh_list(len(self.materials) - 1)
        self.name.setFocus()
        self.name.selectAll()

    def _duplicate(self):
        row = self.list.currentRow()
        if 0 <= row < len(self.materials):
            m = copy.deepcopy(self.materials[row])
            m.name = _("%s (copy)") % m.name
            self.materials.insert(row + 1, m)
            self._refresh_list(row + 1)

    def _delete(self):
        row = self.list.currentRow()
        if 0 <= row < len(self.materials):
            del self.materials[row]
            self._refresh_list(row)

    def _from_current(self):
        self.materials.append(Material(_("New material"), 0.0, "",
                                       {k: copy.copy(v) for k, v in self.current_layers.items()}))
        self._refresh_list(len(self.materials) - 1)
        self.name.setFocus()
        self.name.selectAll()
