"""
3D preview of a generated box (the Generators' 3D tab): the real parts of the
generator (their outlines, holes and the material's thickness) put together,
drawn with Qt alone (projection, flat shading, painter's order). Drag to turn
it, the wheel zooms; "exploded" pulls the parts apart to show the joints; a
sliding lid can be slid out.

Copyright (C) 2026 Kerfly contributors
Licensed under the GNU General Public License v3 or later. See LICENSE.
"""
import math

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QPolygonF
from PySide6.QtWidgets import QWidget

WOOD = [QColor("#d9b98c"), QColor("#cfa977"), QColor("#e3c79d"), QColor("#c99f6c")]
LIGHT = (-0.4, -0.5, 0.77)                      # towards the viewer, from the upper left


def _add(a, b, k=1.0):
    return (a[0] + b[0] * k, a[1] + b[1] * k, a[2] + b[2] * k)


def _norm(v):
    length = math.sqrt(v[0] ** 2 + v[1] ** 2 + v[2] ** 2) or 1.0
    return (v[0] / length, v[1] / length, v[2] / length)


def faces(assembly, exploded=0.0, lid_out=0.0):
    """[(polygons (lists of 3D points; the first is the outline, the rest holes), colour index)] of the box.
    exploded: mm each part moves away from the middle of the box; lid_out: mm a sliding lid moves out."""
    out = []
    centres = []
    for part in assembly:
        if part.get("kind") == "band":
            pts = part["path"]
            centres.append(tuple(sum(p[i] for p in pts) / len(pts) for i in range(2)) + (part["height"] / 2.0,))
        else:
            o, u, v = part["origin"], part["u"], part["v"]
            loop = part["loops"][0]
            mx = sum(x for x, _ in loop) / len(loop)
            my = sum(y for _, y in loop) / len(loop)
            centres.append(_add(_add(o, u, mx), v, my))
    if centres:
        box_mid = tuple(sum(c[i] for c in centres) / len(centres) for i in range(3))
    else:
        box_mid = (0.0, 0.0, 0.0)
    for index, (part, centre) in enumerate(zip(assembly, centres)):
        shift = (0.0, 0.0, 0.0)
        if exploded:
            d = (centre[0] - box_mid[0], centre[1] - box_mid[1], centre[2] - box_mid[2])
            shift = tuple(c * exploded for c in _norm(d))
        colour = index % len(WOOD)
        if part.get("kind") == "band":
            out += _band_faces(part, shift, colour)
            continue
        o = _add(part["origin"], shift)
        if lid_out and part.get("slides"):
            o = _add(o, (0, -1, 0), lid_out)                 # out towards the front
        u, v, n, t = part["u"], part["v"], part["n"], part["t"]

        def at(x, y, depth):
            return _add(_add(_add(o, u, x), v, y), n, depth)
        front = [[at(x, y, 0.0) for x, y in loop] for loop in part["loops"]]
        back = [[at(x, y, t) for x, y in loop] for loop in part["loops"]]
        out.append((front, colour))
        out.append((back, colour))
        for loop in part["loops"]:
            for (x1, y1), (x2, y2) in zip(loop, loop[1:] + loop[:1]):
                out.append(([[at(x1, y1, 0.0), at(x2, y2, 0.0), at(x2, y2, t), at(x1, y1, t)]], colour))
    return out


def _band_faces(part, shift, colour):
    pts, normals, h, t = part["path"], part["out"], part["height"], part["t"]
    res = []
    n = len(pts)
    ring = range(n) if part.get("closed") else range(n - 1)
    for i in ring:
        j = (i + 1) % n
        a, b = _add(pts[i], shift), _add(pts[j], shift)
        na, nb = normals[i], normals[j]
        a2, b2 = _add(a, na, t), _add(b, nb, t)
        top = (0.0, 0.0, h)
        res.append(([[a, b, _add(b, top), _add(a, top)]], colour))                  # inside
        res.append(([[a2, b2, _add(b2, top), _add(a2, top)]], colour))              # outside
        res.append(([[_add(a, top), _add(b, top), _add(b2, top), _add(a2, top)]], colour))   # top edge
        res.append(([[a, b, b2, a2]], colour))                                    # bottom edge
    return res


