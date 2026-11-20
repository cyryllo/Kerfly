"""
Material library dialog: list of materials on the left, the selected
material's cut / outline engrave / raster settings on the right.

Copyright (C) 2026 Kerfly contributors
Licensed under the GNU General Public License v3 or later. See LICENSE.
"""
import copy

from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QDoubleSpinBox, QHBoxLayout, QLabel, QLineEdit,
                               QListWidget, QPlainTextEdit, QPushButton, QSpinBox, QVBoxLayout, QWidget)

from kerfly.core.materials import KINDS, Material, OperationSettings
from kerfly.gui import icons, theme, widgets
from kerfly.gui.sizing import fit_spin
from kerfly.gui.layers_panel import CUT, ENGRAVE, KIND_NAMES, RASTER
from kerfly.i18n import N_, _, ngettext

KIND_TITLES = {"cut": KIND_NAMES[CUT], "engrave": KIND_NAMES[ENGRAVE], "raster": KIND_NAMES[RASTER]}


def list_label(m):
    """'Plywood 3 mm', or 'Plywood (3 mm)' when the name does not say the thickness."""
    if not m.thickness_mm:
        return m.name
    t = "%g mm" % m.thickness_mm
    compact = m.name.replace(" ", "").replace(",", ".").lower()
    if t.replace(" ", "") in compact:
        return m.name
    return "%s (%s)" % (m.name, t)


