"""
Pattern fills: closed outlines filled with a repeated pattern of engraved
lines (lines, waves, honeycomb, ...), clipped to the outline. Holes stay
empty (even-odd rule, so letters like "O" stay open), and a margin keeps the
pattern away from the outline.

Everything is plain geometry in the units of the polygons (Kerfly passes
millimetres, y down); no optional library is needed. The result is a list of
polylines that the shape code turns into vector engrave data, the same kind
of data as a drawn outline.

Copyright (C) 2026 Kerfly contributors
Licensed under the GNU General Public License v3 or later. See LICENSE.
"""
import math
import random

from .hatch import hatch_lines

# pattern code -> English name (translated in the GUI); the order of the pattern list
PATTERNS = (("lines", "Lines"), ("cross", "Cross-hatch"), ("waves", "Waves"), ("zigzag", "Zigzag"),
            ("circles", "Circles"), ("honeycomb", "Honeycomb"), ("diamonds", "Diamonds"),
            ("bricks", "Bricks"), ("concentric", "Concentric"), ("triangles", "Triangles"),
            ("herringbone", "Herringbone"), ("scales", "Fish scales"), ("squarewave", "Square waves"),
            ("spiral", "Spiral"), ("radial", "Sunburst"), ("dots", "Dots"), ("crosses", "Crosses"),
            ("truchet", "Truchet"), ("hilbert", "Hilbert curve"))
PATTERN_CODES = tuple(code for code, _name in PATTERNS)


# ---- geometry helpers ----------------------------------------------------------
def _closed_rings(polygons):
    rings = []
    for poly in polygons:
        pts = [(float(x), float(y)) for x, y in poly]
        if len(pts) < 3:
            continue
        if pts[0] != pts[-1]:
            pts.append(pts[0])
        rings.append(pts)
    return rings


def _bounds(rings):
    xs = [x for r in rings for x, _y in r]
    ys = [y for r in rings for _x, y in r]
    return min(xs), max(xs), min(ys), max(ys)


