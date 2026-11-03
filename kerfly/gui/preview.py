"""
Laser bed view: design elements placed on the bed, which can be selected,
dragged, scaled and rotated with handles.

Scene units are millimetres with y pointing down; the home corner of the bed
is the scene origin (upper left, or upper right with "home is upper right").

Copyright (C) 2026 Kerfly contributors
Licensed under the GNU General Public License v3 or later. See LICENSE.
"""
import math

from PIL import ImageOps
from PySide6.QtCore import QObject, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QImage, QPainter, QPainterPath, QPen, QPixmap, QTransform
from PySide6.QtWidgets import (QGraphicsEllipseItem, QGraphicsItem, QGraphicsLineItem,
                               QGraphicsRectItem, QGraphicsScene, QGraphicsView)

from kerfly.core.config import bed_size_inches, is_true

MM = 25.4
MAX_PREVIEW_PIXELS = 3000   # longest side of a raster preview image

COLORS = {
    "bed": QColor("#e9ebee"),
    "bed_border": QColor("#b8bec7"),
    "background": QColor("#5b616b"),
    "engrave": QColor("#1565c0"),
    "cut": QColor("#d32f2f"),
    "gcode": QColor("#6a1b9a"),
    "outline": QColor("#9aa1ab"),
    "selection": QColor("#1e88e5"),
    "head": QColor("#f57c00"),
}


def _cosmetic_pen(color, width=1.0, style=Qt.SolidLine):
    pen = QPen(color, width, style)
    pen.setCosmetic(True)       # constant width on screen, whatever the zoom
    return pen


def pil_to_qimage(im):
    im = im.convert("L")
    data = im.tobytes()
    return QImage(data, im.width, im.height, im.width, QImage.Format_Grayscale8).copy()


class ViewSignals(QObject):
    selected = Signal(object)                   # element or None
    moved = Signal(object, float, float)        # element, dx, dy (inches, machine x, y up)
    scaled = Signal(object, float)              # element, factor (about its centre)
    rotated = Signal(object, float)             # element, degrees counter-clockwise
    nudged = Signal(object, float, float)       # element, dx, dy in mm (screen right / up)
    drawn = Signal(str, QPointF, QPointF, bool)  # tool, start, end (scene mm), shift held


def element_transform(element, home_ur, bed_w_mm, scale=1.0, extra_rotation=0.0):
    """QTransform from ElementItem local coordinates to scene coordinates."""
    w, h = element.size
    W, H = w * MM, h * MM
    cx = element.x * MM + W / 2.0
    if home_ur:
        cx = bed_w_mm - cx
    cy = -element.y * MM + H / 2.0
    xmin, xmax, ymin, ymax = element.design.bounds
    w0, h0 = (xmax - xmin) * MM, (ymax - ymin) * MM
    t = QTransform()
    t.translate(cx, cy)
    t.rotate(-(element.rotation + extra_rotation))
    t.scale(element.scale_x * scale, element.scale_y * scale)
    t.translate(-w0 / 2.0, -h0 / 2.0)
    return t


class ElementItem(QGraphicsItem):
    """One design element. Local coordinates: mm, y down, (0,0) = top-left
    of the element's source design."""

    def __init__(self, element, values, view, part_color=None):
        super().__init__()
        self.element = element
        self.view = view
        d = element.design
        xmin, xmax, ymin, ymax = d.bounds
        self.w0 = (xmax - xmin) * MM
        self.h0 = (ymax - ymin) * MM
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.ItemIsMovable, True)
        self.setCursor(Qt.SizeAllCursor)
        self.pixmap = None
        if d.raster.image is not None:
            self.pixmap = view.raster_pixmap(element, values)
        self.paths = []
        for kind, coords, color in (("engrave", d.vector_engrave.ecoords, "engrave"),
                                    ("cut", d.vector_cut.ecoords, "cut"),
                                    ("gcode", d.gcode.ecoords, "gcode")):
            if coords:
                path = QPainterPath()
                loop_old = None
                for row in coords:
                    p = QPointF((row[0] - xmin) * MM, (ymax - row[1]) * MM)
                    if row[2] != loop_old:
                        path.moveTo(p)
                    else:
                        path.lineTo(p)
                    loop_old = row[2]
                layer_color = part_color(element, kind) if part_color is not None else None
                self.paths.append((path, _cosmetic_pen(QColor(layer_color) if layer_color else COLORS[color], 1.2)))

    def boundingRect(self):
        return QRectF(0, 0, max(self.w0, 0.01), max(self.h0, 0.01))

    def paint(self, painter, option, widget=None):
        if self.pixmap is not None:
            pm, _scale = self.pixmap
            painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
            painter.drawPixmap(self.boundingRect(), pm, QRectF(pm.rect()))
        for path, pen in self.paths:
            painter.setPen(pen)
            painter.drawPath(path)
        selected = self.isSelected()
        painter.setPen(_cosmetic_pen(COLORS["selection"] if selected else COLORS["outline"], 1,
                                     Qt.SolidLine if selected else Qt.DashLine))
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(self.boundingRect())

    def mousePressEvent(self, event):
        self._press_pos = self.pos()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        super().mouseMoveEvent(event)
        self.view.hide_handles()

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        moved = self.pos() - getattr(self, "_press_pos", QPointF())
        if abs(moved.x()) > 1e-6 or abs(moved.y()) > 1e-6:
            dx = moved.x() / MM * (-1 if self.view.home_ur else 1)
            dy = -moved.y() / MM
            self.view.signals.moved.emit(self.element, dx, dy)


