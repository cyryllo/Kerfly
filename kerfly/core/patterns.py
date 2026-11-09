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

from .hatch import hatch_lines

# pattern code -> English name (translated in the GUI); the order of the pattern list
PATTERNS = (("lines", "Lines"), ("cross", "Cross-hatch"), ("waves", "Waves"), ("zigzag", "Zigzag"),
            ("circles", "Circles"), ("honeycomb", "Honeycomb"), ("diamonds", "Diamonds"),
            ("bricks", "Bricks"), ("concentric", "Concentric"))
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


def hinge_lines(pattern, polygons, cut, gap, spacing, angle_deg=90.0, margin=3.0,
                band_width=0.0, band_offset=0.0):
    """Cut lines of a living hinge inside the closed polygons: rows of cuts
    `cut` long with `gap` of uncut material between them (the bridges that hold
    the sheet together), rows `spacing` apart, every second row shifted by half
    a cut, so the sheet bends across the cuts. The cuts run at angle_deg
    (90: up and down, so the sheet bends round an upright axis) and stay
    `margin` away from the outline, which leaves a solid border.
    band_width > 0 keeps the cuts in a band that wide (across the cuts), its
    middle `band_offset` from the middle of the shape (plus: right for upright
    cuts, down for level ones); 0: the whole shape.
    Raises ValueError for an unknown pattern or non-positive sizes."""
    if cut <= 0 or gap <= 0 or spacing <= 0:
        raise ValueError("hinge sizes must be positive")
    rings = _closed_rings(polygons)
    if not rings:
        return []
    half, to_world = _frame(rings, angle_deg)
    period = cut + gap
    amp = 0.3 * spacing                                  # waves and zigzags stay apart from the next row
    # the band across the rows: +v goes (sin a, cos a) on the page (y down); "plus" means right
    # for upright cuts and down for level ones
    a = math.radians(angle_deg)
    sx, sy = math.sin(a), math.cos(a)
    sign = 1.0 if ((abs(sx) > abs(sy) and sx > 0) or (abs(sy) >= abs(sx) and sy > 0)) else -1.0
    band_mid = sign * band_offset
    local = []
    for k, v in enumerate(_rows(half, spacing)):
        if band_width > 0 and abs(v - band_mid) > band_width / 2.0:
            continue
        start = -half - period - ((k % 2) * period / 2.0)
        n = int((2 * half + 2 * period) / period) + 2
        for j in range(n):
            u0 = start + j * period
            if pattern == "straight":
                local.append([(u0, v), (u0 + cut, v)])
            elif pattern == "wave":
                steps = max(8, int(cut / max(spacing / 2.0, 0.5)))
                local.append([(u0 + cut * i / steps, v + amp * math.sin(2 * math.pi * i / steps))
                              for i in range(steps + 1)])
            elif pattern == "zigzag":
                local.append([(u0, v), (u0 + cut * 0.25, v + amp), (u0 + cut * 0.75, v - amp), (u0 + cut, v)])
            else:
                raise ValueError("unknown hinge pattern: %r" % (pattern,))
    world = [[to_world(u, w) for u, w in line] for line in local]
    return clip_polylines(world, rings, max(0.0, margin))
