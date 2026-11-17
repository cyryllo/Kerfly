"""
3D preview of a generated box (the Generators' 3D tab): the real parts of the
generator (their outlines, holes and the material's thickness) put together as
solids, drawn with Qt alone. Drag to turn it, the wheel zooms; "exploded"
pulls the parts apart to show the joints; a sliding lid can be slid out;
hidden edges (behind other parts) can be shown dashed.

How it is drawn without a depth buffer: every face of every part (its two
faces, its sides, the sides of its slots) is put into a BSP tree once, when
the box changes: the faces are split by each other's planes until each piece
lies wholly on one side of every plane above it in the tree. Drawing walks the
tree from the far side to the near side of each plane, so every piece is drawn
after everything behind it, also where parts reach into each other (fingers,
tabs in slots); faces turned away from the viewer are left out. Only the
faces' real edges are drawn, not the cuts the tree made.

A bent wall (rounded box) is made of its flat strips with their slots, laid
along its path: each straight piece of the path takes the part of the strips
over it, flat.

Copyright (C) 2026 Kerfly contributors
Licensed under the GNU General Public License v3 or later. See LICENSE.
"""
import math

from PySide6.QtCore import QLineF, QPointF, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPainterPath, QPen, QPolygonF
from PySide6.QtWidgets import QWidget

from kerfly.gui import theme

WOOD = [QColor(c) for c in theme.CANVAS["wood"]]
LIGHT = (-0.4, -0.77, 0.5)                      # in view coordinates: from the upper left, towards the viewer
EPS = 1e-3                                      # mm: on a plane
SHARP = math.cos(math.radians(20))              # a bend of a part's outline sharper than this has an edge


def _add(a, b, k=1.0):
    return (a[0] + b[0] * k, a[1] + b[1] * k, a[2] + b[2] * k)


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _norm(v):
    length = math.sqrt(v[0] ** 2 + v[1] ** 2 + v[2] ** 2) or 1.0
    return (v[0] / length, v[1] / length, v[2] / length)


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _area2(loop):
    return sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(loop, loop[1:] + loop[:1])) / 2.0


def _newell(loop):
    """Twice the vector area of a 3D loop (its normal times twice its area)."""
    nx = ny = nz = 0.0
    for a, b in zip(loop, loop[1:] + loop[:1]):
        nx += (a[1] - b[1]) * (a[2] + b[2])
        ny += (a[2] - b[2]) * (a[0] + b[0])
        nz += (a[0] - b[0]) * (a[1] + b[1])
    return nx, ny, nz


def _clip(loop, flags, dist, keep):
    """The part of a loop (points of any dimension) where keep * dist(p) >= 0; flags[i]: the edge from point i
    to the next one is a real edge (not a cut). The new edges along the cut are not real edges.
    Returns (loop, flags) or None when nothing is left."""
    ds = [keep * dist(p) for p in loop]
    out, oflags = [], []
    n = len(loop)
    for i in range(n):
        a, b = loop[i], loop[(i + 1) % n]
        da, db, f = ds[i], ds[(i + 1) % n], flags[i]
        a_in, b_in = da >= -EPS, db >= -EPS
        if a_in and b_in:
            out.append(a)
            oflags.append(f)
        elif a_in:
            if da > EPS:
                out.append(a)
                oflags.append(f)
                k = da / (da - db)
                out.append(tuple(a[c] + (b[c] - a[c]) * k for c in range(len(a))))
                oflags.append(False)
            else:
                out.append(a)
                oflags.append(False)
        elif b_in and db > EPS:
            k = da / (da - db)
            out.append(tuple(a[c] + (b[c] - a[c]) * k for c in range(len(a))))
            oflags.append(f)
    if len(out) < 3:
        return None
    return out, oflags


