"""
File → Save G-code: where X0 Y0 is, the power range of the machine (GRBL's
$30) and the raster overscan, before the file name is asked.

Copyright (C) 2026 Kerfly contributors
Licensed under the GNU General Public License v3 or later. See LICENSE.
"""
from PySide6.QtWidgets import QComboBox, QDialog, QDoubleSpinBox, QSpinBox

from kerfly.gui import theme, widgets
from kerfly.i18n import _


class GcodeDialog(QDialog):
    def __init__(self, values, parent=None):
        super().__init__(parent)
        self.setWindowTitle(_("Save G-code"))
        text = widgets.hint(_("G-code for lasers with a GRBL board (diode lasers, CO2 lasers with GRBL): the ticked "
                              "layers in their order, each with its speed, power and passes. Open the file in "
                              "LaserGRBL, UGS or another G-code sender."))
        self.origin = QComboBox()
        self.origin.addItem(_("The bed's lower left corner (X right, Y up; most GRBL lasers)"), "lower_left")
        self.origin.addItem(_("The design's upper left corner (set the work origin there)"), "design")
        self.origin.setCurrentIndex(max(0, self.origin.findData(values.get("gcode_origin", "lower_left"))))
        origin_tip = _("Where X0 Y0 of the G-code is: the corner of the bed the machine homes to, or the design's "
                       "upper left corner, where you set the work origin on the machine before starting")
        self.origin.setToolTip(origin_tip)
        self.s_max = QSpinBox()
        self.s_max.setRange(1, 100000)
        self.s_max.setValue(int(float(values.get("gcode_s_max", 1000) or 1000)))
        s_tip = _("The S value of full power: the machine's $30 setting (1000 on most GRBL boards); a layer's "
                  "power is that part of it")
        self.s_max.setToolTip(s_tip)
        self.overscan = QDoubleSpinBox()
        self.overscan.setRange(0.0, 50.0)
        self.overscan.setDecimals(1)
        self.overscan.setSuffix(" mm")
        self.overscan.setValue(float(values.get("gcode_overscan", 2.0) or 0))
        over_tip = _("Raster engraving: the head starts this far before each line and stops this far after it, "
                     "so it is at speed where it burns")
        self.overscan.setToolTip(over_tip)
        # the dialog pattern: the explanation, one section (beta until confirmed on a GRBL laser), the footer
        section = widgets.Section(_("G-code for GRBL"), beta=True)
        section.add_row("current-location", _("Origin X0 Y0"), origin_tip, self.origin)
        section.add_row("flame", _("Full power S"), s_tip, self.s_max)
        section.add_row("arrows-horizontal", _("Raster overscan"), over_tip, self.overscan)
        body = widgets.DialogBody()
        body.add(text)
        body.add(section)
        body.layout().addStretch(1)
        footer = widgets.DialogFooter(_("Save…"))
        footer.connect(self)
        widgets.dialog_layout(self, body, footer)
        self.setMinimumWidth(theme.DIALOG_SMALL)

    def values(self):
        return {"gcode_origin": self.origin.currentData(), "gcode_s_max": str(self.s_max.value()),
                "gcode_overscan": "%g" % self.overscan.value()}
