"""
3D preview of a generated box (the Generators' 3D tab): the real parts of the
generator (their outlines, holes and the material's thickness) put together as
solids, drawn with Qt alone. Drag to turn it, the wheel zooms; "exploded"
pulls the parts apart to show the joints; a sliding lid can be slid out.

How it is drawn without a depth buffer: every part is a solid (a slab of the
material, or one piece of a bent wall), and only its faces turned towards the
viewer are drawn (its sides first, then its face), so a part never shows its
far side. The parts are put in order by the planes that separate them: a part
that lies beyond another one's slab (also when only its fingers or tabs reach
into it, as in every joint) is drawn first when the viewer is on the other
side. Parts that pass through each other (crossing dividers) are cut in two at
the other one's middle first, so every pair can be put in order.

Copyright (C) 2026 Kerfly contributors
Licensed under the GNU General Public License v3 or later. See LICENSE.
"""
import heapq
import math

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPainterPath, QPen, QPolygonF
from PySide6.QtWidgets import QWidget

WOOD = [QColor("#d9b98c"), QColor("#cfa977"), QColor("#e3c79d"), QColor("#c99f6c")]
LIGHT = (-0.4, -0.77, 0.5)                      # in view coordinates: from the upper left, towards the viewer
EPS = 1e-4
AXES = ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))


def _add(a, b, k=1.0):
    return (a[0] + b[0] * k, a[1] + b[1] * k, a[2] + b[2] * k)


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _norm(v):
    length = math.sqrt(v[0] ** 2 + v[1] ** 2 + v[2] ** 2) or 1.0
    return (v[0] / length, v[1] / length, v[2] / length)


def _area(loop):
    return sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(loop, loop[1:] + loop[:1])) / 2.0


def _clip(loop, a, b, c, keep_below):
    """The part of a 2D loop where a*x + b*y <= c (keep_below) or >= c (Sutherland-Hodgman)."""
    def inside(p):
        f = a * p[0] + b * p[1] - c
        return f <= 1e-9 if keep_below else f >= -1e-9
    out = []
    for p, q in zip(loop, loop[1:] + loop[:1]):
        pin, qin = inside(p), inside(q)
        if pin:
            out.append(p)
        if pin != qin:
            fp, fq = a * p[0] + b * p[1] - c, a * q[0] + b * q[1] - c
            k = fp / (fp - fq)
            out.append((p[0] + (q[0] - p[0]) * k, p[1] + (q[1] - p[1]) * k))
    return out if len(out) >= 3 and abs(_area(out)) > 1e-6 else None


class Solid:
    """One solid of the box: its faces [(polygons (3D, the first the outline, the rest holes), outward
    normal, is the part's face (not a side))], its points, the direction of its thickness (axis) and the
    thickness, its colour; a slab keeps its frame and loops (to be cut in two)."""

    def __init__(self, faces, axis, thick, colour, name, frame=None, splits=(), planes=()):
        self.faces = faces
        self.points = [q for polys, _n, _c in faces for poly in polys for q in poly]
        self.axis = axis
        self.thick = thick
        self.colour = colour
        self.name = name
        self.frame = frame                       # (origin, u, v, n, t, loops) of a slab
        self.splits = tuple(splits)              # the directions it was cut along
        self.planes = tuple(planes)              # more directions of its sides (a bent wall's joints)
        self._spans = {}
        self.centre = tuple(sum(p[i] for p in self.points) / len(self.points) for i in range(3))

    def span(self, d):
        s = self._spans.get(d)
        if s is None:
            values = [_dot(p, d) for p in self.points]
            s = self._spans[d] = (min(values), max(values))
        return s


def _slab(origin, u, v, n, t, loops, colour, name, splits=()):
    def at(x, y, depth):
        return _add(_add(_add(origin, u, x), v, y), n, depth)
    faces = [([[at(x, y, 0.0) for x, y in loop] for loop in loops], (-n[0], -n[1], -n[2]), True),
             ([[at(x, y, t) for x, y in loop] for loop in loops], tuple(n), True)]
    for k, loop in enumerate(loops):
        sign = 1.0 if (k == 0) == (_area(loop) > 0) else -1.0      # outward: right of the outline's way
        for (x1, y1), (x2, y2) in zip(loop, loop[1:] + loop[:1]):
            dx, dy = x2 - x1, y2 - y1
            if dx * dx + dy * dy < 1e-12:
                continue
            nx, ny = sign * dy, -sign * dx
            normal = _norm(_add(tuple(c * nx for c in u), v, ny))
            faces.append(([[at(x1, y1, 0.0), at(x2, y2, 0.0), at(x2, y2, t), at(x1, y1, t)]], normal, False))
    return Solid(faces, tuple(n), t, colour, name, (origin, u, v, n, t, loops), splits)