class _Region:
    """The filled area of closed rings (even-odd), with fast tests: is a point
    inside, where does a segment cross the outline, how far is a point from it."""

    def __init__(self, rings):
        self.edges = [(a, b) for r in rings for a, b in zip(r, r[1:]) if a != b]
        self.xmin, self.xmax, self.ymin, self.ymax = _bounds(rings)
        span = max(self.xmax - self.xmin, self.ymax - self.ymin, 1e-9)
        n = max(1, min(256, int(math.sqrt(len(self.edges)) * 2)))
        self.cell = span / n
        self.grid = {}
        for i, ((x1, y1), (x2, y2)) in enumerate(self.edges):
            for key in self._cells(min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)):
                self.grid.setdefault(key, []).append(i)
        # horizontal bands for the point-in-region test
        self.band = (self.ymax - self.ymin) / n if self.ymax > self.ymin else 1.0
        self.bands = {}
        for i, ((x1, y1), (x2, y2)) in enumerate(self.edges):
            if y1 == y2:
                continue
            b0 = int((min(y1, y2) - self.ymin) // self.band)
            b1 = int((max(y1, y2) - self.ymin) // self.band)
            for b in range(b0, b1 + 1):
                self.bands.setdefault(b, []).append(i)

    def _cells(self, x0, y0, x1, y1):
        c = self.cell
        i0, i1 = int((x0 - self.xmin) // c), int((x1 - self.xmin) // c)
        j0, j1 = int((y0 - self.ymin) // c), int((y1 - self.ymin) // c)
        for i in range(i0, i1 + 1):
            for j in range(j0, j1 + 1):
                yield i, j

    def _near(self, x0, y0, x1, y1):
        found = set()
        for key in self._cells(x0, y0, x1, y1):
            found.update(self.grid.get(key, ()))
        return found

    def inside(self, x, y):
        if not (self.xmin <= x <= self.xmax and self.ymin <= y <= self.ymax):
            return False
        crossings = 0
        for i in self.bands.get(int((y - self.ymin) // self.band), ()):
            (x1, y1), (x2, y2) = self.edges[i]
            if (y1 > y) != (y2 > y):
                xc = x1 + (y - y1) * (x2 - x1) / (y2 - y1)
                if xc > x:
                    crossings += 1
        return crossings % 2 == 1

    def crossings(self, a, b):
        """Parameters t in (0, 1) where the segment a-b crosses the outline."""
        (ax, ay), (bx, by) = a, b
        dx, dy = bx - ax, by - ay
        out = []
        for i in self._near(min(ax, bx), min(ay, by), max(ax, bx), max(ay, by)):
            (x1, y1), (x2, y2) = self.edges[i]
            ex, ey = x2 - x1, y2 - y1
            den = dx * ey - dy * ex
            if abs(den) < 1e-15:
                continue
            t = ((x1 - ax) * ey - (y1 - ay) * ex) / den
            u = ((x1 - ax) * dy - (y1 - ay) * dx) / den
            if 1e-12 < t < 1 - 1e-12 and -1e-12 <= u <= 1 + 1e-12:
                out.append(t)
        return out

    def distance(self, x, y, limit):
        """Distance from the point to the outline, or `limit` if it is farther."""
        best = limit
        for i in self._near(x - limit, y - limit, x + limit, y + limit):
            (x1, y1), (x2, y2) = self.edges[i]
            ex, ey = x2 - x1, y2 - y1
            ll = ex * ex + ey * ey
            t = 0.0 if ll == 0 else max(0.0, min(1.0, ((x - x1) * ex + (y - y1) * ey) / ll))
            d = math.hypot(x1 + t * ex - x, y1 + t * ey - y)
            if d < best:
                best = d
        return best


def clip_polylines(polylines, polygons, margin=0.0):
    """Parts of the polylines that lie inside the closed polygons (even-odd),
    at least `margin` away from their outline. Returns a list of polylines."""
    rings = _closed_rings(polygons)
    if not rings:
        return []
    region = _Region(rings)
    step = margin / 3.0 if margin > 0 else 0.0

    def keep(p):
        return region.inside(p[0], p[1]) and (margin <= 0 or region.distance(p[0], p[1], margin) >= margin)

    def edge_of_margin(kept, lost):
        for _ in range(24):                            # bisection: the point where the margin begins
            m = ((kept[0] + lost[0]) / 2.0, (kept[1] + lost[1]) / 2.0)
            if keep(m):
                kept = m
            else:
                lost = m
        return kept

    out = []
    for line in polylines:
        run = []                                       # the inside part being collected

        def add(p0, p1):
            nonlocal run
            if run and math.hypot(run[-1][0] - p0[0], run[-1][1] - p0[1]) < 1e-9:
                run.append(p1)
            else:
                end()
                run = [p0, p1]

        def end():
            nonlocal run
            if len(run) >= 2:
                out.append(_without_straight_points(run))
            run = []

        for a, b in zip(line, line[1:]):
            if a == b:
                continue
            ts = [0.0] + sorted(region.crossings(a, b)) + [1.0]
            if step:                                   # extra points, so the margin is not missed
                n = int(math.hypot(b[0] - a[0], b[1] - a[1]) / step)
                ts = sorted(set(ts + [k / (n + 1.0) for k in range(1, n + 1)]))
            for t0, t1 in zip(ts, ts[1:]):
                if t1 - t0 < 1e-12:
                    continue
                p0 = (a[0] + (b[0] - a[0]) * t0, a[1] + (b[1] - a[1]) * t0)
                p1 = (a[0] + (b[0] - a[0]) * t1, a[1] + (b[1] - a[1]) * t1)
                if not step:                           # no margin: the middle of the piece decides
                    if keep(((p0[0] + p1[0]) / 2.0, (p0[1] + p1[1]) / 2.0)):
                        add(p0, p1)
                    else:
                        end()
                    continue
                k0, k1 = keep(p0), keep(p1)
                if k0 and k1:
                    add(p0, p1)
                elif k0:
                    add(p0, edge_of_margin(p0, p1))
                    end()
                elif k1:
                    end()
                    add(edge_of_margin(p1, p0), p1)
                else:
                    end()
        end()
    return out


def _without_straight_points(pts, tol=1e-6):
    """The polyline without points that lie on the straight line between
    their neighbours (the margin search adds many of them)."""
    out = [pts[0]]
    for p, q in zip(pts[1:], pts[2:]):
        a = out[-1]
        cross = (p[0] - a[0]) * (q[1] - a[1]) - (p[1] - a[1]) * (q[0] - a[0])
        if abs(cross) > tol * max(1.0, math.hypot(q[0] - a[0], q[1] - a[1])):
            out.append(p)
    out.append(pts[-1])
    return out


# ---- pattern generators (in a frame rotated by the pattern angle) ---------------------
def _frame(rings, angle_deg):
    """(cx, cy, half size, to_world) for drawing a pattern rotated about the
    shape's centre: pattern coordinates (u, v) -> world (x, y)."""
    xmin, xmax, ymin, ymax = _bounds(rings)
    cx, cy = (xmin + xmax) / 2.0, (ymin + ymax) / 2.0
    half = math.hypot(xmax - xmin, ymax - ymin) / 2.0 + 1e-6
    a = math.radians(angle_deg)
    c, s = math.cos(a), math.sin(a)

    def to_world(u, v):
        # positive angle turns counter-clockwise on the bed (y down in these coordinates)
        return cx + u * c + v * s, cy - u * s + v * c
    return half, to_world


def _rows(half, spacing):
    """v positions of rows covering [-half, half], one through the centre."""
    n = int(half / spacing) + 2
    return [k * spacing for k in range(-n, n + 1)]


def _wave_rows(half, spacing, wave):
    """Rows across the frame shaped by wave(u, row) -> v offset."""
    step = spacing / 12.0
    n_u = int(2 * half / step) + 2
    lines = []
    for r, v0 in enumerate(_rows(half, spacing)):
        pts = []
        for i in range(n_u + 1):
            u = -half + i * step
            pts.append((u, v0 + wave(u, r)))
        if r % 2:
            pts.reverse()                              # zigzag order: less travel between rows
        lines.append(pts)
    return lines


def _hex_edges(half, size):
    """Edges of a honeycomb of hexagons (flat sides up), `size` across the flats."""
    a = size / math.sqrt(3.0)                          # side length
    w, h = 1.5 * a, size                               # column step, row step
    edges = set()
    nx, ny = int(half / w) + 2, int(half / h) + 2
    for i in range(-nx, nx + 1):
        for j in range(-ny, ny + 1):
            cx, cy = i * w, j * h + (h / 2.0 if i % 2 else 0.0)
            pts = [(cx + a * math.cos(math.radians(60 * k)), cy + a * math.sin(math.radians(60 * k)))
                   for k in range(6)]
            for k in range(6):
                p, q = pts[k], pts[(k + 1) % 6]
                key = tuple(sorted(((round(p[0], 6), round(p[1], 6)), (round(q[0], 6), round(q[1], 6)))))
                edges.add(key)
    return [list(e) for e in edges]


def _arc(cx, cy, r, a0, a1, step):
    n = max(4, int(abs(a1 - a0) * r / step) + 1)
    return [(cx + r * math.cos(a0 + (a1 - a0) * i / n), cy + r * math.sin(a0 + (a1 - a0) * i / n))
            for i in range(n + 1)]


def _hilbert(order):
    """Points of the Hilbert curve of the given order on a (2**order) grid."""
    n = 2 ** order
    pts = []
    for d in range(n * n):
        x = y = 0
        t = d
        s = 1
        while s < n:
            rx = 1 & (t // 2)
            ry = 1 & (t ^ rx)
            if ry == 0:
                if rx == 1:
                    x, y = s - 1 - x, s - 1 - y
                x, y = y, x
            x += s * rx
            y += s * ry
            t //= 4
            s *= 2
        pts.append((x, y))
    return pts


def _more_patterns(pattern, half, s):
    """The patterns of step 2 (ROADMAP: pattern fills), in the pattern frame; None: unknown."""
    if pattern == "triangles":
        local = []
        for turn in (0.0, 60.0, -60.0):
            t = math.radians(turn)
            c, sn = math.cos(t), math.sin(t)
            for v in _rows(half, s * math.sqrt(3) / 2):
                local.append([(u * c - w * sn, u * sn + w * c) for u, w in ((-half, v), (half, v))])
        return local
    if pattern == "herringbone":
        local = []
        n = int(half / s) + 2
        for j in range(-n, n + 1):
            u0 = j * s
            for k in range(-2 * n, 2 * n + 1):
                v = k * s / 2.0
                local.append([(u0, v), (u0 + s, v + s)] if j % 2 == 0 else [(u0, v + s), (u0 + s, v)])
        return local
    if pattern == "scales":
        local = []
        n = int(half / s) + 2
        for k in range(-2 * n, 2 * n + 1):
            v = k * s / 2.0
            off = s / 2.0 if k % 2 else 0.0
            for j in range(-n, n + 1):
                local.append(_arc(j * s + off, v, s / 2.0, 0.0, math.pi, s / 10.0))
        return local
    if pattern == "squarewave":
        local = []
        for r, v0 in enumerate(_rows(half, s)):
            pts = []
            n = int(half / (s / 2.0)) + 2
            for j in range(-n, n):
                u = j * s / 2.0
                hi = v0 + (0.25 * s if j % 2 else -0.25 * s)
                pts += [(u, hi), (u + s / 2.0, hi)]
            local.append(pts if r % 2 == 0 else list(reversed(pts)))
        return local
    if pattern == "spiral":
        pts, theta = [], 0.0
        while True:
            r = s * theta / (2 * math.pi)
            if r > half * 1.05:
                break
            pts.append((r * math.cos(theta), r * math.sin(theta)))
            theta += max(0.02, min(0.3, (s / 6.0) / max(r, s / 6.0)))
        return [pts]
    if pattern == "radial":
        n = max(8, int(math.pi * half / s))
        r0 = s * 0.5
        return [[(r0 * math.cos(2 * math.pi * k / n), r0 * math.sin(2 * math.pi * k / n)),
                 (half * 1.05 * math.cos(2 * math.pi * k / n), half * 1.05 * math.sin(2 * math.pi * k / n))]
                for k in range(n)]
    if pattern in ("dots", "crosses"):
        local = []
        n = int(half / s) + 1
        for i in range(-n, n + 1):
            for j in range(-n, n + 1):
                u, v = i * s, j * s
                if pattern == "dots":
                    r = s * 0.15
                    local.append([(u + r * math.cos(2 * math.pi * a / 12), v + r * math.sin(2 * math.pi * a / 12))
                                  for a in range(13)])
                else:
                    a = s * 0.25
                    local += [[(u - a, v), (u + a, v)], [(u, v - a), (u, v + a)]]
        return local
    if pattern == "truchet":
        local = []
        n = int(half / s) + 1
        for i in range(-n, n + 1):
            for j in range(-n, n + 1):
                u, v = i * s, j * s
                flip = random.Random(i * 1000003 + j).random() < 0.5   # the same tiles every time
                step = s / 10.0
                if flip:
                    local.append(_arc(u, v, s / 2.0, 0.0, math.pi / 2, step))
                    local.append(_arc(u + s, v + s, s / 2.0, math.pi, 1.5 * math.pi, step))
                else:
                    local.append(_arc(u + s, v, s / 2.0, math.pi / 2, math.pi, step))
                    local.append(_arc(u, v + s, s / 2.0, 1.5 * math.pi, 2 * math.pi, step))
        return local
    if pattern == "hilbert":
        order = max(1, min(7, int(math.ceil(math.log(max(2.0, 2 * half / s), 2)))))
        cells = 2 ** order
        cell = 2 * half / cells
        return [[(-half + (x + 0.5) * cell, -half + (y + 0.5) * cell) for x, y in _hilbert(order)]]
    return None


def pattern_lines(pattern, polygons, spacing, angle_deg=0.0, margin=0.0):
    """Polylines of `pattern` filling the closed polygons, every `spacing`
    units (the size of one repeat), turned by angle_deg, kept `margin` away
    from the outline. Raises ValueError for an unknown pattern."""
    if spacing <= 0:
        raise ValueError("pattern spacing must be positive")
    rings = _closed_rings(polygons)
    if not rings:
        return []
    if pattern in ("lines", "cross") and margin <= 0:
        # straight lines: the hatch code is exact and fast
        segs = hatch_lines(rings, spacing, angle_deg, cross=pattern == "cross")
        return [[a, b] for a, b in segs]
    if pattern == "concentric":
        # rings following the outline inwards (the angle does not matter)
        from . import offset
        if not offset.available():
            return []
        return offset.concentric_rings(rings, spacing, margin, tolerance=min(0.01, spacing / 20.0))
    half, to_world = _frame(rings, angle_deg)
    s = spacing
    if pattern == "lines":
        local = [[(-half, v), (half, v)] if k % 2 == 0 else [(half, v), (-half, v)]
                 for k, v in enumerate(_rows(half, s))]
    elif pattern == "cross":
        rows = _rows(half, s)
        local = [[(-half, v), (half, v)] for v in rows] + [[(u, -half), (u, half)] for u in rows]
    elif pattern == "waves":
        local = _wave_rows(half, s, lambda u, r: 0.35 * s * math.sin(math.pi * u / s))
    elif pattern == "zigzag":
        def tri(u, r):
            p = (u / s) % 2.0                          # period 2 spacings
            return 0.35 * s * (2 * p - 1 if p < 1 else 3 - 2 * p)
        local = _wave_rows(half, s, tri)
    elif pattern == "circles":
        local = []
        k = 1
        while k * s <= half * 1.05:
            r = k * s
            n = max(24, int(2 * math.pi * r / (s / 6.0)))
            local.append([(r * math.cos(2 * math.pi * i / n), r * math.sin(2 * math.pi * i / n))
                          for i in range(n + 1)])
            k += 1
    elif pattern == "honeycomb":
        local = _hex_edges(half, s)
    elif pattern == "diamonds":
        local = []
        for turn in (60.0, -60.0):
            t = math.radians(turn)
            c, sn = math.cos(t), math.sin(t)
            for v in _rows(half, s):
                ends = [(-half, v), (half, v)]
                local.append([(u * c - w * sn, u * sn + w * c) for u, w in ends])
    elif pattern == "bricks":
        rows = _rows(half, s)
        local = [[(-half, v), (half, v)] for v in rows]
        for k, v in enumerate(rows[:-1]):
            off = s if k % 2 else 0.0
            n = int(half / (2 * s)) + 2
            for j in range(-n, n + 1):
                u = j * 2 * s + off
                local.append([(u, v), (u, v + s)])
    else:
        local = _more_patterns(pattern, half, s)
        if local is None:
            raise ValueError("unknown fill pattern: %r" % (pattern,))
    world = [[to_world(u, v) for u, v in line] for line in local]
    return chain_polylines(clip_polylines(world, rings, margin))


def chain_polylines(polylines, tol=1e-6):
    """Join polylines that meet end to end into longer ones (a honeycomb is
    made of short edges: joined, the laser is switched on and off less often)."""
    def key(p):
        return (round(p[0] / tol), round(p[1] / tol)) if tol else p
    ends = {}
    for i, line in enumerate(polylines):
        ends.setdefault(key(line[0]), []).append(i)
        ends.setdefault(key(line[-1]), []).append(i)
    used = [False] * len(polylines)

    def take(point):
        for j in ends.get(key(point), ()):
            if not used[j]:
                used[j] = True
                line = polylines[j]
                return line if key(line[0]) == key(point) else line[::-1]
        return None
    out = []
    for i, line in enumerate(polylines):
        if used[i]:
            continue
        used[i] = True
        chain = list(line)
        while True:                                    # grow at the end, then at the start
            nxt = take(chain[-1])
            if nxt is None:
                break
            chain.extend(nxt[1:])
        while True:
            prv = take(chain[0])
            if prv is None:
                break
            chain[:0] = prv[::-1][:-1]
        out.append(chain)
    return out


# ---- living hinges: rows of cuts that let a sheet bend -------------------------------
# hinge code -> English name (translated in the GUI)
HINGES = (("straight", "Straight cuts"), ("wave", "Wavy cuts"), ("zigzag", "Zigzag cuts"))
HINGE_CODES = tuple(code for code, _name in HINGES)


def hinge_lines(pattern, polygons, cut, gap, spacing, angle_deg=90.0, margin=0.0,
                band_width=0.0, band_offset=0.0):
    """Cut lines of a living hinge inside the closed polygons: rows `spacing` apart, the cuts in each row
    about `cut` long with `gap` of uncut material between them (the bridges that hold the sheet together),
    the rows taking turns: one row has only long cuts, with a bridge at both ends; the next is shifted by
    half, its bridges in the middle of those cuts: a short cut runs from the outline at each end, long ones
    between (the user's choice 2026-11-20). Each row is laid out on its own length inside the shape (the
    cuts a little longer or shorter than `cut`, no slivers at the outline). The short cuts reaching the
    outline matter: a solid border along it would keep the sheet from bending. The cuts run at angle_deg (90: up and down, so the sheet bends
    round an upright axis); `margin` of solid material is left only at the ends of the hinge, across the rows
    (the first and last rows at least half a row gap in from the outline). The rows are in a snake's order
    (every second one the other way), for short moves.
    band_width > 0 keeps the cuts in a band that wide (across the cuts), its middle `band_offset` from the
    middle of the shape (plus: right for upright cuts, down for level ones); 0: the whole shape.
    Raises ValueError for an unknown pattern or non-positive sizes."""
    if cut <= 0 or gap <= 0 or spacing <= 0:
        raise ValueError("hinge sizes must be positive")
    if pattern not in ("straight", "wave", "zigzag"):
        raise ValueError("unknown hinge pattern: %r" % (pattern,))
    rings = _closed_rings(polygons)
    if not rings:
        return []
    half, to_world = _frame(rings, angle_deg)
    amp = 0.3 * spacing                                  # waves and zigzags stay apart from the next row
    # the band across the rows: +v goes (sin a, cos a) on the page (y down); "plus" means right
    # for upright cuts and down for level ones
    a = math.radians(angle_deg)
    sx, sy = math.sin(a), math.cos(a)
    sign = 1.0 if ((abs(sx) > abs(sy) and sx > 0) or (abs(sy) >= abs(sx) and sy > 0)) else -1.0
    band_mid = sign * band_offset
    cx, cy = to_world(0.0, 0.0)
    vs = [(x - cx) * sx + (y - cy) * sy for ring in rings for x, y in ring]     # across the rows
    end_in = max(max(0.0, margin), spacing / 2.0)
    region = _Region(rings)
    shortest = min(0.5, cut)                             # no cut shorter than this
    out = []
    kept = 0
    for v in _rows(half, spacing):
        if v < min(vs) + end_in - 1e-9 or v > max(vs) - end_in + 1e-9:
            continue
        if band_width > 0 and abs(v - band_mid) > band_width / 2.0:
            continue
        # where the row lies inside the shape: the outline's crossings along it
        p0, p1 = to_world(-half - 1.0, v), to_world(half + 1.0, v)
        length = 2.0 * half + 2.0
        ts = sorted(region.crossings(p0, p1))
        spans = []
        for t0, t1 in zip(ts, ts[1:]):
            mid = to_world(-half - 1.0 + length * (t0 + t1) / 2.0, v)
            if region.inside(mid[0], mid[1]):
                spans.append((-half - 1.0 + length * t0, -half - 1.0 + length * t1))
        cuts = []
        for ua, ub in spans:
            chord = ub - ua
            # row B: n long cuts, none touching the outline: a bridge at both ends and between them
            n = max(1, int(round((chord - gap) / (cut + gap))))
            c = (chord - (n + 1) * gap) / n
            if c < shortest:
                continue
            bridges = [ua + gap / 2.0 + i * (c + gap) for i in range(n + 1)]          # their middles
            if kept % 2 == 0:
                # row A, shifted by half: its bridges in the middle of row B's cuts, so a short cut runs from
                # the outline at each end and long ones between (no two bridges of neighbouring rows line up:
                # a solid band across the rows would not bend)
                bridges = [(b0 + b1) / 2.0 for b0, b1 in zip(bridges, bridges[1:])]
                edges = [ua - gap / 2.0] + bridges + [ub + gap / 2.0]
            else:
                edges = bridges
            for b0, b1 in zip(edges, edges[1:]):
                u0, u1 = max(ua, b0 + gap / 2.0), min(ub, b1 - gap / 2.0)
                if u1 - u0 >= shortest:
                    cuts.append((u0, u1))
        lines = []
        for u0, u1 in cuts:
            if pattern == "straight":
                pts = [(u0, v), (u1, v)]
            elif pattern == "wave":
                steps = max(8, int((u1 - u0) / max(spacing / 2.0, 0.5)))
                pts = [(u0 + (u1 - u0) * i / steps, v + amp * math.sin(2 * math.pi * i / steps))
                       for i in range(steps + 1)]
            else:
                pts = [(u0, v), (u0 + (u1 - u0) * 0.25, v + amp), (u0 + (u1 - u0) * 0.75, v - amp), (u1, v)]
            lines.append([to_world(u, w) for u, w in pts])
        if kept % 2:                                     # the snake: every second row the other way
            lines = [line[::-1] for line in reversed(lines)]
        out.extend(lines)
        if cuts:
            kept += 1
    return out