class Poly:
    """A flat face (or a piece of one): loops (3D; the first the outline, the rest holes, filled odd-even),
    flags (which edges are real), its outward normal and plane, the part it belongs to."""
    __slots__ = ("loops", "flags", "normal", "d", "part", "key", "centre", "radius")

    def __init__(self, loops, flags, normal, part, d=None):
        self.loops = loops
        self.flags = flags
        self.normal = normal
        self.d = _dot(normal, loops[0][0]) if d is None else d
        self.part = part
        n, d = normal, self.d
        if (n[0], n[1], n[2]) < (0.0, 0.0, 0.0):          # one key for both sides of a plane
            n, d = (-n[0], -n[1], -n[2]), -d
        self.key = (round(n[0], 4), round(n[1], 4), round(n[2], 4), round(d, 2))
        pts = loops[0]
        self.centre = tuple(sum(q[i] for q in pts) / len(pts) for i in range(3))
        self.radius = max(math.dist(q, self.centre) for q in pts)


def _face(loops, normal, part):
    return Poly(loops, [[True] * len(lp) for lp in loops], normal, part)


def _slab_faces(origin, u, v, n, t, loops, part):
    """The faces of a flat part: its two faces and the sides of its outline and holes."""
    def at(x, y, depth):
        return _add(_add(_add(origin, u, x), v, y), n, depth)
    out = [_face([[at(x, y, 0.0) for x, y in lp] for lp in loops], (-n[0], -n[1], -n[2]), part),
           _face([[at(x, y, t) for x, y in lp] for lp in loops], tuple(n), part)]
    for k, lp in enumerate(loops):
        sign = 1.0 if (k == 0) == (_area2(lp) > 0) else -1.0       # outward: right of the outline's way
        m = len(lp)
        dirs = []
        for i in range(m):
            (x1, y1), (x2, y2) = lp[i], lp[(i + 1) % m]
            length = math.hypot(x2 - x1, y2 - y1)
            dirs.append(((x2 - x1) / length, (y2 - y1) / length) if length > 1e-9 else None)

        def sharp(i):                       # is there an edge across the side at point i?
            a, b = dirs[i - 1], dirs[i]
            return a is None or b is None or a[0] * b[0] + a[1] * b[1] < SHARP
        for i in range(m):
            if dirs[i] is None:
                continue
            (x1, y1), (x2, y2) = lp[i], lp[(i + 1) % m]
            nx, ny = sign * dirs[i][1], -sign * dirs[i][0]
            normal = _norm(_add(tuple(c * nx for c in u), v, ny))
            quad = [at(x1, y1, 0.0), at(x2, y2, 0.0), at(x2, y2, t), at(x1, y1, t)]
            out.append(Poly([quad], [[True, sharp((i + 1) % m), True, sharp(i)]], normal, part))
    return out


