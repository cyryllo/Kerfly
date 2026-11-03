"""
Dialog asking for the physical size of a bitmap image.

Copyright (C) 2026 Kerfly contributors
Licensed under the GNU General Public License v3 or later. See LICENSE.
"""
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout, QLabel,
                               QVBoxLayout)

from kerfly.i18n import _

DEFAULT_DPI = 96.0


class ImageSizeDialog(QDialog):
    """Resolution, width and height are linked; the aspect ratio is kept."""

    def __init__(self, width_px, height_px, dpi=None, units="mm", parent=None):
        super().__init__(parent)
        self.setWindowTitle(_("Image size"))
        self.width_px = width_px
        self.height_px = height_px
        self.per_inch = 25.4 if units == "mm" else 1.0      # length units per inch
        self._updating = False

        self.dpi = QDoubleSpinBox()
        self.dpi.setRange(1.0, 20000.0)
        self.dpi.setDecimals(1)
        self.dpi.setSuffix(" dpi")
        self.width = QDoubleSpinBox()
        self.height = QDoubleSpinBox()
        for w in (self.width, self.height):
            w.setRange(0.01, 100000.0)
            w.setDecimals(2 if units == "mm" else 3)
            w.setSuffix(" " + units)

        form = QFormLayout()
        form.addRow(_("Image:"), QLabel(_("%d × %d pixels") % (width_px, height_px)))
        form.addRow(_("Resolution:"), self.dpi)
        form.addRow(_("Width:"), self.width)
        form.addRow(_("Height:"), self.height)
        note = QLabel(_("Dark pixels are engraved, light and transparent pixels are not."))
        note.setWordWrap(True)
        note.setStyleSheet("color:#616161;")
        if not dpi:
            hint = QLabel(_("The file does not say how large the image is. Set its size."))
            hint.setWordWrap(True)
            hint.setStyleSheet("color:#c62828;")
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        if not dpi:
            layout.addWidget(hint)
        layout.addLayout(form)
        layout.addWidget(note)
        layout.addWidget(buttons)

        self.dpi.valueChanged.connect(self._dpi_changed)
        self.width.valueChanged.connect(lambda v: self._size_changed(v, self.width_px))
        self.height.valueChanged.connect(lambda v: self._size_changed(v, self.height_px))
        self.dpi.setValue(dpi or DEFAULT_DPI)
        self._dpi_changed(self.dpi.value())

    def _set(self, dpi=None, width=None, height=None):
        self._updating = True
        try:
            if dpi is not None:
                self.dpi.setValue(dpi)
            if width is not None:
                self.width.setValue(width)
            if height is not None:
                self.height.setValue(height)
        finally:
            self._updating = False

    def _dpi_changed(self, dpi):
        if self._updating or dpi <= 0:
            return
        self._set(width=self.width_px / dpi * self.per_inch, height=self.height_px / dpi * self.per_inch)

    def _size_changed(self, length, pixels):
        if self._updating or length <= 0:
            return
        dpi = pixels / (length / self.per_inch)
        self._set(dpi=dpi, width=self.width_px / dpi * self.per_inch,
                  height=self.height_px / dpi * self.per_inch)

    def result_dpi(self):
        """Resolution matching the width shown (more precise than the rounded dpi field)."""
        return self.width_px / (self.width.value() / self.per_inch)
