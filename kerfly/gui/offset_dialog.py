"""
The Offset dialog: how far to move the outlines of the selected shapes,
round or sharp corners, and whether to keep the original shapes.

Copyright (C) 2026 Kerfly contributors
Licensed under the GNU General Public License v3 or later. See LICENSE.
"""
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout,
                               QLabel, QVBoxLayout)

from kerfly.i18n import _

# remembered while the program runs
LAST = {"distance": 2.0, "join": "round", "keep": True}


class OffsetDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(_("Offset"))
        form = QFormLayout()
        self.distance = QDoubleSpinBox()
        self.distance.setRange(-50.0, 50.0)
        self.distance.setDecimals(2)
        self.distance.setSingleStep(0.5)
        self.distance.setSuffix(" mm")
        self.distance.setValue(LAST["distance"])
        tip = _("How far the new outline lies from the shape: positive outside (holes get smaller), "
                "negative inside")
        self.distance.setToolTip(tip)
        self.distance.setProperty("offset_field", "distance")
        lbl = QLabel(_("Distance"))
        lbl.setToolTip(tip)
        form.addRow(lbl, self.distance)
        self.join = QComboBox()
        self.join.addItem(_("Round"), "round")
        self.join.addItem(_("Sharp"), "miter")
        self.join.setCurrentIndex(max(0, self.join.findData(LAST["join"])))
        tip = _("Corners of the new outline: rounded, or sharp like the shape's")
        self.join.setToolTip(tip)
        self.join.setProperty("offset_field", "join")
        lbl = QLabel(_("Corners"))
        lbl.setToolTip(tip)
        form.addRow(lbl, self.join)
        self.keep = QCheckBox(_("Keep the original shapes"))
        self.keep.setChecked(LAST["keep"])
        self.keep.setToolTip(_("Add the new outline next to the shape; off: the shape is replaced by it"))
        self.keep.setProperty("offset_field", "keep")
        form.addRow(self.keep)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        note = QLabel(_("Draws a new outline around the selected shapes (or inside them). Only closed "
                        "outlines are used."))
        note.setWordWrap(True)
        lay.addWidget(note)
        lay.addLayout(form)
        lay.addWidget(buttons)

    def values(self):
        return {"distance": self.distance.value(), "join": self.join.currentData(), "keep": self.keep.isChecked()}

    def accept(self):
        LAST.update(self.values())
        super().accept()