def _band(part, shift, colour):
    """A bent wall: one convex solid for each piece between two points of its path."""
    pts, normals, h, t = part["path"], part["out"], part["height"], part["t"]
    closed = part.get("closed")
    n = len(pts)
    top = (0.0, 0.0, h)
    out = []
    pieces = range(n) if closed else range(n - 1)
    for i in pieces:
        j = (i + 1) % n
        a, b = _add(pts[i], shift), _add(pts[j], shift)
        a2, b2 = _add(a, normals[i], t), _add(b, normals[j], t)
        outward = _norm((normals[i][0] + normals[j][0], normals[i][1] + normals[j][1], 0.0))
        along = _norm((b[0] - a[0], b[1] - a[1], b[2] - a[2]))
        faces = [([[a, b, _add(b, top), _add(a, top)]], (-outward[0], -outward[1], -outward[2]), False),
                 ([[a2, b2, _add(b2, top), _add(a2, top)]], outward, True),
                 ([[_add(a, top), _add(b, top), _add(b2, top), _add(a2, top)]], (0.0, 0.0, 1.0), False),
                 ([[a, b, b2, a2]], (0.0, 0.0, -1.0), False)]
        if not closed and i == 0:
            faces.append(([[a, a2, _add(a2, top), _add(a, top)]], (-along[0], -along[1], -along[2]), False))
        if not closed and i == n - 2:
            faces.append(([[b, b2, _add(b2, top), _add(b, top)]], along, False))
        joints = ((-normals[i][1], normals[i][0], 0.0), (-normals[j][1], normals[j][0], 0.0))
        out.append(Solid(faces, outward, t, colour, part.get("name", ""), planes=joints))
    return out


def solids(assembly, exploded=0.0, lid_out=0.0):
    """The box as solids: exploded: mm each part moves away from the middle of the box; lid_out: mm a sliding
    lid moves out (towards the front)."""
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
            d = _norm((centre[0] - box_mid[0], centre[1] - box_mid[1], centre[2] - box_mid[2]))
            shift = tuple(c * exploded for c in d)
        colour = index % len(WOOD)
        if part.get("kind") == "band":
            out += _band(part, shift, colour)
            continue
        o = _add(part["origin"], shift)
        if lid_out and part.get("slides"):
            o = _add(o, (0.0, -1.0, 0.0), lid_out)
        loops = [list(map(tuple, lp)) for lp in part["loops"] if len(lp) >= 3]
        out.append(_slab(o, part["u"], part["v"], part["n"], part["t"], loops, colour, part.get("name", "")))
    return out


def _tolerant(a, b, d, s):
    """Along the thickness d of slab b: +1 when a lies beyond b (it may reach into b's slab, as fingers and
    tabs do, but not through it), -1 when it lies before it, 0 when neither."""
    a0, a1 = a.span(d)
    b0, b1 = b.span(d)
    if a0 >= b0 - EPS and a1 > b1 + EPS:
        return s
    if a1 <= b1 + EPS and a0 < b0 - EPS:
        return -s
    return 0


def relation(a, b):
    """(d, +1 / -1): a lies beyond / before b along d (a plane across d separates them, or a's fingers only
    reach into b's slab); None when no such direction is found."""
    axes = list(AXES) + [a.axis, b.axis] + list(a.splits) + list(b.splits) + list(a.planes) + list(b.planes)
    for d in axes:                                   # a plane between them
        a0, a1 = a.span(d)
        b0, b1 = b.span(d)
        if a0 >= b1 - EPS:
            return d, 1
        if a1 <= b0 + EPS:
            return d, -1
    r = _tolerant(a, b, b.axis, 1)                   # a joint: one reaches into the other's slab
    if r:
        return b.axis, r
    r = _tolerant(b, a, a.axis, -1)
    if r:
        return a.axis, r
    return None


def _split(s, d, at):
    """A slab cut in two by the plane across d at `at` (None when the plane misses it)."""
    origin, u, v, n, t, loops = s.frame
    a, b, c = _dot(u, d), _dot(v, d), at - _dot(origin, d)
    if abs(a) < 1e-9 and abs(b) < 1e-9:
        return None
    pieces = []
    for below in (True, False):
        part = []
        for k, loop in enumerate(loops):
            clipped = _clip(loop, a, b, c, below)
            if clipped:
                part.append(clipped)
            elif k == 0:
                part = []
                break
        if part:
            pieces.append(_slab(origin, u, v, n, t, part, s.colour, s.name, s.splits + (d,)))
    return pieces if len(pieces) == 2 else None


