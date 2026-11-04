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
from PySide6.QtWidgets import (QGraphicsEllipseItem, QGraphicsItem, QGraphicsLineItem, QGraphicsPathItem,
                               QGraphicsSimpleTextItem,
                               QGraphicsRectItem, QGraphicsScene, QGraphicsView)

from kerfly.core import snap as snapping
from kerfly.core.config import bed_size_inches, is_true
from kerfly.i18n import N_, _

SNAP_PIXELS = 10                     # snap distance on screen
SNAP_LABELS = {snapping.CORNER: N_("corner"), snapping.CENTRE: N_("centre"),
               snapping.MIDDLE: N_("middle"), snapping.EDGE: N_("on line"),
               snapping.ALIGNED: N_("in line")}

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
    "off_bed": QColor("#d32f2f"),
    "snap": QColor("#e040fb"),
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
    polyline_drawn = Signal(list, bool)           # corner points (scene mm), closed
    nodes_changed = Signal(object, list, bool)    # element, its corner points (scene mm), closed


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
        self.local_polys = []        # polylines in local coordinates, for snapping
        self._snap_cache = None
        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges, True)
        self._dragging = False
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
                        self.local_polys.append([])
                    else:
                        path.lineTo(p)
                    self.local_polys[-1].append((p.x(), p.y()))
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
        if self.off_bed():
            # outside the work area: red frame and tint (the job is blocked)
            tint = QColor(COLORS["off_bed"])
            tint.setAlpha(45)
            painter.setPen(_cosmetic_pen(COLORS["off_bed"], 2))
            painter.setBrush(QBrush(tint))
            painter.drawRect(self.boundingRect())
            return
        painter.setPen(_cosmetic_pen(COLORS["selection"] if selected else COLORS["outline"], 1,
                                     Qt.SolidLine if selected else Qt.DashLine))
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(self.boundingRect())

    def off_bed(self):
        """Outside the bed rectangle (checked on the scene, so it follows a drag)."""
        bed = getattr(self.view, "bed_rect", None)
        if bed is None or not self.element.visible:
            return False
        tol = 0.05                                   # mm
        return not bed.adjusted(-tol, -tol, tol, tol).contains(self.sceneBoundingRect())

    def snap_shape(self):
        """Snap targets of this element in scene coordinates (cached until it moves)."""
        t = self.sceneTransform()
        key = (t.m11(), t.m12(), t.m21(), t.m22(), t.dx(), t.dy())
        if self._snap_cache is None or self._snap_cache[0] != key:
            polys = [[t.map(x, y) for x, y in poly] for poly in self.local_polys]
            r = self.sceneBoundingRect()
            self._snap_cache = (key, snapping.SnapShape(polys, (r.left(), r.top(), r.right(), r.bottom())))
        return self._snap_cache[1]

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionChange and self._dragging:
            return self.view.snap_drag(self, value)
        return super().itemChange(change, value)

    def mousePressEvent(self, event):
        self._press_pos = self.pos()
        self._dragging = event.button() == Qt.LeftButton
        self.view.last_move_snapped = False
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        super().mouseMoveEvent(event)
        self.view.hide_handles()

    def mouseReleaseEvent(self, event):
        self._dragging = False
        self.view.hide_snap_marker()
        super().mouseReleaseEvent(event)
        moved = self.pos() - getattr(self, "_press_pos", QPointF())
        if abs(moved.x()) > 1e-6 or abs(moved.y()) > 1e-6:
            dx = moved.x() / MM * (-1 if self.view.home_ur else 1)
            dy = -moved.y() / MM
            self.view.signals.moved.emit(self.element, dx, dy)


