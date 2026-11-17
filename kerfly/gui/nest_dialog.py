"""
Arrange → Nest on the bed: the gap between the parts and whether they may be
turned by 90 degrees. A sheet is always the laser's bed.

Copyright (C) 2026 Kerfly contributors
Licensed under the GNU General Public License v3 or later. See LICENSE.
"""
from PySide6.QtWidgets import QCheckBox, QDialog, QDoubleSpinBox

from kerfly.gui import theme, widgets
from kerfly.i18n import _


class NestDialog(QDialog):
    def __init__(self, values, bed_mm, count, parent=None):
        super().__init__(parent)
        self.setWindowTitle(_("Nest on the bed"))
        text = widgets.hint(_("The %(n)d selected parts (a group as one part) are laid out on the laser's bed "
                        "(%(w).0f × %(h).0f mm) as tightly as their outlines' rectangles allow. What does not fit "
                        "goes on a next sheet: each sheet is a group in the element list, sheets 2 and on "
                        "unticked.") % {"n": count, "w": bed_mm[0], "h": bed_mm[1]})
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
        # the dialog pattern: the explanation, the fields, the footer with the named action
        section = widgets.Section()
        section.add_row("box-padding", _("Gap"), gap_tip, self.gap)
        section.add_row("rotate-clockwise-2", _("Turn by 90°"), turn_tip, self.turn)
        body = widgets.DialogBody()
        body.add(text)
        body.add(section)
        body.layout().addStretch(1)
        footer = widgets.DialogFooter(_("Nest"))
        footer.connect(self)
        widgets.dialog_layout(self, body, footer)
        self.setMinimumWidth(theme.DIALOG_SMALL)

    def values(self):
        return {"gap": self.gap.value(), "turn": self.turn.isChecked()}