def prepare(parts):
    """Cuts the solids that pass through another one (crossing dividers) at its middle, then finds the
    relations of every pair: [(i, j, d, sign)] (i beyond / before j along d)."""
    parts = list(parts)
    for _round in range(8):
        changed = False
        for i in range(len(parts)):
            for j in range(len(parts)):
                if i == j or parts[i].frame is None or relation(parts[i], parts[j]) is not None:
                    continue
                a0, a1 = parts[i].span(parts[j].axis)
                b0, b1 = parts[j].span(parts[j].axis)
                if a0 < b0 - EPS and a1 > b1 + EPS:          # i goes through j: cut it at j's middle
                    pieces = _split(parts[i], parts[j].axis, (b0 + b1) / 2.0)
                    if pieces:
                        parts[i:i + 1] = pieces
                        changed = True
                        break
            if changed:
                break
        if not changed:
            break
    rels = []
    for i in range(len(parts)):
        for j in range(i + 1, len(parts)):
            r = relation(parts[i], parts[j])
            if r is not None:
                rels.append((i, j, r[0], r[1]))
    return parts, rels


DIRECTIONS = [(math.cos(k * math.pi / 8), math.sin(k * math.pi / 8)) for k in range(8)]


def outline(points):
    """A solid's outline on the screen, as its extent along 8 directions (a 16-sided polygon round it)."""
    out = []
    for cx, cy in DIRECTIONS:
        values = [x * cx + y * cy for x, y in points]
        out.append((min(values), max(values)))
    return out


def overlap(a, b, gap=1e-3):
    """Do two outlines overlap by more than gap?"""
    return all(a0 < b1 - gap and b0 < a1 - gap for (a0, a1), (b0, b1) in zip(a, b))


def hull(points):
    """The convex hull of 2D points, counter-clockwise (monotone chain)."""
    pts = sorted(set(points))
    if len(pts) < 3:
        return pts

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    lower, upper = [], []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return lower[:-1] + upper[:-1]


def hulls_overlap(h1, h2, gap=1e-3):
    """Do two convex polygons overlap by more than gap (separating axis test)?"""
    for poly in (h1, h2):
        for (x1, y1), (x2, y2) in zip(poly, poly[1:] + poly[:1]):
            nx, ny = y2 - y1, x1 - x2
            length = math.hypot(nx, ny)
            if length < 1e-12:
                continue
            p1 = [(x * nx + y * ny) / length for x, y in h1]
            p2 = [(x * nx + y * ny) / length for x, y in h2]
            if min(p1) >= max(p2) - gap or min(p2) >= max(p1) - gap:
                return False
    return True


def order(parts, rels, depth_of, toward, outlines=None, exact=None):
    """The solids far to near: those behind another one first, ties by depth. toward(d): how much d points
    to the viewer; outlines: each solid's outline on the screen: only solids that overlap there need an
    order; exact(i, j): a closer look at whether they overlap, used when the outlines lead to a loop.
    Returns (order, number of conflicts that had to be broken)."""
    seq, broken = _order(parts, rels, depth_of, toward, outlines, None)
    if broken and exact is not None:
        seq, broken = _order(parts, rels, depth_of, toward, outlines, exact)
    return seq, broken


def _order(parts, rels, depth_of, toward, outlines, exact):
    n = len(parts)
    after = [[] for _ in range(n)]
    count = [0] * n
    for i, j, d, sign in rels:
        if outlines is not None and not overlap(outlines[i], outlines[j]):
            continue
        if exact is not None and not exact(i, j):
            continue
        side = toward(d) * sign                       # > 0: i is nearer
        if side > 1e-9:
            after[j].append(i)
            count[i] += 1
        elif side < -1e-9:
            after[i].append(j)
            count[j] += 1
    depth = [depth_of(s.centre) for s in parts]
    ready = [(-depth[k], k) for k in range(n) if count[k] == 0]
    heapq.heapify(ready)
    done, out, broken = [False] * n, [], 0
    while len(out) < n:
        if not ready:                                 # a loop of "behind": take the farthest one left
            k = max((k for k in range(n) if not done[k]), key=lambda k: depth[k])
            broken += 1
            count[k] = 0
            heapq.heappush(ready, (-depth[k], k))
        _d, k = heapq.heappop(ready)
        if done[k]:
            continue
        done[k] = True
        out.append(k)
        for m in after[k]:
            count[m] -= 1
            if count[m] == 0 and not done[m]:
                heapq.heappush(ready, (-depth[m], m))
    return out, broken