class Box3DView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.assembly = []
        self.yaw, self.pitch, self.zoom = -35.0, 28.0, 1.0
        self.exploded = 0.0
        self.lid_out = 0.0
        self._drag = None
        self.setMinimumSize(420, 320)
        self.setToolTip(_tip())

    def set_assembly(self, assembly):
        self.assembly = list(assembly or [])
        self.update()

    def set_exploded(self, mm):
        self.exploded = float(mm)
        self.update()

    def set_lid_out(self, mm):
        self.lid_out = float(mm)
        self.update()

    def has_sliding_lid(self):
        return any(p.get("slides") for p in self.assembly)

    # ---- mouse --------------------------------------------------------------
    def mousePressEvent(self, event):
        self._drag = event.position()

    def mouseMoveEvent(self, event):
        if self._drag is not None:
            d = event.position() - self._drag
            self._drag = event.position()
            self.yaw += d.x() * 0.5
            self.pitch = max(-89.0, min(89.0, self.pitch + d.y() * 0.5))
            self.update()

    def mouseReleaseEvent(self, event):
        self._drag = None

    def mouseDoubleClickEvent(self, event):
        self.yaw, self.pitch, self.zoom = -35.0, 28.0, 1.0
        self.update()

    def wheelEvent(self, event):
        self.zoom = max(0.2, min(8.0, self.zoom * (1.15 if event.angleDelta().y() > 0 else 1 / 1.15)))
        self.update()

    # ---- drawing --------------------------------------------------------------
    def view_point(self, p, mid):
        """3D mm -> (screen x, screen y, depth) before scaling: turned by yaw about the vertical, then by
        pitch, looking along -z of the view (z up in the box)."""
        x, y, z = p[0] - mid[0], p[1] - mid[1], p[2] - mid[2]
        cy, sy = math.cos(math.radians(self.yaw)), math.sin(math.radians(self.yaw))
        x, y = x * cy - y * sy, x * sy + y * cy
        cp, sp = math.cos(math.radians(self.pitch)), math.sin(math.radians(self.pitch))
        y, z = y * cp - z * sp, y * sp + z * cp
        return x, -z, y

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.fillRect(self.rect(), QColor("#eef0f3"))
        fs = faces(self.assembly, self.exploded, self.lid_out)
        if not fs:
            p.end()
            return
        pts = [q for polys, _c in fs for poly in polys for q in poly]
        mid = tuple((min(q[i] for q in pts) + max(q[i] for q in pts)) / 2.0 for i in range(3))
        view = [[[self.view_point(q, mid) for q in poly] for poly in polys] for polys, _c in fs]
        xs = [v[0] for polys in view for poly in polys for v in poly]
        ys = [v[1] for polys in view for poly in polys for v in poly]
        span = max(max(xs) - min(xs), max(ys) - min(ys), 1.0)
        k = 0.85 * min(self.width(), self.height()) / span * self.zoom
        cx, cy = self.width() / 2.0, self.height() / 2.0
        order = []
        for polys, (_p, colour) in zip(view, fs):
            outline = polys[0]
            depth = sum(v[2] for v in outline) / len(outline)
            # the face's normal in the view, for its shade
            if len(outline) >= 3:
                a, b, c = outline[0], outline[1], outline[2]
                u = (b[0] - a[0], b[1] - a[1], b[2] - a[2])
                w = (c[0] - a[0], c[1] - a[1], c[2] - a[2])
                nrm = _norm((u[1] * w[2] - u[2] * w[1], u[2] * w[0] - u[0] * w[2], u[0] * w[1] - u[1] * w[0]))
            else:
                nrm = (0.0, 0.0, 1.0)
            shade = abs(nrm[0] * LIGHT[0] + nrm[1] * LIGHT[1] + nrm[2] * LIGHT[2])
            order.append((depth, polys, colour, shade))
        order.sort(key=lambda o: -o[0])                    # far first
        pen = QPen(QColor(90, 64, 34, 160), 0.8)
        for _d, polys, colour, shade in order:
            path = QPainterPath()
            path.setFillRule(Qt.OddEvenFill)
            for poly in polys:
                path.addPolygon(QPolygonF([QPointF(cx + v[0] * k, cy + v[1] * k) for v in poly]))
                path.closeSubpath()
            base = WOOD[colour]
            f = 0.55 + 0.45 * shade
            p.setPen(pen)
            p.setBrush(QColor(int(base.red() * f), int(base.green() * f), int(base.blue() * f)))
            p.drawPath(path)
        p.end()


def _tip():
    from kerfly.i18n import _
    return _("Drag to turn the box, the wheel zooms, a double click turns it back")