class Handle(QGraphicsRectItem):
    """Scale handle (corner) or rotation handle, constant size on screen."""

    def __init__(self, kind, view, target):
        super().__init__(-5, -5, 10, 10)
        self.kind = kind
        self.view = view
        self.target = target        # ElementItem
        self.setFlag(QGraphicsItem.ItemIgnoresTransformations, True)
        self.setZValue(20)
        self.setPen(_cosmetic_pen(COLORS["selection"], 1.5))
        self.setBrush(QBrush(QColor("white")))
        self.setCursor(Qt.CrossCursor if kind == "rotate" else Qt.SizeFDiagCursor)
        self._start = None
        self._value = None

    def paint(self, painter, option, widget=None):
        painter.setPen(self.pen())
        painter.setBrush(self.brush())
        painter.setRenderHint(QPainter.Antialiasing, True)
        if self.kind == "rotate":
            painter.drawEllipse(self.rect())
        else:
            painter.drawRect(self.rect())

    def _centre(self):
        return self.target.mapToScene(self.target.boundingRect().center())

    def mousePressEvent(self, event):
        self._start = event.scenePos()
        self._centre_at_start = self._centre()
        self._value = None
        event.accept()

    def mouseMoveEvent(self, event):
        if self._start is None:
            return
        c, p, p0 = self._centre_at_start, event.scenePos(), self._start
        e = self.target.element
        if self.kind == "rotate":
            a0 = math.degrees(math.atan2(p0.y() - c.y(), p0.x() - c.x()))
            a1 = math.degrees(math.atan2(p.y() - c.y(), p.x() - c.x()))
            delta = -(a1 - a0)            # scene y is down: counter-clockwise is negative
            if event.modifiers() & Qt.ShiftModifier:
                delta = round(delta / 15.0) * 15.0
            self._value = delta
            t = element_transform(e, self.view.home_ur, self.view.bed_w_mm, extra_rotation=delta)
        else:
            d0 = math.hypot(p0.x() - c.x(), p0.y() - c.y())
            d = math.hypot(p.x() - c.x(), p.y() - c.y())
            self._value = max(0.01, d / d0) if d0 > 0 else 1.0
            t = element_transform(e, self.view.home_ur, self.view.bed_w_mm, scale=self._value)
        # keep the element's centre where it was while dragging
        self.target.setTransform(t)
        self.view.hide_handles(except_item=self)

    def mouseReleaseEvent(self, event):
        if self._start is None:
            return
        self._start = None
        if self._value is None:
            return
        if self.kind == "rotate":
            self.view.signals.rotated.emit(self.target.element, self._value)
        else:
            self.view.signals.scaled.emit(self.target.element, self._value)