class Box3DView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.assembly = []
        self.yaw, self.pitch, self.zoom = -35.0, 28.0, 1.0
        self.exploded = 0.0
        self.lid_out = 0.0
        self.broken = 0                       # conflicts in the last drawing's order (tests)
        self._drag = None
        self._solids = None
        self.setMinimumSize(420, 320)
        self.setToolTip(_tip())

    def set_assembly(self, assembly):
        self.assembly = list(assembly or [])
        self._solids = None
        self.update()

    def set_exploded(self, mm):
        self.exploded = float(mm)
        self._solids = None
        self.update()

    def set_lid_out(self, mm):
        self.lid_out = float(mm)
        self._solids = None
        self.update()

    def has_sliding_lid(self):
        return any(p.get("slides") for p in self.assembly)

    def solids(self):
        if self._solids is None:
            parts, rels = prepare(solids(self.assembly, self.exploded, self.lid_out))
            pts = [q for s in parts for q in s.points] or [(0.0, 0.0, 0.0)]
            mid = tuple((min(q[i] for q in pts) + max(q[i] for q in pts)) / 2.0 for i in range(3))
            radius = max(math.dist(q, mid) for q in pts) or 1.0
            self._solids = (parts, rels, mid, radius)
        return self._solids

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

    def render(self, painter, width, height, ids=False):
        """Draws the box into painter; ids: each solid in a colour of its own (red = its number + 1), not
        shaded, no edges (for the tests: which solid is seen where)."""
        parts, rels, mid, radius = self.solids()
        if not parts:
            return []
        k = 0.47 * min(width, height) / radius * self.zoom
        cx, cy = width / 2.0, height / 2.0

        def depth_of(p):
            return self.turn((p[0] - mid[0], p[1] - mid[1], p[2] - mid[2]))[1]
        flat = [[(x, z) for x, _y, z in map(self.turn, s.points)] for s in parts]
        outlines = [outline(f) for f in flat]
        hulls = {}

        def exact(i, j):
            for k in (i, j):
                if k not in hulls:
                    hulls[k] = hull([(round(x, 6), round(z, 6)) for x, z in flat[k]])
            return hulls_overlap(hulls[i], hulls[j])
        seq, self.broken = order(parts, rels, depth_of, lambda d: -self.turn(d)[1], outlines, exact)
        pen = QPen(QColor(90, 64, 34, 150), 0.8)
        for index in seq:
            s = parts[index]
            sides, face = [], []
            for polys, normal, is_face in s.faces:
                nv = self.turn(normal)
                if nv[1] > -1e-6:                          # turned away from the viewer
                    continue
                flat = [[self.turn((q[0] - mid[0], q[1] - mid[1], q[2] - mid[2])) for q in poly] for poly in polys]
                d = sum(q[1] for q in flat[0]) / len(flat[0])
                (face if is_face else sides).append((d, flat, nv))
            sides.sort(key=lambda f: -f[0])
            for _d, flat, nv in sides + face:
                path = QPainterPath()
                path.setFillRule(Qt.OddEvenFill)
                for poly in flat:
                    path.addPolygon(QPolygonF([QPointF(cx + q[0] * k, cy - q[2] * k) for q in poly]))
                    path.closeSubpath()
                if ids:
                    painter.setPen(Qt.NoPen)
                    painter.setBrush(QColor(index + 1, 0, 0))
                else:
                    base = WOOD[s.colour]
                    f = 0.6 + 0.4 * max(0.0, nv[0] * LIGHT[0] + nv[1] * LIGHT[1] + nv[2] * LIGHT[2])
                    painter.setPen(pen)
                    painter.setBrush(QColor(int(base.red() * f), int(base.green() * f), int(base.blue() * f)))
                painter.drawPath(path)
        return parts

    def part_at(self, x, y):
        """The name of the solid seen at (x, y) of the view, or "" (for the tests)."""
        img = QImage(self.width(), self.height(), QImage.Format_RGB32)
        img.fill(QColor(0, 0, 0))
        p = QPainter(img)
        parts = self.render(p, self.width(), self.height(), ids=True)
        p.end()
        n = img.pixelColor(int(x), int(y)).red()
        return parts[n - 1].name if 0 < n <= len(parts) else ""

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.fillRect(self.rect(), QColor("#eef0f3"))
        self.render(p, self.width(), self.height())
        p.end()


def _tip():
    from kerfly.i18n import _
    return _("Drag to turn the box, the wheel zooms, a double click turns it back")
