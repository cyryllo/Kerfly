"""
Dialog asking for the physical size of a bitmap image.

Copyright (C) 2026 Kerfly contributors
Licensed under the GNU General Public License v3 or later. See LICENSE.
"""
from PySide6.QtWidgets import QDialog, QDoubleSpinBox, QLabel

from kerfly.gui import theme, widgets
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

        # the dialog pattern (docs/ui-mockups/ImageSize): the fields, the note, Cancel and Insert picture
        self.dpi.setToolTip(_("Resolution: dots per inch of the picture; more dots make it smaller"))
        self.width.setToolTip(_("Width of the picture on the bed"))
        self.height.setToolTip(_("Height of the picture on the bed (the proportions are kept)"))
        section = widgets.Section()
        section.add_row("photo", _("Image"), _("The picture's size in pixels, as in the file"),
                        QLabel(_("%d × %d pixels") % (width_px, height_px)))
        section.add_row("grid-dots", _("Resolution"), self.dpi.toolTip(), self.dpi)
        section.add_row("arrows-horizontal", _("Width"), self.width.toolTip(), self.width)
        section.add_row("line-height", _("Height"), self.height.toolTip(), self.height)
        body = widgets.DialogBody()
        if not dpi:
            body.add(widgets.error(_("The file does not say how large the image is. Set its size.")))
        body.add(section)
        body.add(widgets.hint(_("Dark pixels are engraved, light and transparent pixels are not.")))
        body.layout().addStretch(1)
        footer = widgets.DialogFooter(_("Insert picture"))
        footer.connect(self)
        widgets.dialog_layout(self, body, footer)
        self.setMinimumWidth(theme.DIALOG_SMALL)

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
