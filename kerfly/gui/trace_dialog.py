"""
Trace a picture (Edit → Trace picture…, or the Trace button of a selected
picture): its dark areas become paths, shown over the picture while the
threshold, specks, detail and smoothing are set.

Copyright (C) 2026 Kerfly contributors
Licensed under the GNU General Public License v3 or later. See LICENSE.
"""
from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QImage, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (QCheckBox, QDialog, QDoubleSpinBox, QHBoxLayout, QLabel, QSlider, QSpinBox,
                               QVBoxLayout, QWidget)

from kerfly.core import curves, trace
from kerfly.gui import theme, widgets
from kerfly.i18n import _

PREVIEW = 460


class TraceDialog(QDialog):
    def __init__(self, image, parent=None):
        super().__init__(parent)
        self.setWindowTitle(_("Trace picture"))
        self.image = image.convert("L")
        w, h = self.image.size
        self.k = min(1.0, PREVIEW / float(max(w, h)))
        small = self.image.resize((max(1, int(w * self.k)), max(1, int(h * self.k))))
        rgb = small.convert("RGB")
        self.base = QImage(rgb.tobytes(), rgb.width, rgb.height, rgb.width * 3, QImage.Format_RGB888).copy()
        self.small = small
        self.paths = []

        self.view = QLabel()
        self.view.setFixedSize(PREVIEW, PREVIEW)
        self.view.setAlignment(Qt.AlignCenter)
        self.threshold = QSlider(Qt.Horizontal)
        self.threshold.setRange(1, 254)
        self.threshold.setValue(128)
        self.threshold.setToolTip(_("Threshold: pixels darker than this are traced"))
        self.threshold_value = QSpinBox()
        self.threshold_value.setRange(1, 254)
        self.threshold_value.setValue(128)
        self.threshold.valueChanged.connect(self.threshold_value.setValue)
        self.threshold_value.valueChanged.connect(self.threshold.setValue)
        self.invert = QCheckBox(_("Trace the light areas instead"))
        self.specks = QSpinBox()
        self.specks.setRange(0, 100000)
        self.specks.setValue(4)
        self.specks.setSuffix(" px²")
        self.specks.setToolTip(_("Ignore specks: dark spots smaller than this many pixels are left out"))
        self.detail = QDoubleSpinBox()
        self.detail.setRange(0.3, 20.0)
        self.detail.setSingleStep(0.1)
        self.detail.setValue(1.0)
        self.detail.setSuffix(" px")
        self.detail.setToolTip(_("Detail: how far the outline may stray from the pixel edges (smaller: more nodes, "
                                 "closer to the picture)"))
        self.smooth = QCheckBox(_("Smooth curves (sharp corners stay sharp)"))
        self.smooth.setChecked(True)
        self.corner = QSpinBox()
        self.corner.setRange(10, 170)
        self.corner.setValue(60)
        self.corner.setSuffix("°")
        self.corner.setToolTip(_("Corner: turns sharper than this stay corners, the rest become curves"))
        # the dialog pattern (docs/ui-mockups/Trace): the settings in two sections on the left, the preview on
        # the right, the number of outlines in the footer with Cancel and Trace
        footer = widgets.DialogFooter(_("Trace"))
        footer.connect(self)
        self.count = footer.info
        thr = QWidget()
        th = QHBoxLayout(thr)
        th.setContentsMargins(0, 0, 0, 0)
        th.addWidget(self.threshold, 1)
        th.addWidget(self.threshold_value)
        self.invert.setToolTip(_("Trace the light areas of the picture instead of the dark ones"))
        self.smooth.setToolTip(_("Curves through the outline's nodes; corners sharper than the angle below stay "
                                 "sharp"))
        what = widgets.Section(_("What to trace"))
        what.add_row("square-minus", _("Threshold"), self.threshold.toolTip(), thr)
        what.add_wide(self.invert)
        what.add_row("circle-dashed", _("Ignore specks"), self.specks.toolTip(), self.specks)
        shape = widgets.Section(_("Outline shape"))
        shape.add_row("vector", _("Detail"), self.detail.toolTip(), self.detail)
        shape.add_wide(self.smooth)
        shape.add_row("angle", _("Corner"), self.corner.toolTip(), self.corner)
        side = QVBoxLayout()
        side.setSpacing(theme.SPACE_L)
        side.addWidget(what)
        side.addWidget(shape)
        side.addStretch(1)
        side.addWidget(widgets.hint(_("The paths are put over the picture as a new element; the picture stays "
                                      "(delete it or leave it out of the job).")))
        top = QHBoxLayout()
        top.setSpacing(theme.PAD_DIALOG)
        top.addLayout(side, 1)
        top.addWidget(self.view)
        body = widgets.DialogBody()
        body.layout().addLayout(top)
        widgets.dialog_layout(self, body, footer)
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(150)
        self.timer.timeout.connect(self._preview)
        for wd in (self.threshold_value, self.specks, self.corner):
            wd.valueChanged.connect(self.timer.start)
        self.detail.valueChanged.connect(self.timer.start)
        for wd in (self.invert, self.smooth):
            wd.toggled.connect(self.timer.start)
        self.smooth.toggled.connect(self.corner.setEnabled)
        self._preview()

    def options(self):
        return dict(threshold=self.threshold_value.value(), invert=self.invert.isChecked(),
                    specks=self.specks.value(), detail=self.detail.value(), smooth=self.smooth.isChecked(),
                    corner_deg=float(self.corner.value()))

    def _preview(self):
        opts = self.options()
        k = self.k
        # the preview traces the small picture: specks and detail scaled to it
        paths = trace.trace(self.small, opts["threshold"], opts["invert"], opts["specks"] * k * k,
                            max(0.3, opts["detail"] * k), opts["smooth"], opts["corner_deg"])
        pm = QPixmap(PREVIEW, PREVIEW)
        pm.fill(theme.canvas("preview_paper"))
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing, True)
        ox, oy = (PREVIEW - self.base.width()) / 2.0, (PREVIEW - self.base.height()) / 2.0
        p.setOpacity(0.35)
        p.drawImage(QRectF(ox, oy, self.base.width(), self.base.height()), self.base)
        p.setOpacity(1.0)
        p.setPen(QPen(theme.canvas("preview_line"), 1.3))
        n = 0
        for poly in curves.flatten(paths):
            path = QPainterPath(QPointF(ox + poly[0][0], oy + poly[0][1]))
            for x, y in poly[1:]:
                path.lineTo(ox + x, oy + y)
            p.drawPath(path)
            n += 1
        p.end()
        self.view.setPixmap(pm)
        self.count.setText(_("%d outlines") % n)
        self.preview_count = n

    def result_paths(self):
        """The paths of the whole picture (pixels, y down)."""
        o = self.options()
        return trace.trace(self.image, o["threshold"], o["invert"], o["specks"], o["detail"], o["smooth"],
                           o["corner_deg"])