def _band_faces(part, shift, index):
    """The faces of a bent wall: on each straight piece of its path, the part of its strips over it (their
    slots too), flat."""
    pts = [_add(p, shift) for p in part["path"]]
    normals, h, t = part["out"], part["height"], part["t"]
    closed = part.get("closed")
    n = len(pts)
    pieces = list(range(n)) if closed else list(range(n - 1))
    s_at = [0.0]
    for i in pieces:
        s_at.append(s_at[-1] + math.dist(pts[i], pts[(i + 1) % n]))
    total = s_at[-1]
    strips = part.get("strips")
    if strips:
        scale = total / float(part.get("length") or total)
    else:                                       # a plain band: one strip all along
        strips = [{"loops": [[(0.0, 0.0), (total, 0.0), (total, h), (0.0, h)]], "start": 0.0}]
        scale = 1.0
    out = []
    for k, i in enumerate(pieces):
        j = (i + 1) % n
        a, b = pts[i], pts[j]
        a2, b2 = _add(a, normals[i], t), _add(b, normals[j], t)
        s0, s1 = s_at[k], s_at[k + 1]
        if s1 - s0 < 1e-9:
            continue
        along = _norm(_sub(b, a))
        outward = _norm(_cross(along, (0.0, 0.0, 1.0)))
        if _dot(outward, normals[i]) < 0:
            outward = (-outward[0], -outward[1], -outward[2])

        def inner(p, a=a, b=b, s0=s0, s1=s1):
            f = (p[0] - s0) / (s1 - s0)
            return (a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f, a[2] + h - p[1])

        def outer(p, a2=a2, b2=b2, s0=s0, s1=s1):
            f = (p[0] - s0) / (s1 - s0)
            return (a2[0] + (b2[0] - a2[0]) * f, a2[1] + (b2[1] - a2[1]) * f, a2[2] + h - p[1])
        for strip in strips:
            for wrap in ((-total, 0.0, total) if closed else (0.0,)):
                off = strip["start"] * scale + wrap
                loops, flags = [], []
                for m, lp in enumerate(strip["loops"]):
                    moved = [(x * scale + off, y) for x, y in lp]
                    res = _clip(moved, [True] * len(moved), lambda p, s0=s0: p[0] - s0, 1)
                    res = res and _clip(res[0], res[1], lambda p, s1=s1: s1 - p[0], 1)
                    if res and abs(_area2(res[0])) > 1e-6:
                        loops.append(res[0])
                        flags.append(res[1])
                    elif m == 0:
                        break
                if not loops:
                    continue
                out.append(Poly([[inner(p) for p in lp] for lp in loops], [list(f) for f in flags],
                                (-outward[0], -outward[1], -outward[2]), index))
                out.append(Poly([[outer(p) for p in lp] for lp in loops], [list(f) for f in flags], outward, index))
                for m, (lp, fl) in enumerate(zip(loops, flags)):
                    sign = 1.0 if (m == 0) == (_area2(lp) > 0) else -1.0
                    for q in range(len(lp)):
                        if not fl[q]:
                            continue                     # a cut between pieces of the path: no side there
                        p1, p2 = lp[q], lp[(q + 1) % len(lp)]
                        dx, dy = p2[0] - p1[0], p2[1] - p1[1]
                        if dx * dx + dy * dy < 1e-12:
                            continue
                        # the side's outward direction: x of the strip runs along the path, y down
                        nx, ny = sign * dy, -sign * dx
                        normal = _norm(_add(tuple(c * nx for c in along), (0.0, 0.0, -1.0), ny))
                        quad = [inner(p1), inner(p2), outer(p2), outer(p1)]
                        across = abs(dx) < 1e-9          # a slot's or a strip end's side: corners at its ends
                        out.append(Poly([quad], [[True, across, True, across]], normal, index))
    return out


def faces(assembly, exploded=0.0, lid_out=0.0):
    """Every face of the box: exploded: mm each part moves away from the middle of the box; lid_out: mm a
    sliding lid moves out (towards the front)."""
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
    box_mid = tuple(sum(c[i] for c in centres) / len(centres) for i in range(3)) if centres else (0.0, 0.0, 0.0)
    out = []
    for index, (part, centre) in enumerate(zip(assembly, centres)):
        shift = (0.0, 0.0, 0.0)
        if exploded:
            d = _sub(centre, box_mid)
            if math.sqrt(_dot(d, d)) > 1e-6:
                shift = tuple(c * exploded for c in _norm(d))
        if part.get("kind") == "band":
            out += _band_faces(part, shift, index)
            continue
        o = _add(part["origin"], shift)
        if lid_out and part.get("slides"):
            o = _add(o, (0.0, -1.0, 0.0), lid_out)
        loops = [list(map(tuple, lp)) for lp in part["loops"] if len(lp) >= 3]
        out += _slab_faces(o, part["u"], part["v"], part["n"], part["t"], loops, index)
    return out


def _split(poly, n, d):
    """(front, back) pieces of a face cut by the plane n.p = d (None for an empty side)."""
    sides = []
    for keep in (1, -1):
        loops, flags = [], []
        for m, (lp, fl) in enumerate(zip(poly.loops, poly.flags)):
            res = _clip(lp, fl, lambda p: _dot(n, p) - d, keep)
            if res and sum(abs(c) for c in _newell(res[0])) > 1e-6:
                loops.append(res[0])
                flags.append(res[1])
            elif m == 0:
                break
        sides.append(Poly(loops, flags, poly.normal, poly.part, poly.d) if loops else None)
    return sides