class PreviewView(QGraphicsView):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setScene(QGraphicsScene(self))
        self.setRenderHint(QPainter.Antialiasing, True)
        self.setRenderHint(QPainter.SmoothPixmapTransform, True)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setBackgroundBrush(COLORS["background"])
        self.setViewportUpdateMode(QGraphicsView.FullViewportUpdate)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setDragMode(QGraphicsView.RubberBandDrag)
        self.signals = ViewSignals()
        self.home_ur = False
        self.bed_w_mm = 0.0
        self.grid_mm = 0.0
        self.tool = "select"        # or a shape kind: rectangle, ellipse, polygon, line, text
        self._draw_start = None
        self._draw_item = None
        self._pixmaps = {}          # (id(design), id(image), negate, halftone) -> (pixmap, scale)
        self._items = []
        self._handles = []
        self._fitted = False
        self._panning = None
        self._rebuilding = False
        self.scene().selectionChanged.connect(self._selection_changed)

    # ---- navigation: wheel zooms, middle (or right) button drags the view ----
    def wheelEvent(self, event):
        factor = 1.25 if event.angleDelta().y() > 0 else 1 / 1.25
        current = self.transform().m11()
        if 0.05 < current * factor < 400:
            self.scale(factor, factor)

    def set_tool(self, tool):
        self.tool = tool
        drawing = tool != "select"
        self.setDragMode(QGraphicsView.NoDrag if drawing else QGraphicsView.RubberBandDrag)
        self.viewport().setCursor(Qt.CrossCursor if drawing else Qt.ArrowCursor)

    def _snap_point(self, p):
        if self.grid_mm > 0:
            g = self.grid_mm
            return QPointF(round(p.x() / g) * g, round(p.y() / g) * g)
        return p

    def _draw_shape_item(self, start, end, shift):
        """Rubber-band preview of the shape being drawn."""
        if self._draw_item is not None:
            self.scene().removeItem(self._draw_item)
            self._draw_item = None
        pen = _cosmetic_pen(COLORS["selection"], 1.2, Qt.DashLine)
        if self.tool == "line":
            self._draw_item = self.scene().addLine(start.x(), start.y(), end.x(), end.y(), pen)
            return
        rect = QRectF(start, end).normalized()
        if shift:
            side = max(rect.width(), rect.height())
            rect = QRectF(start.x() if end.x() >= start.x() else start.x() - side,
                          start.y() if end.y() >= start.y() else start.y() - side, side, side)
        if self.tool == "ellipse":
            self._draw_item = self.scene().addEllipse(rect, pen)
        else:
            self._draw_item = self.scene().addRect(rect, pen)
        self._draw_item.setZValue(30)

    def mousePressEvent(self, event):
        if self.tool != "select" and event.button() == Qt.LeftButton:
            self._draw_start = self._snap_point(self.mapToScene(event.position().toPoint()))
            event.accept()
            return
        if event.button() in (Qt.MiddleButton, Qt.RightButton):
            self._panning = event.position()
            self.setCursor(Qt.ClosedHandCursor)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._draw_start is not None:
            end = self._snap_point(self.mapToScene(event.position().toPoint()))
            if self.tool != "text":
                self._draw_shape_item(self._draw_start, end, bool(event.modifiers() & Qt.ShiftModifier))
            event.accept()
            return
        if self._panning is not None:
            delta = event.position() - self._panning
            self._panning = event.position()
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - int(delta.x()))
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - int(delta.y()))
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._draw_start is not None and event.button() == Qt.LeftButton:
            start = self._draw_start
            end = self._snap_point(self.mapToScene(event.position().toPoint()))
            self._draw_start = None
            if self._draw_item is not None:
                self.scene().removeItem(self._draw_item)
                self._draw_item = None
            self.signals.drawn.emit(self.tool, start, end, bool(event.modifiers() & Qt.ShiftModifier))
            event.accept()
            return
        if self._panning is not None and event.button() in (Qt.MiddleButton, Qt.RightButton):
            self._panning = None
            self.unsetCursor()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event):
        """Arrow keys move the selected element (1 mm or one grid step; Shift: 10x).
        Escape leaves a drawing tool."""
        if event.key() == Qt.Key_Escape and self.tool != "select":
            self.signals.drawn.emit("cancel", QPointF(), QPointF(), False)
            event.accept()
            return
        keys = {Qt.Key_Left: (-1, 0), Qt.Key_Right: (1, 0), Qt.Key_Up: (0, 1), Qt.Key_Down: (0, -1)}
        items = self._selected_items()
        if event.key() in keys and len(items) == 1 and not (event.modifiers() & Qt.ControlModifier):
            step = self.grid_mm or 1.0
            if event.modifiers() & Qt.ShiftModifier:
                step *= 10
            dx, dy = keys[event.key()]
            self.signals.nudged.emit(items[0].element, dx * step, dy * step)
            event.accept()
            return
        super().keyPressEvent(event)

    def fit_all(self):
        rect = self.scene().itemsBoundingRect()
        if not rect.isEmpty():
            self.fitInView(rect.adjusted(-5, -5, 5, 5), Qt.KeepAspectRatio)
            self._place_handles()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if not self._fitted:
            self.fit_all()

    # ---- selection and handles ----------------------------------------
    def _selected_items(self):
        return [i for i in self.scene().selectedItems() if isinstance(i, ElementItem)]

    def _selection_changed(self):
        if self._rebuilding:
            return
        self._place_handles()
        items = self._selected_items()
        self.signals.selected.emit(items[0].element if len(items) == 1 else None)

    def _place_handles(self):
        for h in self._handles:
            self.scene().removeItem(h)
        self._handles = []
        items = self._selected_items()
        if len(items) != 1:
            return
        item = items[0]
        r = item.boundingRect()
        for corner in (r.topLeft(), r.topRight(), r.bottomLeft(), r.bottomRight()):
            h = Handle("scale", self, item)
            h.setPos(item.mapToScene(corner))
            self.scene().addItem(h)
            self._handles.append(h)
        top = item.mapToScene(QPointF(r.center().x(), r.top()))
        centre = item.mapToScene(r.center())
        dx, dy = top.x() - centre.x(), top.y() - centre.y()
        length = math.hypot(dx, dy) or 1.0
        offset = 22.0 / max(self.transform().m11(), 1e-6)      # ~22 px beyond the edge
        h = Handle("rotate", self, item)
        h.setPos(QPointF(top.x() + dx / length * offset, top.y() + dy / length * offset))
        self.scene().addItem(h)
        self._handles.append(h)

    def hide_handles(self, except_item=None):
        for h in self._handles:
            if h is not except_item:
                h.setVisible(False)

    def select_element(self, element):
        for item in self._items:
            item.setSelected(item.element is element)

    # ---- drawing --------------------------------------------------------
    def raster_pixmap(self, element, values):
        d = element.design
        key = (id(d), id(d.raster.image), is_true(values["negate"]), is_true(values["halftone"]))
        cached = self._pixmaps.get(key)
        if cached is not None:
            return cached
        im = d.raster.image.convert("L")
        scale = min(1.0, MAX_PREVIEW_PIXELS / float(max(im.size)))
        if scale < 1.0:
            im = im.resize((max(1, int(im.width * scale)), max(1, int(im.height * scale))))
        if key[2]:
            im = ImageOps.invert(im)
        if not key[3]:
            im = im.point(lambda x: 0 if x < 128 else 255, "1").convert("L")
        result = (QPixmap.fromImage(pil_to_qimage(im)), scale)
        self._pixmaps[key] = result
        return result

    def show_layout(self, elements, selected, settings, values, head, fit=False, grid_mm=0.0, part_color=None):
        """Redraw the bed, the elements and the laser head (head in bed inches, y <= 0)."""
        self._rebuilding = True
        scene = self.scene()
        scene.clear()
        self._items, self._handles = [], []
        bed_w, bed_h = bed_size_inches(values)
        self.home_ur = bool(settings.home_upper_right)
        self.bed_w_mm = bed_w * MM

        bed = scene.addRect(QRectF(0, 0, bed_w * MM, bed_h * MM),
                            _cosmetic_pen(COLORS["bed_border"]), QBrush(COLORS["bed"]))
        bed.setZValue(-10)
        self.grid_mm = grid_mm
        if grid_mm > 0:
            # draw at least every 5 mm so a fine grid does not turn into a grey area
            step = grid_mm * max(1, int(math.ceil(5.0 / grid_mm)))
            minor = _cosmetic_pen(QColor("#d3d7dd"), 1)
            major = _cosmetic_pen(QColor("#bfc5cd"), 1)
            n = 0
            x = 0.0
            while x <= bed_w * MM + 1e-6:
                line = scene.addLine(x, 0, x, bed_h * MM, major if n % 5 == 0 else minor)
                line.setZValue(-9)
                x += step
                n += 1
            n = 0
            y = 0.0
            while y <= bed_h * MM + 1e-6:
                line = scene.addLine(0, y, bed_w * MM, y, major if n % 5 == 0 else minor)
                line.setZValue(-9)
                y += step
                n += 1
        live = {id(e.design) for e in elements}
        self._pixmaps = {k: v for k, v in self._pixmaps.items() if k[0] in live}

        for e in elements:
            item = ElementItem(e, values, self, part_color)
            if self.tool != "select":
                item.setFlag(QGraphicsItem.ItemIsMovable, False)
            item.setTransform(element_transform(e, self.home_ur, self.bed_w_mm))
            if not e.visible:
                item.setOpacity(0.25)
            scene.addItem(item)
            self._items.append(item)

        hx = (bed_w - head[0]) if self.home_ur else head[0]
        marker = QGraphicsEllipseItem(-6, -6, 12, 12)
        marker.setPen(_cosmetic_pen(COLORS["head"], 2))
        marker.setFlag(QGraphicsItem.ItemIgnoresTransformations, True)
        marker.setPos(QPointF(hx * MM, -head[1] * MM))
        marker.setZValue(15)
        scene.addItem(marker)
        for dx, dy in ((-10, 0), (0, -10)):
            line = QGraphicsLineItem(dx, dy, -dx, -dy, marker)
            line.setPen(_cosmetic_pen(COLORS["head"], 1))

        scene.setSceneRect(QRectF(-60, -60, bed_w * MM + 120, bed_h * MM + 120))
        if fit or not self._fitted:
            self.fit_all()
            self._fitted = True
        self._rebuilding = False
        if selected is not None:
            self.select_element(selected)
        self._place_handles()
