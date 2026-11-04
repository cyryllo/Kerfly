"""
Node editing in the bed view (the Edit nodes tool), modelled on MeerK40t's
node editor:

    click a node                 select it (Shift+click: add to the selection)
    drag a node                  move it (all selected nodes move together)
    drag a round handle          bend the curve; a smooth node keeps both handles
                                 in line (hold Ctrl to move one handle alone)
    double-click a side          add a node there
    double-click a node          remove it
    keys / buttons               I insert, D or Delete remove, L line, C curve,
                                 O smooth, S symmetric, Z close / open, B break

The path is edited in scene coordinates and handed back to the main window
(signal nodes_changed) when a change is finished.

Copyright (C) 2026 Kerfly contributors
Licensed under the GNU General Public License v3 or later. See LICENSE.
"""
import math

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QBrush, QColor, QPainterPath, QPen
from PySide6.QtWidgets import QGraphicsEllipseItem, QGraphicsItem, QGraphicsRectItem

from kerfly.core import curves
from kerfly.core import snap as snapping

ACTIONS = ("insert", "delete", "line", "curve", "smooth", "symmetric", "close", "break")
KEYS = {Qt.Key_I: "insert", Qt.Key_D: "delete", Qt.Key_Delete: "delete", Qt.Key_Backspace: "delete",
        Qt.Key_L: "line", Qt.Key_C: "curve", Qt.Key_O: "smooth", Qt.Key_S: "symmetric",
        Qt.Key_Z: "close", Qt.Key_B: "break"}
BLUE = QColor("#1e88e5")


def _pen(color, width=1.5, style=Qt.SolidLine):
    pen = QPen(color, width, style)
    pen.setCosmetic(True)
    return pen


class _Grip:
    """Shared mouse handling of node and handle markers."""

    def _press(self, event):
        if event.button() != Qt.LeftButton:
            return False
        self._moved = False
        self.editor.pressed(self, bool(event.modifiers() & Qt.ShiftModifier))
        event.accept()
        return True

    def _move(self, event):
        self._moved = True
        self.editor.dragged(self, event.scenePos(), bool(event.modifiers() & Qt.ControlModifier))
        event.accept()

    def _release(self, event):
        self.editor.released(self, getattr(self, "_moved", False))
        event.accept()


class NodeMark(_Grip, QGraphicsRectItem):
    def __init__(self, editor, sub, i):
        QGraphicsRectItem.__init__(self, -4.5, -4.5, 9, 9)
        self.editor, self.key = editor, (sub, i)
        self.setFlag(QGraphicsItem.ItemIgnoresTransformations, True)
        self.setZValue(46)
        self.setCursor(Qt.SizeAllCursor)
        self.setPen(_pen(BLUE))

    def mousePressEvent(self, event):
        if not self._press(event):
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        self._move(event)

    def mouseReleaseEvent(self, event):
        self._release(event)

    def mouseDoubleClickEvent(self, event):
        self.editor.select({self.key})
        self.editor.action("delete")
        event.accept()


class HandleMark(_Grip, QGraphicsEllipseItem):
    def __init__(self, editor, sub, i, which):
        QGraphicsEllipseItem.__init__(self, -4, -4, 8, 8)
        self.editor, self.key, self.which = editor, (sub, i), which
        self.setFlag(QGraphicsItem.ItemIgnoresTransformations, True)
        self.setZValue(47)
        self.setCursor(Qt.CrossCursor)
        self.setPen(_pen(BLUE))
        self.setBrush(QBrush(QColor("white")))

    def mousePressEvent(self, event):
        if not self._press(event):
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        self._move(event)

    def mouseReleaseEvent(self, event):
        self._release(event)