class Node:
    __slots__ = ("normal", "d", "faces", "front", "back")

    def __init__(self, normal, d, faces):
        self.normal, self.d, self.faces = normal, d, faces
        self.front = self.back = None


def build(polys):
    """The BSP tree of the faces (the plane shared by most faces first)."""
    root = None
    work = [(list(polys), None, "")]
    while work:
        polys, parent, side = work.pop()
        if not polys:
            continue
        counts = {}
        for p in polys:
            counts[p.key] = counts.get(p.key, 0) + 1
        best = max(counts, key=counts.get)
        rep = next(p for p in polys if p.key == best)
        n, d = rep.normal, rep.d
        same, front, back = [rep], [], []
        for p in polys:
            if p is rep:
                continue
            dc = _dot(n, p.centre) - d
            if dc > p.radius + EPS:
                front.append(p)
                continue
            if dc < -p.radius - EPS:
                back.append(p)
                continue
            ds = [_dot(n, q) - d for lp in p.loops for q in lp]
            lo, hi = min(ds), max(ds)
            if lo > -EPS and hi < EPS:
                same.append(p)
            elif lo > -EPS:
                front.append(p)
            elif hi < EPS:
                back.append(p)
            else:
                f, b = _split(p, n, d)
                if f:
                    front.append(f)
                if b:
                    back.append(b)
        node = Node(n, d, same)
        if parent is None:
            root = node
        else:
            setattr(parent, side, node)
        work.append((front, node, "front"))
        work.append((back, node, "back"))
    return root


def walk(root, toward):
    """The faces far to near for a viewer in the direction toward."""
    out = []
    stack = [root]
    while stack:
        item = stack.pop()
        if item is None:
            continue
        if isinstance(item, Node):
            if _dot(item.normal, toward) >= 0:       # the viewer in front of the plane: the back first
                stack += [item.front, item.faces, item.back]
            else:
                stack += [item.back, item.faces, item.front]
        else:
            out += item
    return out


