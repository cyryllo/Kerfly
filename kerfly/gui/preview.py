"""
Preview of the laser bed with the design placed at the laser head.

Scene units are millimetres with y pointing down; the bed's top-left corner
(the K40 home position) is the scene origin.

Copyright (C) 2026 Kerfly contributors
Licensed under the GNU General Public License v3 or later. See LICENSE.
"""
from PIL import ImageOps
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QImage, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (QGraphicsEllipseItem, QGraphicsItem, QGraphicsLineItem,
                               QGraphicsScene, QGraphicsView)

from kerfly.core.config import bed_size_inches, is_true
from kerfly.core.job import mirror_rotate_vector_coords

MM = 25.4
MAX_PREVIEW_PIXELS = 4000   # longest side of the raster preview image

COLORS = {
    "bed": QColor("#e9ebee"),
    "bed_border": QColor("#b8bec7"),
    "background": QColor("#5b616b"),
    "raster": QColor("#000000"),
    "engrave": QColor("#1565c0"),
    "cut": QColor("#d32f2f"),
    "gcode": QColor("#6a1b9a"),
    "design_box": QColor("#7d8590"),
    "head": QColor("#f57c00"),
}


def _cosmetic_pen(color, width=1.0, style=Qt.SolidLine):
    pen = QPen(color, width, style)
    pen.setCosmetic(True)       # constant width on screen, whatever the zoom
    return pen


def pil_to_qimage(im):
    im = im.convert("L")
    data = im.tobytes()
    qimg = QImage(data, im.width, im.height, im.width, QImage.Format_Grayscale8)
    return qimg.copy()          # detach from the Python buffer


class PreviewView(QGraphicsView):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setScene(QGraphicsScene(self))
        self.setRenderHint(QPainter.Antialiasing, True)
        self.setRenderHint(QPainter.SmoothPixmapTransform, True)
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setBackgroundBrush(COLORS["background"])
        self.setViewportUpdateMode(QGraphicsView.FullViewportUpdate)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._raster_cache_key = None
        self._raster_pixmap = None
        self._fitted = False

    # ---- interaction -------------------------------------------------
    def wheelEvent(self, event):
        factor = 1.25 if event.angleDelta().y() > 0 else 1 / 1.25
        current = self.transform().m11()
        if 0.05 < current * factor < 400:
            self.scale(factor, factor)

    def fit_all(self):
        rect = self.scene().itemsBoundingRect()
        if not rect.isEmpty():
            self.fitInView(rect.adjusted(-5, -5, 5, 5), Qt.KeepAspectRatio)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if not self._fitted:
            self.fit_all()

    # ---- drawing -----------------------------------------------------
    def _raster_pixmap_for(self, design, values):
        image = design.raster.image
        key = (id(image), is_true(values["negate"]), is_true(values["halftone"]),
               is_true(values["mirror"]), is_true(values["rotate"]))
        if key == self._raster_cache_key:
            return self._raster_pixmap
        im = image.convert("L")
        scale = min(1.0, MAX_PREVIEW_PIXELS / float(max(im.size)))
        if scale < 1.0:
            im = im.resize((max(1, int(im.width * scale)), max(1, int(im.height * scale))))
        if key[1]:
            im = ImageOps.invert(im)
        if not key[2]:
            im = im.point(lambda x: 0 if x < 128 else 255, "1").convert("L")
        if key[3]:
            im = ImageOps.mirror(im)
        if key[4]:
            im = im.rotate(90, expand=True)
        self._raster_cache_key = key
        self._raster_pixmap = (QPixmap.fromImage(pil_to_qimage(im)), scale)
        return self._raster_pixmap

    def show_design(self, design, settings, values, head, fit=False, head_offset=(0.0, 0.0)):
        """Redraw everything. head = design origin at the laser head, inches (y <= 0);
        head_offset = temporary head offset from it (e.g. at a design corner), inches."""
        scene = self.scene()
        scene.clear()
        bed_w, bed_h = bed_size_inches(values)

        bed = scene.addRect(QRectF(0, 0, bed_w * MM, bed_h * MM),
                            _cosmetic_pen(COLORS["bed_border"]), QBrush(COLORS["bed"]))
        bed.setZValue(-10)

        xmin, xmax, ymin, ymax = design.origin_bounds(settings)
        if settings.home_upper_right:
            ox = bed_w - head[0] - (xmax - xmin)
        else:
            ox = head[0]
        oy = head[1]

        def to_scene(x, y):
            return QPointF((x - xmin + ox) * MM, -(y - ymax + oy) * MM)

        # raster image
        if design.raster.image is not None and is_true(values["include_Reng"]):
            pixmap, scale = self._raster_pixmap_for(design, values)
            item = scene.addPixmap(pixmap)
            px_mm = MM / design.input_dpi / scale
            item.setScale(px_mm)
            item.setTransformationMode(Qt.SmoothTransformation)
            item.setPos(QPointF(ox * MM, -oy * MM))
            item.setZValue(-5)

        # vector paths
        layers = [
            ("include_Veng", design.vector_engrave.ecoords, "engrave"),
            ("include_Vcut", design.vector_cut.ecoords, "cut"),
            ("include_Gcde", design.gcode.ecoords, "gcode"),
        ]
        for key, coords, color in layers:
            if not coords or not is_true(values[key]):
                continue
            if settings.mirror or settings.rotate:
                coords = mirror_rotate_vector_coords(coords, design, settings)
            path = QPainterPath()
            loop_old = None
            for x, y, loop in ((c[0], c[1], c[2]) for c in coords):
                if loop != loop_old:
                    path.moveTo(to_scene(x, y))
                else:
                    path.lineTo(to_scene(x, y))
                loop_old = loop
            scene.addPath(path, _cosmetic_pen(COLORS[color], 1.2))

        # design outline
        w, h = xmax - xmin, ymax - ymin
        if w > 0 and h > 0:
            box = scene.addRect(QRectF(ox * MM, -oy * MM, w * MM, h * MM),
                                _cosmetic_pen(COLORS["design_box"], 1, Qt.DashLine))
            box.setZValue(-4)

        # laser head marker (fixed size on screen)
        x_head = head[0] + head_offset[0]
        hx = (bed_w - x_head) if settings.home_upper_right else x_head
        marker = QGraphicsEllipseItem(-6, -6, 12, 12)
        marker.setPen(_cosmetic_pen(COLORS["head"], 2))
        marker.setFlag(QGraphicsItem.ItemIgnoresTransformations, True)
        marker.setPos(QPointF(hx * MM, -(head[1] + head_offset[1]) * MM))
        marker.setZValue(10)
        scene.addItem(marker)
        for dx, dy in ((-10, 0), (0, -10)):
            line = QGraphicsLineItem(dx, dy, -dx, -dy, marker)
            line.setPen(_cosmetic_pen(COLORS["head"], 1))

        scene.setSceneRect(scene.itemsBoundingRect().adjusted(-50, -50, 50, 50))
        if fit or not self._fitted:
            self.fit_all()
            self._fitted = True