class NodeEditor:
    def __init__(self, view):
        self.view = view
        self.item = None             # ElementItem being edited
        self.path = None             # its subpaths in scene coordinates
        self.selected = set()        # {(sub, i)}
        self._element = None
        self._marks = {}
        self._handles = []
        self._lines = None
        self._outline = None

    # ---- attach / detach -------------------------------------------------------------
    def attach(self, item, local_subpaths):
        same = self._element is item.element
        self.clear_graphics()
        self.item = item
        self._element = item.element
        t = item.sceneTransform()

        def m(x, y):
            return t.map(x, y)
        path = []
        for sp in local_subpaths:
            nodes = []
            for n in sp["nodes"]:
                x, y = m(n[0], n[1])
                hin = m(n[2], n[3]) if n[2] is not None else None
                hout = m(n[4], n[5]) if n[4] is not None else None
                nodes.append(curves.node(x, y, hin, hout))
            path.append({"closed": bool(sp.get("closed")), "nodes": nodes})
        self.path = path
        if not same:
            self.selected = set()
        self.selected = {k for k in self.selected if k[0] < len(path) and k[1] < len(path[k[0]]["nodes"])}
        self.draw()

    def detach(self):
        self.clear_graphics()
        self.item = None
        self.path = None
        self._element = None
        self.selected = set()
        self.view.signals.node_selection.emit(0)

    def clear_graphics(self):
        scene = self.view.scene()
        for it in list(self._marks.values()) + self._handles + [self._lines, self._outline]:
            if it is not None and it.scene() is scene:
                scene.removeItem(it)
        self._marks, self._handles, self._lines, self._outline = {}, [], None, None

    def forget_graphics(self):
        """The scene was cleared: the items are gone already."""
        self._marks, self._handles, self._lines, self._outline = {}, [], None, None

    # ---- drawing ---------------------------------------------------------------------
    def draw(self):
        self.clear_graphics()
        if self.path is None:
            return
        scene = self.view.scene()
        self._outline = scene.addPath(self._outline_path(), _pen(BLUE, 1.2, Qt.DashLine))
        self._outline.setZValue(44)
        for s, sp in enumerate(self.path):
            for i, n in enumerate(sp["nodes"]):
                mark = NodeMark(self, s, i)
                mark.setPos(QPointF(n[0], n[1]))
                scene.addItem(mark)
                self._marks[(s, i)] = mark
        self._style_marks()
        self._draw_handles()

    def _outline_path(self):
        qp = QPainterPath()
        for poly in curves.flatten(self.path, tol=0.05):
            qp.moveTo(QPointF(*poly[0]))
            for p in poly[1:]:
                qp.lineTo(QPointF(*p))
        return qp

    def _style_marks(self):
        self.view.signals.node_selection.emit(len(self.selected) if self.path is not None else 0)
        for key, mark in self._marks.items():
            mark.setBrush(QBrush(BLUE if key in self.selected else QColor("white")))

    def _draw_handles(self):
        scene = self.view.scene()
        for h in self._handles:
            if h.scene() is scene:
                scene.removeItem(h)
        self._handles = []
        if self._lines is not None and self._lines.scene() is scene:
            scene.removeItem(self._lines)
        lines = QPainterPath()
        for s, i in sorted(self.selected):
            n = self.path[s]["nodes"][i]
            for which, k in (("in", 2), ("out", 4)):
                if n[k] is None:
                    continue
                h = HandleMark(self, s, i, which)
                h.setPos(QPointF(n[k], n[k + 1]))
                scene.addItem(h)
                self._handles.append(h)
                lines.moveTo(QPointF(n[0], n[1]))
                lines.lineTo(QPointF(n[k], n[k + 1]))
        self._lines = scene.addPath(lines, _pen(BLUE, 1))
        self._lines.setZValue(45)

    def _refresh_positions(self):
        """Live update while dragging (no items are created or removed except handles)."""
        for (s, i), mark in self._marks.items():
            n = self.path[s]["nodes"][i]
            mark.setPos(QPointF(n[0], n[1]))
        if self._outline is not None:
            self._outline.setPath(self._outline_path())
        lines = QPainterPath()
        for h in self._handles:
            n = self.path[h.key[0]]["nodes"][h.key[1]]
            k = 2 if h.which == "in" else 4
            if n[k] is None:
                continue
            h.setPos(QPointF(n[k], n[k + 1]))
            lines.moveTo(QPointF(n[0], n[1]))
            lines.lineTo(QPointF(n[k], n[k + 1]))
        if self._lines is not None:
            self._lines.setPath(lines)

    # ---- selection -------------------------------------------------------------------
    def select(self, keys):
        if self.path is None:
            return
        self.selected = set(keys)
        self._style_marks()
        self._draw_handles()

    def pressed(self, grip, shift):
        if isinstance(grip, NodeMark):
            if shift:
                self.selected ^= {grip.key}
            elif grip.key not in self.selected:
                self.selected = {grip.key}
            self._style_marks()
            self._draw_handles()
        self._drag_start = None

    # ---- dragging --------------------------------------------------------------------
    def dragged(self, grip, pos, ctrl):
        if isinstance(grip, NodeMark):
            s, i = grip.key
            n = self.path[s]["nodes"][i]
            target = self._snap(pos, grip.key)
            dx, dy = target.x() - n[0], target.y() - n[1]
            for (ss, ii) in (self.selected | {grip.key}):
                m = self.path[ss]["nodes"][ii]
                curves.move_node(self.path, ss, ii, m[0] + dx, m[1] + dy)
        else:
            s, i = grip.key
            target = self.view.snap_point(pos, exclude=(self.item,)) if not ctrl else pos
            curves.move_handle(self.path, s, i, grip.which, target.x(), target.y(), keep_smooth=not ctrl)
        self._refresh_positions()

    def released(self, grip, moved):
        self.view.hide_snap_marker()
        self.view._remove_guides()
        if moved:
            self.commit()

    def _snap(self, pos, key):
        """Snap a dragged node: own other nodes, other elements, in line with a node, grid."""
        view = self.view
        if view.snap_suspended():
            view.hide_snap_marker()
            view._remove_guides()
            return pos
        others = [(n[0], n[1]) for s, sp in enumerate(self.path) for i, n in enumerate(sp["nodes"])
                  if (s, i) != key and (s, i) not in self.selected]
        if view.snap_objects:
            tol = view._snap_tolerance()
            own = []
            if others:
                shape = snapping.SnapShape([], (min(p[0] for p in others), min(p[1] for p in others),
                                                max(p[0] for p in others), max(p[1] for p in others)))
                shape.points = [(x, y, snapping.CORNER) for x, y in others]
                shape.segments = []
                own = [shape]
            hit = snapping.find_snap(pos.x(), pos.y(), own + view._snap_shapes((self.item,)), tol)
            if hit is not None:
                view._remove_guides()
                view.show_snap_marker(*hit)
                return QPointF(hit[0], hit[1])
            aligned = snapping.find_axis_snap(pos.x(), pos.y(), others, tol)
            if aligned is not None:
                x, y, guides = aligned
                view.show_snap_marker(x, y, snapping.ALIGNED)
                view._show_guides(guides)
                return QPointF(x, y)
        view._remove_guides()
        return view.snap_point(pos, exclude=(self.item,))

    # ---- changes -----------------------------------------------------------------------
    def commit(self):
        if self.item is not None and self.path is not None:
            self.view.signals.nodes_changed.emit(self.item.element, curves.copy_path(self.path), True)

    def insert_at(self, p):
        """Add a node on the nearest side, where it was double-clicked."""
        if self.path is None:
            return False
        best = None
        for s, sp in enumerate(self.path):
            for k, seg in enumerate(curves.segments_of(sp)):
                for step in range(0, 101):
                    t = step / 100.0
                    x, y = curves.bezier_point(seg, t)
                    d = math.hypot(x - p.x(), y - p.y())
                    if best is None or d < best[0]:
                        best = (d, s, k, t)
        if best is None or best[0] > 3 * self.view._snap_tolerance():
            return False
        _d, s, k, t = best
        t = min(max(t, 0.01), 0.99)
        i = curves.insert_node(self.path, s, k, t)
        self.selected = {(s, i)}
        self.commit()
        return True

    def action(self, code):
        """Apply a node command to the selected nodes (insert, delete, line,
        curve, smooth, symmetric, close, break)."""
        if self.path is None:
            return False
        keys = sorted(self.selected, reverse=True)      # from the end, so indexes stay valid
        changed = False
        if code == "close":
            for s in sorted({k[0] for k in keys} or set(range(len(self.path)))):
                changed |= curves.toggle_closed(self.path, s)
        elif not keys:
            return False
        elif code == "delete":
            for s, i in keys:
                changed |= curves.delete_node(self.path, s, i)
            self.selected = set()
        elif code == "insert":
            new = set()
            for s, i in keys:
                segs = curves.segments_of(self.path[s])
                if i < len(segs):
                    new.add((s, curves.insert_node(self.path, s, i, 0.5)))
                    changed = True
            self.selected = new
        elif code == "break":
            s, i = keys[0]
            changed = curves.break_at(self.path, s, i)
            self.selected = set()
        else:
            for s, i in keys:
                if code == "line":
                    curves.make_line(self.path, s, i)
                elif code == "curve":
                    curves.make_curve(self.path, s, i)
                elif code in ("smooth", "symmetric"):
                    curves.smooth_node(self.path, s, i, symmetric=code == "symmetric")
                changed = True
        if changed:
            self.commit()
        return changed

    def key(self, event):
        code = KEYS.get(event.key())
        if code is None or event.modifiers() & (Qt.ControlModifier | Qt.AltModifier):
            return False
        return self.action(code) or code in ("delete",)
