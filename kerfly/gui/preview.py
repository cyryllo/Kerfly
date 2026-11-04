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
    nodes_changed = Signal(object, list, bool)    # element, its new path (scene mm), unused
    pen_drawn = Signal(list)                      # path drawn with the pen (subpaths, scene mm)
    measured = Signal(float, float)               # dx, dy of the ruler in mm (screen right / down)


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
        self._pen = None            # pen path being drawn: {"nodes": [...], "pressed": bool}
        self._freehand = None       # points of a freehand line being drawn (scene mm)
        self._measure_start = None
        self._measure_item = None
        self.units = "mm"
        self.snap_objects = True    # snap to corners, centres, middles and lines of other elements
        self.node_points_provider = None   # element -> subpaths in item coordinates, or None
        from kerfly.gui.node_editor import NodeEditor
        self.node_editor = NodeEditor(self)
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
        self._user_zoomed = True                 # keep the user's zoom when the window is resized
        factor = 1.25 if event.angleDelta().y() > 0 else 1 / 1.25
        current = self.transform().m11()
        if 0.05 < current * factor < 400:
            self.scale(factor, factor)

    def set_tool(self, tool):
        self._clear_measure()
        self._clear_polyline()
        self._clear_pen()
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
    @staticmethod
    def snap_suspended():
        """Alt held down: no snapping at all for a moment (objects and grid)."""
        from PySide6.QtWidgets import QApplication
        return bool(QApplication.keyboardModifiers() & Qt.AltModifier)

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
        object snapping is on) or else to the grid. Alt: no snapping."""
        if self.snap_suspended():
            self.hide_snap_marker()
            return p
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
        if not self.snap_objects or len(self._selected_items()) > 1 or self.snap_suspended():
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

    # ---- pen: click = corner, press and drag = smooth node with handles; click the
    # first node to close; double-click or Enter finishes; Backspace; Esc; Shift 45 degrees
    def _clear_pen(self):
        self._pen = None
        if self._draw_item is not None and self._draw_item.scene() is not None:
            self.scene().removeItem(self._draw_item)
        self._draw_item = None

    def _pen_path(self, cursor=None):
        from kerfly.core import curves
        nodes = [list(n) for n in self._pen["nodes"]]
        if cursor is not None and nodes:
            nodes.append(curves.node(cursor.x(), cursor.y()))
        return [{"closed": False, "nodes": nodes}]

    def _draw_pen(self, cursor=None):
        from kerfly.core import curves
        if self._draw_item is not None and self._draw_item.scene() is not None:
            self.scene().removeItem(self._draw_item)
        self._draw_item = None
        if not self._pen or not self._pen["nodes"]:
            return
        qp = QPainterPath()
        for poly in curves.flatten(self._pen_path(cursor), tol=0.05):
            qp.moveTo(QPointF(*poly[0]))
            for q in poly[1:]:
                qp.lineTo(QPointF(*q))
        last = self._pen["nodes"][-1]
        for k in (2, 4):                                   # handles of the last node
            if last[k] is not None:
                qp.moveTo(QPointF(last[0], last[1]))
                qp.lineTo(QPointF(last[k], last[k + 1]))
        closing = cursor is not None and self._pen_near_first(cursor)
        pen = _cosmetic_pen(COLORS["cut"] if closing else COLORS["selection"], 1.3,
                            Qt.SolidLine if closing else Qt.DashLine)
        self._draw_item = self.scene().addPath(qp, pen)
        self._draw_item.setZValue(30)
        first = self._pen["nodes"][0]
        dot = QGraphicsEllipseItem(-4, -4, 8, 8, self._draw_item)
        dot.setPen(pen)
        dot.setFlag(QGraphicsItem.ItemIgnoresTransformations, True)
        dot.setPos(QPointF(first[0], first[1]))

    def _pen_near_first(self, p):
        if not self._pen or len(self._pen["nodes"]) < 2:
            return False
        a = self.mapFromScene(QPointF(self._pen["nodes"][0][0], self._pen["nodes"][0][1]))
        b = self.mapFromScene(p)
        return abs(a.x() - b.x()) <= 8 and abs(a.y() - b.y()) <= 8

    def _pen_point(self, event):
        p = self.snap_point(self.mapToScene(event.position().toPoint()))
        if event.modifiers() & Qt.ShiftModifier and self._pen and self._pen["nodes"]:
            last = self._pen["nodes"][-1]
            dx, dy = p.x() - last[0], p.y() - last[1]
            angle = round(math.atan2(dy, dx) / (math.pi / 4)) * (math.pi / 4)
            length = math.hypot(dx, dy)
            p = QPointF(last[0] + length * math.cos(angle), last[1] + length * math.sin(angle))
        return p

    def _finish_pen(self, closed):
        if not self._pen:
            return
        nodes = []
        for n in self._pen["nodes"]:
            if not nodes or abs(n[0] - nodes[-1][0]) > 1e-6 or abs(n[1] - nodes[-1][1]) > 1e-6:
                nodes.append(n)
        self._clear_pen()
        if len(nodes) >= (3 if closed else 2) or (closed and len(nodes) == 2 and nodes[0][4] is not None):
            self.signals.pen_drawn.emit([{"closed": closed, "nodes": nodes}])

    # ---- freehand: draw with the mouse button held; ends near the start: closed
    def _draw_freehand(self):
        if self._draw_item is not None and self._draw_item.scene() is not None:
            self.scene().removeItem(self._draw_item)
        qp = QPainterPath(QPointF(*self._freehand[0]))
        for p in self._freehand[1:]:
            qp.lineTo(QPointF(*p))
        self._draw_item = self.scene().addPath(qp, _cosmetic_pen(COLORS["selection"], 1.3))
        self._draw_item.setZValue(30)

    def _finish_freehand(self, end_view_pos):
        from kerfly.core import curves
        pts, self._freehand = self._freehand, None
        if self._draw_item is not None and self._draw_item.scene() is not None:
            self.scene().removeItem(self._draw_item)
        self._draw_item = None
        if not pts or len(pts) < 2:
            return
        start = self.mapFromScene(QPointF(*pts[0]))
        closed = len(pts) > 10 and abs(start.x() - end_view_pos.x()) <= 10 and abs(start.y() - end_view_pos.y()) <= 10
        tol = 1.5 / max(abs(self.transform().m11()), 1e-9)          # 1.5 screen pixels, in mm
        simple = curves.simplify(pts, tol)
        if closed and len(simple) > 3:
            simple = simple[:-1]
        if len(simple) < 2:
            return
        self.signals.pen_drawn.emit(curves.smooth_path(simple, closed and len(simple) >= 3))

    # ---- ruler: drag between two points (snapping works) -------------------------
    def _clear_measure(self):
        self._measure_start = None
        if self._measure_item is not None and self._measure_item.scene() is not None:
            self.scene().removeItem(self._measure_item)
        self._measure_item = None

    def _draw_measure(self, a, b):
        if self._measure_item is not None and self._measure_item.scene() is not None:
            self.scene().removeItem(self._measure_item)
        qp = QPainterPath(a)
        qp.lineTo(b)
        pen = _cosmetic_pen(COLORS["head"], 1.5)
        item = self.scene().addPath(qp, pen)
        item.setZValue(48)
        for p in (a, b):
            tick = QGraphicsEllipseItem(-3, -3, 6, 6, item)
            tick.setPen(pen)
            tick.setFlag(QGraphicsItem.ItemIgnoresTransformations, True)
            tick.setPos(p)
        dx, dy = b.x() - a.x(), b.y() - a.y()
        dist = math.hypot(dx, dy)
        k, unit = (1.0, "mm") if self.units == "mm" else (1 / 25.4, "in")
        text = "%.2f %s   (%.2f × %.2f, %.1f°)" % (dist * k, unit, abs(dx) * k, abs(dy) * k,
                                                           math.degrees(math.atan2(-dy, dx)))
        label = QGraphicsSimpleTextItem(text, item)
        label.setBrush(QBrush(COLORS["head"]))
        label.setFlag(QGraphicsItem.ItemIgnoresTransformations, True)
        label.setPos(QPointF((a.x() + b.x()) / 2.0, (a.y() + b.y()) / 2.0))
        self._measure_item = item

    def mouseDoubleClickEvent(self, event):
        if self.tool == "nodes" and event.button() == Qt.LeftButton and self._node_item is not None:
            from kerfly.gui.node_editor import HandleMark, NodeMark
            hit = self.itemAt(event.position().toPoint())
            if not isinstance(hit, (NodeMark, HandleMark)):
                self.node_editor.insert_at(self.mapToScene(event.position().toPoint()))
                event.accept()
                return
        if self.tool == "polyline" and event.button() == Qt.LeftButton:
            self._finish_polyline(False)
            event.accept()
            return
        if self.tool == "pen" and event.button() == Qt.LeftButton:
            self._finish_pen(False)
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def mousePressEvent(self, event):
        if self.tool == "measure" and event.button() == Qt.LeftButton:
            self._clear_measure()
            self._measure_start = self.snap_point(self.mapToScene(event.position().toPoint()))
            event.accept()
            return
        if self.tool == "freehand" and event.button() == Qt.LeftButton:
            p = self.snap_point(self.mapToScene(event.position().toPoint()))
            self.hide_snap_marker()
            self._freehand = [(p.x(), p.y())]
            event.accept()
            return
        if self.tool == "pen" and event.button() == Qt.LeftButton:
            from kerfly.core import curves
            p = self._pen_point(event)
            if self._pen_near_first(p):
                self._finish_pen(True)
            else:
                if self._pen is None:
                    self._pen = {"nodes": [], "pressed": False}
                self._pen["nodes"].append(curves.node(p.x(), p.y()))
                self._pen["pressed"] = True
                self._draw_pen()
            event.accept()
            return
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
            self._user_zoomed = True             # panned: keep this view when the window is resized
            self._panning = event.position()
            self.setCursor(Qt.ClosedHandCursor)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.tool not in ("select", "nodes") and self._draw_start is None and not self._poly_points \
                and not self._pen and self._freehand is None and self._measure_start is None \
                and not event.buttons():
            self.snap_point(self.mapToScene(event.position().toPoint()))     # shows where a click lands
        if self.tool == "measure" and self._measure_start is not None:
            end = self.snap_point(self.mapToScene(event.position().toPoint()))
            self._draw_measure(self._measure_start, end)
            event.accept()
            return
        if self.tool == "freehand" and self._freehand is not None:
            pos = self.mapToScene(event.position().toPoint())
            last = self._freehand[-1]
            if math.hypot(pos.x() - last[0], pos.y() - last[1]) > 0.4 / max(abs(self.transform().m11()), 1e-9):
                self._freehand.append((pos.x(), pos.y()))
                self._draw_freehand()
            event.accept()
            return
        if self.tool == "pen" and self._pen:
            pos = self.mapToScene(event.position().toPoint())
            if self._pen["pressed"]:                      # dragging out the handles of the new node
                n = self._pen["nodes"][-1]
                if math.hypot(pos.x() - n[0], pos.y() - n[1]) > 0.5 * self._snap_tolerance():
                    n[4], n[5] = pos.x(), pos.y()
                    n[2], n[3] = 2 * n[0] - pos.x(), 2 * n[1] - pos.y()
                self._draw_pen()
            else:
                self._draw_pen(self._pen_point(event))
            event.accept()
            return
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
        if self.tool == "measure" and event.button() == Qt.LeftButton and self._measure_start is not None:
            end = self.snap_point(self.mapToScene(event.position().toPoint()))
            self.hide_snap_marker()
            self._draw_measure(self._measure_start, end)
            self.signals.measured.emit(end.x() - self._measure_start.x(), end.y() - self._measure_start.y())
            self._measure_start = None
            event.accept()
            return
        if self.tool == "freehand" and event.button() == Qt.LeftButton and self._freehand is not None:
            self._finish_freehand(event.position())
            event.accept()
            return
        if self.tool == "pen" and event.button() == Qt.LeftButton:
            if self._pen:
                self._pen["pressed"] = False
            event.accept()
            return
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

    def event(self, event):
        # in the node tool, its letter keys and Delete go to the nodes, not to menu shortcuts
        from PySide6.QtCore import QEvent
        if event.type() == QEvent.ShortcutOverride and self.tool == "nodes" and self._node_item is not None:
            from kerfly.gui.node_editor import KEYS
            if event.key() in KEYS and not event.modifiers() & (Qt.ControlModifier | Qt.AltModifier):
                event.accept()
                return True
        return super().event(event)

    def keyPressEvent(self, event):
        """Arrow keys move the selected element (1 mm or one grid step; Shift: 10x).
        Escape leaves a drawing tool."""
        if self.tool == "nodes" and self._node_item is not None and self.node_editor.key(event):
            event.accept()
            return
        if self.tool == "pen" and self._pen:
            if event.key() in (Qt.Key_Return, Qt.Key_Enter):
                self._finish_pen(False)
                event.accept()
                return
            if event.key() == Qt.Key_Backspace:
                self._pen["nodes"].pop()
                if not self._pen["nodes"]:
                    self._clear_pen()
                else:
                    self._draw_pen()
                event.accept()
                return
            if event.key() == Qt.Key_Escape:
                self._clear_pen()
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
        self._user_zoomed = False
        rect = self.scene().itemsBoundingRect()
        if not rect.isEmpty():
            self.fitInView(rect.adjusted(-5, -5, 5, 5), Qt.KeepAspectRatio)
            self._place_handles()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if not self._fitted or not getattr(self, "_user_zoomed", False):
            self.fit_all()                       # the bed follows the window size until you zoom

    # ---- selection and handles ----------------------------------------
    def _selected_items(self):
        return [i for i in self.scene().selectedItems() if isinstance(i, ElementItem)]

    def _selection_changed(self):
        if self._rebuilding or getattr(self, "_expanding", False):
            return
        groups = {i.element.group for i in self._selected_items() if i.element.group}
        if groups and self.tool != "nodes":         # a group is selected as a whole (nodes: one shape)
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

    # ---- node tool (kerfly.gui.node_editor) --------------------------------
    def _place_nodes(self, item):
        if item is None or self.node_points_provider is None:
            self.node_editor.detach()
            return
        found = self.node_points_provider(item.element)
        if not found:
            self.node_editor.detach()
            return
        self.node_editor.attach(item, found)

    @property
    def _node_item(self):
        return self.node_editor.item

    @property
    def _node_handles(self):
        return list(self.node_editor._marks.values())

    def node_scene_points(self):
        """Nodes of the edited shape (scene mm), in order."""
        if self.node_editor.path is None:
            return []
        return [QPointF(n[0], n[1]) for sp in self.node_editor.path for n in sp["nodes"]]

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
        self.node_editor.forget_graphics()
        self._guides = None
        scene.clear()
        self._items, self._handles = [], []
        bed_w, bed_h = bed_size_inches(values)
        self.units = values.get("units", "mm")
        self._measure_item = None
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