class Box3DView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.assembly = []
        self.yaw, self.pitch, self.zoom = -35.0, 28.0, 1.0
        self.exploded = 0.0
        self.lid_out = 0.0
        self.hidden_edges = True              # the edges behind other parts, dashed
        self._drag = None
        self._model = None
        self.setMinimumSize(420, 320)
        self.setToolTip(_tip())

    def set_assembly(self, assembly):
        self.assembly = list(assembly or [])
        self._model = None
        self.update()

    def set_exploded(self, mm):
        self.exploded = float(mm)
        self._model = None
        self.update()

    def set_lid_out(self, mm):
        self.lid_out = float(mm)
        self._model = None
        self.update()

    def set_hidden_edges(self, on):
        self.hidden_edges = bool(on)
        self.update()

    def has_sliding_lid(self):
        return any(p.get("slides") for p in self.assembly)

    def model(self):
        """(faces, BSP tree, real edges, middle, radius) of the box as it is now."""
        if self._model is None:
            polys = faces(self.assembly, self.exploded, self.lid_out)
            tree = build(polys) if polys else None
            edges = {}
            for p in polys:
                for lp, fl in zip(p.loops, p.flags):
                    for i, real in enumerate(fl):
                        if real:
                            a, b = lp[i], lp[(i + 1) % len(lp)]
                            ka = tuple(round(c, 2) for c in a)
                            kb = tuple(round(c, 2) for c in b)
                            edges[(ka, kb) if ka < kb else (kb, ka)] = (a, b)
            pts = [q for p in polys for lp in p.loops for q in lp] or [(0.0, 0.0, 0.0)]
            mid = tuple((min(q[i] for q in pts) + max(q[i] for q in pts)) / 2.0 for i in range(3))
            radius = max(math.dist(q, mid) for q in pts) or 1.0
            self._model = (polys, tree, list(edges.values()), mid, radius)
        return self._model

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
    def turn(self, p):
        """A 3D direction turned into the view: (to the right, away from the viewer, up)."""
        cy, sy = math.cos(math.radians(self.yaw)), math.sin(math.radians(self.yaw))
        x, y = p[0] * cy - p[1] * sy, p[0] * sy + p[1] * cy
        cp, sp = math.cos(math.radians(self.pitch)), math.sin(math.radians(self.pitch))
        return x, y * cp - p[2] * sp, y * sp + p[2] * cp

    def toward(self):
        """The direction to the viewer, in the box's coordinates (turn() of it is (0, -1, 0))."""
        cy, sy = math.cos(math.radians(self.yaw)), math.sin(math.radians(self.yaw))
        cp, sp = math.cos(math.radians(self.pitch)), math.sin(math.radians(self.pitch))
        y, z = -cp, sp                                   # the pitch undone
        return (y * sy, y * cy, z)                       # then the yaw

    def screen(self, width, height):
        """A function: mm of the box -> the point of a width x height view."""
        _polys, _tree, _edges, mid, radius = self.model()
        k = 0.47 * min(width, height) / radius * self.zoom
        cx, cy = width / 2.0, height / 2.0
        turn = self.turn

        def to_screen(p):
            x, _y, z = turn((p[0] - mid[0], p[1] - mid[1], p[2] - mid[2]))
            return QPointF(cx + x * k, cy - z * k)
        return to_screen

    def render(self, painter, width, height, ids=False):
        """Draws the box into painter; ids: each part in a colour of its own (red = its number + 1), not
        shaded, no edges (for the tests: which part is seen where)."""
        _polys, tree, edges, _mid, _radius = self.model()
        if tree is None:
            return
        to_screen = self.screen(width, height)
        toward = self.toward()
        edge_pen = QPen(QColor(80, 56, 28, 210), 1.0)
        for p in walk(tree, toward):
            if _dot(p.normal, toward) <= 1e-9:            # turned away from the viewer
                continue
            path = QPainterPath()
            path.setFillRule(Qt.OddEvenFill)
            screen_loops = []
            for lp in p.loops:
                pts = [to_screen(q) for q in lp]
                screen_loops.append(pts)
                path.addPolygon(QPolygonF(pts))
                path.closeSubpath()
            if ids:
                painter.setPen(Qt.NoPen)
                painter.setBrush(QColor(p.part + 1, 0, 0))
                painter.drawPath(path)
                continue
            base = WOOD[p.part % len(WOOD)]
            nv = self.turn(p.normal)
            f = 0.6 + 0.4 * max(0.0, nv[0] * LIGHT[0] + nv[1] * LIGHT[1] + nv[2] * LIGHT[2])
            colour = QColor(int(base.red() * f), int(base.green() * f), int(base.blue() * f))
            painter.setPen(QPen(colour, 1.0))                 # the same colour: no seams between pieces
            painter.setBrush(colour)
            painter.drawPath(path)
            lines = [QLineF(pts[i], pts[(i + 1) % len(pts)]) for pts, fl in zip(screen_loops, p.flags)
                     for i, real in enumerate(fl) if real]
            if lines:
                painter.setPen(edge_pen)
                painter.drawLines(lines)
        if self.hidden_edges and not ids:
            painter.setPen(QPen(QColor(60, 40, 20, 110), 0.8, Qt.DashLine))
            painter.drawLines([QLineF(to_screen(a), to_screen(b)) for a, b in edges])

    def part_at(self, x, y):
        """The name of the part seen at (x, y) of the view, or "" (for the tests)."""
        img = QImage(self.width(), self.height(), QImage.Format_RGB32)
        img.fill(QColor(0, 0, 0))
        p = QPainter(img)
        self.render(p, self.width(), self.height(), ids=True)
        p.end()
        n = img.pixelColor(int(x), int(y)).red()
        return self.assembly[n - 1].get("name", "") if 0 < n <= len(self.assembly) else ""

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.fillRect(self.rect(), theme.canvas("box3d_bg"))
        self.render(p, self.width(), self.height())
        p.end()


def _tip():
    from kerfly.i18n import _
    return _("Drag to turn the box, the wheel zooms, a double click turns it back")