class MaterialsDialog(QDialog):
    def __init__(self, materials, current_layers=None, units="mm", parent=None, current_extra=None, speed_factor=1.0):
        """current_layers: {kind: OperationSettings} of the job's basic layers, and
        current_extra: [ExtraLayer] its other layers, for 'New from current layers'."""
        super().__init__(parent)
        self.speed_factor = float(speed_factor) or 1.0           # shown = kept (mm/s) x it: mm/min for GRBL
        self.setWindowTitle(_("Material library"))
        self.materials = copy.deepcopy(materials)
        self.current_layers = current_layers or {}
        self.current_extra = list(current_extra or [])
        self._loading = False

        # the dialog pattern (docs/ui-mockups/Materials): the list with New, Duplicate, Import above it and New
        # from current layers under it; the material's name, thickness, a table of its layers (the units in the
        # header), notes, Export and Delete; the footer with the number of materials, Cancel and Save
        self.list = QListWidget()
        self.list.setMinimumWidth(theme.OPTION_TITLE * 2)
        self.list.currentRowChanged.connect(self._show)

        def button(text, icon, tip, slot):
            b = QPushButton(icons.tabler(icon, theme.token("danger") if icon == "trash" else None), _(text))
            b.setToolTip(tip)
            b.setFixedHeight(theme.HEIGHT_FIELD)
            b.clicked.connect(slot)
            return b
        left = QVBoxLayout()
        left.setSpacing(theme.SPACE_M)
        row = QHBoxLayout()
        row.setSpacing(theme.SPACE_S)
        row.addWidget(button(N_("New"), "plus", _("A new material"), self._new))
        row.addWidget(button(N_("Duplicate"), "copy", _("A copy of the selected material"), self._duplicate))
        row.addWidget(button(N_("Import\u2026"), "folder-open", _("Add the materials of a library file"),
                             self._import))
        row.addStretch(1)
        left.addLayout(row)
        left.addWidget(self.list, 1)
        save_current = QPushButton(_("New from current layers"))
        save_current.setToolTip(_("Create a material from the speed, passes and power of the current layers"))
        save_current.clicked.connect(self._from_current)
        save_current.setEnabled(bool(self.current_layers))
        left.addWidget(save_current)

        self.editor = QWidget()
        form = QVBoxLayout(self.editor)
        form.setContentsMargins(0, 0, 0, 0)
        form.setSpacing(theme.SPACE_L)
        top = widgets.Section()
        self.name = QLineEdit()
        self.name.textEdited.connect(self._store)
        top.add_row("typography", _("Name"), _("The material's name, as the list shows it"), self.name)
        self.thickness = QDoubleSpinBox()
        self.thickness.setRange(0, 1000)
        self.thickness.setDecimals(1)
        self.thickness.setSuffix(" mm")
        fit_spin(self.thickness, 999.9)
        self.thickness.valueChanged.connect(self._store)
        top.add_row("line-height", _("Thickness"), _("The material's thickness"), self.thickness)
        form.addWidget(top)
        unit = "mm/s" if self.speed_factor == 1 else "mm/min"
        layers = widgets.Section(_("Layers"))
        g = layers.grid
        g.setHorizontalSpacing(theme.SPACE_M)
        g.setColumnStretch(0, 1)
        self.speed_header = widgets.label(_("Speed (%s)") % unit, "caption", wrap=True)
        for col, w in enumerate((widgets.label(_("Name"), "caption"), self.speed_header,
                                 widgets.label(_("Passes"), "caption"), widgets.label(_("Power (%)"), "caption"),
                                 widgets.label(_("Kerf (mm)"), "caption"))):
            g.addWidget(w, 0, col)
        self.fields = {}
        for r, kind in enumerate(KINDS, start=1):
            speed = QDoubleSpinBox()
            speed.setRange(0, 10000 * self.speed_factor)
            speed.setDecimals(1 if self.speed_factor == 1 else 0)
            speed.setToolTip(_("Speed of the %s layer") % _(KIND_TITLES[kind]).lower())
            passes = QSpinBox()
            passes.setRange(1, 100)
            power = QDoubleSpinBox()
            power.setRange(0, 100)
            power.setDecimals(0)
            power.setToolTip(_("Used with M3 boards (power per layer)"))
            for w in (speed, passes, power):
                w.valueChanged.connect(self._store)
            g.addWidget(QLabel(_(KIND_TITLES[kind])), r, 0)
            g.addWidget(speed, r, 1)
            g.addWidget(passes, r, 2)
            g.addWidget(power, r, 3)
            kerf = None
            if kind == "cut":
                kerf = QDoubleSpinBox()
                kerf.setRange(0, 2)
                kerf.setDecimals(2)
                kerf.setSingleStep(0.05)
                kerf.setToolTip(_("Width of the cut in this material (measure it with Generators → Kerf test): "
                                  "the cut layer moves the outlines out by half of it"))
                kerf.valueChanged.connect(self._store)
                g.addWidget(kerf, r, 4)
            else:
                g.addWidget(widgets.hint("-", wrap=False), r, 4)
            self.fields[kind] = (speed, passes, power, kerf)
        layers.add_wide(widgets.hint(_("The power works with an M3 board only. Measure the kerf with the Kerf test "
                                       "generator.")))
        form.addWidget(layers)
        # the material's other layers (a second cut layer, slower, ...): kept by their names
        self.extra_box = widgets.Section(_("Other layers"))
        self.extra_box.setToolTip(_("The job's layers besides the three basic ones, kept with the material: "
                                    "applying it sets the layer of the same name, or adds it"))
        self.extra_grid = self.extra_box.grid
        form.addWidget(self.extra_box)
        self.notes = QPlainTextEdit()
        self.notes.setFixedHeight(3 * theme.HEIGHT_FIELD)
        self.notes.setPlaceholderText(_("Notes (e.g. supplier, lens, air assist)"))
        self.notes.textChanged.connect(self._store)
        notes = widgets.Section(_("Notes"))
        notes.add_wide(self.notes)
        form.addWidget(notes)
        if units == "in":
            form.addWidget(widgets.hint(_("Speeds are stored in mm/s and converted to in/min for the layers.")))
        form.addStretch(1)
        row = QHBoxLayout()
        row.addWidget(button(N_("Export\u2026"), "file-export", _("Save the library to a file"), self._export))
        row.addWidget(button(N_("Delete"), "trash", _("Delete the selected material"), self._delete))
        row.addStretch(1)
        form.addLayout(row)

        main = QHBoxLayout()
        main.setSpacing(theme.PAD_DIALOG)
        main.addLayout(left)
        main.addWidget(self.editor, 1)
        body = widgets.DialogBody()
        body.layout().addLayout(main, 1)
        footer = widgets.DialogFooter(buttons=QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        footer.connect(self)
        self.count = footer.info
        widgets.dialog_layout(self, body, footer)
        self.resize(theme.DIALOG_LARGE + 80, theme.DIALOG_LARGE - 160)
        self._refresh_list(0)

    # ---- list ---------------------------------------------------------------
    def _refresh_list(self, select):
        self.list.blockSignals(True)
        self.list.clear()
        for m in self.materials:
            self.list.addItem(list_label(m))
        self.list.blockSignals(False)
        n = len(self.materials)
        self.count.setText(ngettext("%d material", "%d materials", n) % n)
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
        for kind, (speed, passes, power, kerf) in self.fields.items():
            s = m.settings.get(kind) or OperationSettings()
            speed.setValue(s.speed * self.speed_factor)
            passes.setValue(s.passes)
            power.setValue(s.power * 100)
            if kerf is not None:
                kerf.setValue(s.kerf)
        self.notes.setPlainText(m.notes)
        self._show_extra(m)
        self._loading = False

    def _store(self, *args):
        row = self.list.currentRow()
        if self._loading or not (0 <= row < len(self.materials)):
            return
        m = self.materials[row]
        m.name = self.name.text().strip() or _("Material")
        m.thickness_mm = self.thickness.value()
        m.notes = self.notes.toPlainText()
        for kind, (speed, passes, power, kerf) in self.fields.items():
            m.settings[kind] = OperationSettings(speed.value() / self.speed_factor, passes.value(),
                                                 power.value() / 100.0, kerf.value() if kerf is not None else 0.0)
        item = self.list.item(row)
        item.setText(list_label(m))

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

    def _import(self):
        from PySide6.QtWidgets import QFileDialog, QMessageBox
        from kerfly.core.materials import import_library, merge_materials
        name, _unused = QFileDialog.getOpenFileName(self, _("Import material library"), "",
                                                    _("Material library") + " (*.json)")
        if not name:
            return
        try:
            imported = import_library(name)
        except (OSError, ValueError) as e:
            QMessageBox.critical(self, _("Import material library"),
                                 _("The file is not a Kerfly material library.") + "\n\n" + str(e))
            return
        self.materials, added, replaced = merge_materials(self.materials, imported)
        self._refresh_list(self.list.currentRow())
        QMessageBox.information(self, _("Import material library"),
                                _("Materials added: %d\nMaterials updated (same name): %d") % (added, replaced))

    def _export(self):
        from PySide6.QtWidgets import QFileDialog, QMessageBox
        from kerfly.core.materials import export_library
        name, _unused = QFileDialog.getSaveFileName(self, _("Export material library"), "kerfly-materials.json",
                                                    _("Material library") + " (*.json)")
        if not name:
            return
        if not name.lower().endswith(".json"):
            name += ".json"
        try:
            export_library(self.materials, name)
        except OSError as e:
            QMessageBox.critical(self, _("Export material library"), str(e))

    def _show_extra(self, m):
        """The material's other layers: name, speed, passes, power (and kerf for cut), a remove button."""
        while self.extra_grid.count():
            w = self.extra_grid.takeAt(0).widget()
            if w is not None:
                widgets.retire(w)          # hidden now, deleted by Qt later
        extra = m.extra_layers or []
        self.extra_box.setVisible(bool(extra))
        self.extra_rows = []
        for row, x in enumerate(extra):
            name = QLabel("%s (%s)" % (x.name, _(KIND_TITLES[x.kind])))
            speed = QDoubleSpinBox()
            speed.setRange(0, 10000 * self.speed_factor)
            speed.setDecimals(1 if self.speed_factor == 1 else 0)
            speed.setValue(x.speed * self.speed_factor)
            passes = QSpinBox()
            passes.setRange(1, 100)
            passes.setValue(x.passes)
            power = QDoubleSpinBox()
            power.setRange(0, 100)
            power.setDecimals(0)
            power.setValue(x.power * 100)
            kerf = None
            cells = [name, speed, passes, power]
            if x.kind == "cut":
                kerf = QDoubleSpinBox()
                kerf.setRange(0, 2)
                kerf.setDecimals(2)
                kerf.setSingleStep(0.05)
                kerf.setValue(x.kerf)
                kerf.setToolTip(_("Kerf:"))
                cells.append(kerf)
            remove = QPushButton(_("Remove"))
            remove.setToolTip(_("Remove this layer from the material"))
            remove.clicked.connect(lambda _c=False, r=row: self._remove_extra(r))
            for col, w in enumerate(cells):
                self.extra_grid.addWidget(w, row, col)
            self.extra_grid.addWidget(remove, row, 5)
            for w in (speed, passes, power, kerf):
                if w is not None:
                    w.valueChanged.connect(self._store_extra)
            self.extra_rows.append((speed, passes, power, kerf))

    def _store_extra(self, *args):
        row = self.list.currentRow()
        if self._loading or not (0 <= row < len(self.materials)):
            return
        m = self.materials[row]
        for x, (speed, passes, power, kerf) in zip(m.extra_layers or [], self.extra_rows):
            x.speed, x.passes, x.power = speed.value() / self.speed_factor, passes.value(), power.value() / 100.0
            if kerf is not None:
                x.kerf = kerf.value()

    def _remove_extra(self, index):
        row = self.list.currentRow()
        if not (0 <= row < len(self.materials)):
            return
        m = self.materials[row]
        if m.extra_layers and 0 <= index < len(m.extra_layers):
            del m.extra_layers[index]
            self._loading = True
            self._show_extra(m)
            self._loading = False

    def _from_current(self):
        self.materials.append(Material(_("New material"), 0.0, "",
                                       {k: copy.copy(v) for k, v in self.current_layers.items()},
                                       [copy.copy(x) for x in self.current_extra]))
        self._refresh_list(len(self.materials) - 1)
        self.name.setFocus()
        self.name.selectAll()