class NodeHandle(QGraphicsRectItem):
    """A corner point of a shape in the node tool: drag to move it, click to
    select it (Delete removes it), double-click to remove it."""

    def __init__(self, index, view):
        super().__init__(-4.5, -4.5, 9, 9)
        self.index = index
        self.view = view
        self.setFlag(QGraphicsItem.ItemIgnoresTransformations, True)
        self.setZValue(45)
        self.setCursor(Qt.SizeAllCursor)
        self.set_selected(False)

    def set_selected(self, on):
        self.setPen(_cosmetic_pen(COLORS["selection"], 1.5))
        self.setBrush(QBrush(COLORS["selection"] if on else QColor("white")))

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.view.select_node(self)
            self._moved = False
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        self.setPos(self.view.snap_node(self, event.scenePos()))
        self._moved = True
        self.view._draw_node_overlay()
        event.accept()

    def mouseReleaseEvent(self, event):
        self.view.hide_snap_marker()
        self.view._remove_guides()
        if getattr(self, "_moved", False):
            self.view._commit_nodes()
        event.accept()

    def mouseDoubleClickEvent(self, event):
        self.view.delete_node(self)
        event.accept()


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
        self._poly_points = []      # polyline being drawn (scene mm)
        self.snap_objects = True    # snap to corners, centres, middles and lines of other elements
        self.node_points_provider = None   # element -> (points in item coordinates, closed) or None
        self._node_handles = []
        self._node_item = None
        self._node_closed = False
        self._node_overlay = None
        self.last_move_snapped = False
        self._snap_marker = None
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
        self._clear_polyline()
        self.hide_snap_marker()
        self.tool = tool
        for item in self._items:
            item.setFlag(QGraphicsItem.ItemIsMovable, tool == "select")
        self._place_handles()
        if tool == "nodes":
            self.setDragMode(QGraphicsView.NoDrag)
            self.viewport().setCursor(Qt.ArrowCursor)
            return
        drawing = tool != "select"
        self.setDragMode(QGraphicsView.NoDrag if drawing else QGraphicsView.RubberBandDrag)
        self.viewport().setCursor(Qt.CrossCursor if drawing else Qt.ArrowCursor)

    # ---- snapping: other elements first, then the grid ------------------------
    def _snap_tolerance(self):
        return SNAP_PIXELS / max(abs(self.transform().m11()), 1e-9)

    def _snap_shapes(self, exclude=()):
        shapes = [i.snap_shape() for i in self._items if i not in exclude and i.element.visible]
        bed = getattr(self, "bed_rect", None)
        if bed is not None:
            shapes.append(snapping.SnapShape([], (bed.left(), bed.top(), bed.right(), bed.bottom())))
        return shapes

    def hide_snap_marker(self):
        if self._snap_marker is not None:
            if self._snap_marker.scene() is not None:
                self.scene().removeItem(self._snap_marker)
            self._snap_marker = None

    def show_snap_marker(self, x, y, kind):
        self.hide_snap_marker()
        path = QPainterPath()
        if kind == snapping.CORNER:
            path.addRect(-5, -5, 10, 10)
        elif kind == snapping.CENTRE:
            path.addEllipse(-5, -5, 10, 10)
            path.moveTo(-7, 0); path.lineTo(7, 0); path.moveTo(0, -7); path.lineTo(0, 7)
        elif kind == snapping.MIDDLE:
            path.moveTo(0, -6); path.lineTo(6, 5); path.lineTo(-6, 5); path.closeSubpath()
        elif kind == snapping.ALIGNED:
            path.moveTo(-7, 0); path.lineTo(7, 0); path.moveTo(0, -7); path.lineTo(0, 7)
        else:
            path.moveTo(-5, -5); path.lineTo(5, 5); path.moveTo(-5, 5); path.lineTo(5, -5)
        marker = QGraphicsPathItem(path)
        marker.setPen(_cosmetic_pen(COLORS["snap"], 2))
        marker.setFlag(QGraphicsItem.ItemIgnoresTransformations, True)
        marker.setPos(QPointF(x, y))
        marker.setZValue(50)
        label = QGraphicsSimpleTextItem(_(SNAP_LABELS[kind]), marker)
        label.setBrush(QBrush(COLORS["snap"]))
        label.setPos(8, 4)
        self.scene().addItem(marker)
        self._snap_marker = marker

    def snap_node(self, handle, p):
        """Where a dragged corner goes in the node tool: onto other elements, the
        other corners and side middles of its own shape, in line (same x or y)
        with another corner, or onto the grid."""
        others = [h.pos() for h in self._node_handles if h is not handle]
        own = []
        if self.snap_objects and others:
            i = self._node_handles.index(handle)
            pts = [h.pos() for h in self._node_handles]
            n = len(pts)
            pairs = [(k, (k + 1) % n) for k in range(n if self._node_closed else n - 1)]
            sides = [(pts[a].x(), pts[a].y(), pts[b].x(), pts[b].y()) for a, b in pairs if i not in (a, b)]
            own_shape = snapping.SnapShape([], (min(q.x() for q in others), min(q.y() for q in others),
                                                max(q.x() for q in others), max(q.y() for q in others)))
            own_shape.points = [(q.x(), q.y(), snapping.CORNER) for q in others] + \
                [((x1 + x2) / 2.0, (y1 + y2) / 2.0, snapping.MIDDLE) for x1, y1, x2, y2 in sides]
            own_shape.segments = sides
            own = [own_shape]
        exclude = (self._node_item,) if self._node_item is not None else ()
        if self.snap_objects:
            tol = self._snap_tolerance()
            hit = snapping.find_snap(p.x(), p.y(), own + self._snap_shapes(exclude), tol)
            if hit is not None:
                self._remove_guides()
                self.show_snap_marker(*hit)
                return QPointF(hit[0], hit[1])
            aligned = snapping.find_axis_snap(p.x(), p.y(), [(q.x(), q.y()) for q in others], tol)
            if aligned is not None:
                x, y, guides = aligned
                self.show_snap_marker(x, y, snapping.ALIGNED)
                self._show_guides(guides)
                return QPointF(x, y)
        self._remove_guides()
        return self.snap_point(p, exclude=exclude)

    def _show_guides(self, guides):
        self._remove_guides()
        path = QPainterPath()
        for x1, y1, x2, y2 in guides:
            path.moveTo(x1, y1)
            path.lineTo(x2, y2)
        self._guides = self.scene().addPath(path, _cosmetic_pen(COLORS["snap"], 1, Qt.DashLine))
        self._guides.setZValue(44)

    def _remove_guides(self):
        g = getattr(self, "_guides", None)
        if g is not None and g.scene() is not None:
            self.scene().removeItem(g)
        self._guides = None

    def snap_point(self, p, exclude=()):
        """A point the user clicks or drags to, snapped to other elements (when
        object snapping is on) or else to the grid."""
        if self.snap_objects:
            hit = snapping.find_snap(p.x(), p.y(), self._snap_shapes(exclude), self._snap_tolerance())
            if hit is not None:
                self.show_snap_marker(*hit)
                return QPointF(hit[0], hit[1])
        self.hide_snap_marker()
        if self.grid_mm > 0:
            g = self.grid_mm
            return QPointF(round(p.x() / g) * g, round(p.y() / g) * g)
        return p

    _snap_point = snap_point

    def snap_drag(self, item, new_pos):
        """While an element is dragged: move it so one of its corners, middles or
        its centre lands on a target of another element (or of the bed)."""
        self.last_move_snapped = False
        if not self.snap_objects or len(self._selected_items()) > 1:
            self.hide_snap_marker()
            return new_pos
        delta = new_pos - item.pos()
        r = item.sceneBoundingRect().translated(delta)
        refs = [(r.left(), r.top()), (r.right(), r.top()), (r.right(), r.bottom()), (r.left(), r.bottom()),
                (r.center().x(), r.center().y()), (r.center().x(), r.top()), (r.right(), r.center().y()),
                (r.center().x(), r.bottom()), (r.left(), r.center().y())]
        off = snapping.snap_offset(refs, self._snap_shapes(exclude=(item,)), self._snap_tolerance())
        if off is None:
            self.hide_snap_marker()
            return new_pos
        dx, dy, x, y, kind = off
        self.show_snap_marker(x, y, kind)
        self.last_move_snapped = True
        return new_pos + QPointF(dx, dy)

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

    # ---- polyline: click corners; click the first point to close, double-click
    # or Enter to finish open; Backspace removes the last corner; Shift: 45 degrees
    def _clear_polyline(self):
        self._poly_points = []
        if self._draw_item is not None:
            self.scene().removeItem(self._draw_item)
            self._draw_item = None

    def _poly_constrained(self, p, shift):
        if not shift or not self._poly_points:
            return p
        last = self._poly_points[-1]
        dx, dy = p.x() - last.x(), p.y() - last.y()
        angle = round(math.atan2(dy, dx) / (math.pi / 4)) * (math.pi / 4)
        length = math.hypot(dx, dy)
        return QPointF(last.x() + length * math.cos(angle), last.y() + length * math.sin(angle))

    def _near_first_point(self, p):
        if len(self._poly_points) < 3:
            return False
        a = self.mapFromScene(self._poly_points[0])
        b = self.mapFromScene(p)
        return abs(a.x() - b.x()) <= 8 and abs(a.y() - b.y()) <= 8

    def _draw_polyline_item(self, cursor=None):
        if self._draw_item is not None:
            self.scene().removeItem(self._draw_item)
            self._draw_item = None
        pts = list(self._poly_points) + ([cursor] if cursor is not None else [])
        if not pts:
            return
        path = QPainterPath(pts[0])
        for q in pts[1:]:
            path.lineTo(q)
        closing = cursor is not None and self._near_first_point(cursor)
        pen = _cosmetic_pen(COLORS["cut"] if closing else COLORS["selection"], 1.4 if closing else 1.2,
                            Qt.SolidLine if closing else Qt.DashLine)
        self._draw_item = self.scene().addPath(path, pen)
        self._draw_item.setZValue(30)
        for q in self._poly_points[:1]:        # mark the start: click it to close the shape
            dot = QGraphicsEllipseItem(-4, -4, 8, 8, self._draw_item)
            dot.setPen(pen)
            dot.setFlag(QGraphicsItem.ItemIgnoresTransformations, True)
            dot.setPos(q)

    def _finish_polyline(self, closed):
        pts = []
        for q in self._poly_points:
            if not pts or abs(q.x() - pts[-1].x()) > 1e-6 or abs(q.y() - pts[-1].y()) > 1e-6:
                pts.append(q)
        self._clear_polyline()
        if len(pts) >= (3 if closed else 2):
            self.signals.polyline_drawn.emit(pts, closed)

    def mouseDoubleClickEvent(self, event):
        if self.tool == "nodes" and event.button() == Qt.LeftButton and self._node_item is not None:
            hit = self.itemAt(event.position().toPoint())
            if not isinstance(hit, NodeHandle):
                self.insert_node(self.mapToScene(event.position().toPoint()))
                event.accept()
                return
        if self.tool == "polyline" and event.button() == Qt.LeftButton:
            self._finish_polyline(False)
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def mousePressEvent(self, event):
        if self.tool == "nodes" and event.button() == Qt.LeftButton:
            super().mousePressEvent(event)          # select a shape, or grab one of its nodes
            return
        if self.tool == "polyline" and event.button() == Qt.LeftButton:
            p = self._snap_point(self.mapToScene(event.position().toPoint()))
            p = self._poly_constrained(p, bool(event.modifiers() & Qt.ShiftModifier))
            if self._near_first_point(p):
                self._finish_polyline(True)
            else:
                self._poly_points.append(p)
                self._draw_polyline_item()
            event.accept()
            return
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
        if self.tool not in ("select", "nodes") and self._draw_start is None and not self._poly_points \
                and not event.buttons():
            self.snap_point(self.mapToScene(event.position().toPoint()))     # shows where a click lands
        if self.tool == "polyline" and self._poly_points:
            p = self._snap_point(self.mapToScene(event.position().toPoint()))
            self._draw_polyline_item(self._poly_constrained(p, bool(event.modifiers() & Qt.ShiftModifier)))
            event.accept()
            return
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
        if self.tool == "nodes" and event.key() in (Qt.Key_Delete, Qt.Key_Backspace):
            chosen = [h for h in self._node_handles if h.brush().color() == COLORS["selection"]]
            if chosen:
                self.delete_node(chosen[0])
                event.accept()
                return
        if self.tool == "polyline" and self._poly_points:
            if event.key() in (Qt.Key_Return, Qt.Key_Enter):
                self._finish_polyline(False)
                event.accept()
                return
            if event.key() == Qt.Key_Backspace:
                self._poly_points.pop()
                self._draw_polyline_item()
                event.accept()
                return
            if event.key() == Qt.Key_Escape:
                self._clear_polyline()            # first Escape drops the unfinished shape
                event.accept()
                return
        if event.key() == Qt.Key_Escape and self.tool != "select":
            self.signals.drawn.emit("cancel", QPointF(), QPointF(), False)
            event.accept()
            return
        keys = {Qt.Key_Left: (-1, 0), Qt.Key_Right: (1, 0), Qt.Key_Up: (0, 1), Qt.Key_Down: (0, -1)}
        items = self._selected_items()
        if event.key() in keys and items and not (event.modifiers() & Qt.ControlModifier):
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
        if self._rebuilding or getattr(self, "_expanding", False):
            return
        groups = {i.element.group for i in self._selected_items() if i.element.group}
        if groups:                                  # a group is always selected as a whole
            self._expanding = True
            for item in self._items:
                if item.element.group in groups and not item.isSelected():
                    item.setSelected(True)
            self._expanding = False
        self._place_handles()
        items = self._selected_items()
        self.signals.selected.emit(items[0].element if len(items) == 1 else None)

    def _place_handles(self):
        for h in self._handles:
            self.scene().removeItem(h)
        self._handles = []
        items = self._selected_items()
        self._place_nodes(items[0] if len(items) == 1 and self.tool == "nodes" else None)
        if len(items) != 1 or self.tool == "nodes":
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

    # ---- node tool --------------------------------------------------------
    def _clear_nodes(self):
        for h in self._node_handles:
            if h.scene() is not None:
                self.scene().removeItem(h)
        self._node_handles = []
        if self._node_overlay is not None and self._node_overlay.scene() is not None:
            self.scene().removeItem(self._node_overlay)
        self._node_overlay = None
        self._node_item = None

    def _place_nodes(self, item):
        self._clear_nodes()
        if item is None or self.node_points_provider is None:
            return
        found = self.node_points_provider(item.element)
        if not found:
            return
        points, closed = found
        self._node_item = item
        self._node_closed = closed
        t = item.sceneTransform()
        for i, (x, y) in enumerate(points):
            h = NodeHandle(i, self)
            h.setPos(QPointF(*t.map(x, y)))
            self.scene().addItem(h)
            self._node_handles.append(h)

    def node_scene_points(self):
        return [h.pos() for h in self._node_handles]

    def select_node(self, handle):
        for h in self._node_handles:
            h.set_selected(h is handle)

    def _draw_node_overlay(self):
        if self._node_overlay is not None and self._node_overlay.scene() is not None:
            self.scene().removeItem(self._node_overlay)
        pts = self.node_scene_points()
        if len(pts) < 2:
            self._node_overlay = None
            return
        path = QPainterPath(pts[0])
        for q in pts[1:]:
            path.lineTo(q)
        if self._node_closed:
            path.closeSubpath()
        self._node_overlay = self.scene().addPath(path, _cosmetic_pen(COLORS["selection"], 1.2, Qt.DashLine))
        self._node_overlay.setZValue(40)

    def _commit_nodes(self, points=None):
        if self._node_item is None:
            return
        element = self._node_item.element
        self.signals.nodes_changed.emit(element, points if points is not None else self.node_scene_points(),
                                        self._node_closed)

    def delete_node(self, handle):
        pts = self.node_scene_points()
        if len(pts) <= (3 if self._node_closed else 2):
            return                                  # keep at least a line / a triangle
        del pts[self._node_handles.index(handle)]
        self._commit_nodes(pts)

    def insert_node(self, p):
        """Add a corner on the nearest side of the shape (double-click on it)."""
        pts = self.node_scene_points()
        if len(pts) < 2:
            return
        pairs = list(zip(range(len(pts)), pts, pts[1:] + ([pts[0]] if self._node_closed else [])))
        best = None
        for i, a, b in pairs:
            nx, ny = snapping._nearest_on_segment(p.x(), p.y(), a.x(), a.y(), b.x(), b.y())
            d = math.hypot(nx - p.x(), ny - p.y())
            if best is None or d < best[0]:
                best = (d, i, QPointF(nx, ny))
        if best is None or best[0] > 3 * self._snap_tolerance():
            return                                  # not on the outline
        pts.insert(best[1] + 1, best[2])
        self._commit_nodes(pts)

    def select_element(self, element):
        """Select one element, or several when given a list."""
        wanted = element if isinstance(element, (list, tuple)) else [element]
        self._expanding = True                      # one selection signal at the end, not one per item
        for item in self._items:
            item.setSelected(any(item.element is e for e in wanted))
        self._expanding = False
        self._selection_changed()

    def selected_elements(self):
        return [i.element for i in self._selected_items()]

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
        self._snap_marker = None                 # deleted with the scene contents
        self._node_handles, self._node_item, self._node_overlay = [], None, None
        self._guides = None
        scene.clear()
        self._items, self._handles = [], []
        bed_w, bed_h = bed_size_inches(values)
        self.home_ur = bool(settings.home_upper_right)
        self.bed_w_mm = bed_w * MM

        self.bed_rect = QRectF(0, 0, bed_w * MM, bed_h * MM)
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
