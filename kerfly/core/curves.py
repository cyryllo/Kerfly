"""
Curves: paths made of straight lines and cubic Bezier curves, with nodes that
can be edited (moved, smoothed, turned into lines or curves, ...).

A path is a list of subpaths:
    {"closed": bool, "nodes": [[x, y, in_x, in_y, out_x, out_y], ...]}
in millimetres, y down (like the bed view). in_* / out_* are the node's two
control handles (None when the neighbouring segment is a straight line). The
segment from node i to node i + 1 is a cubic curve when node i has an out
handle or node i + 1 an in handle, otherwise a line.

The laser gets the path as short straight pieces (flatten()), so the laser
core is untouched.

Reading curves from files:
    svg_segments()  SVG paths, rectangles, circles, ellipses, lines and
                    polylines (svgelements), red -> cut, blue -> engrave as in
                    K40 Whisperer
    dxf_segments()  DXF entities; arcs, circles and polyline bulges stay arcs
                    (as Bezier curves), everything else as read by K40
                    Whisperer's reader, so positions match exactly

Copyright (C) 2026 Kerfly contributors
Licensed under the GNU General Public License v3 or later. See LICENSE.
"""
import math

FLATNESS_MM = 0.02           # largest distance of the laser's straight pieces from the true curve
JOIN_TOLERANCE = 1e-4        # end points closer than this (in the segments' units) are joined
KAPPA = 4.0 * (math.sqrt(2.0) - 1.0) / 3.0      # quarter-circle Bezier handle length


# ---- nodes and segments -------------------------------------------------------
def node(x, y, hin=None, hout=None):
    return [x, y, hin[0] if hin else None, hin[1] if hin else None,
            hout[0] if hout else None, hout[1] if hout else None]


def _hin(n):
    return None if n[2] is None else (n[2], n[3])


def _hout(n):
    return None if n[4] is None else (n[4], n[5])


def segments_of(sub):
    """Segments of a subpath: (p0, c1, c2, p3) with c1 = c2 = None for a line."""
    nodes = sub["nodes"]
    n = len(nodes)
    count = n if sub.get("closed") and n > 1 else n - 1
    out = []
    for i in range(max(0, count)):
        a, b = nodes[i], nodes[(i + 1) % n]
        c1, c2 = _hout(a), _hin(b)
        if c1 is None and c2 is None:
            out.append(((a[0], a[1]), None, None, (b[0], b[1])))
        else:
            out.append(((a[0], a[1]), c1 or (a[0], a[1]), c2 or (b[0], b[1]), (b[0], b[1])))
    return out


def is_curve(seg):
    return seg[1] is not None


def bezier_point(seg, t):
    p0, c1, c2, p3 = seg
    if c1 is None:
        return (p0[0] + (p3[0] - p0[0]) * t, p0[1] + (p3[1] - p0[1]) * t)
    u = 1.0 - t
    a, b, c, d = u * u * u, 3 * u * u * t, 3 * u * t * t, t * t * t
    return (a * p0[0] + b * c1[0] + c * c2[0] + d * p3[0], a * p0[1] + b * c1[1] + c * c2[1] + d * p3[1])


def _flatten_cubic(seg, tol, out, depth=0):
    p0, c1, c2, p3 = seg
    # flat enough when both control points are within tol of the chord
    dx, dy = p3[0] - p0[0], p3[1] - p0[1]
    length = math.hypot(dx, dy)
    if length > 0:
        d1 = abs((c1[0] - p0[0]) * dy - (c1[1] - p0[1]) * dx) / length
        d2 = abs((c2[0] - p0[0]) * dy - (c2[1] - p0[1]) * dx) / length
    else:
        d1 = math.hypot(c1[0] - p0[0], c1[1] - p0[1])
        d2 = math.hypot(c2[0] - p0[0], c2[1] - p0[1])
    if max(d1, d2) <= tol or depth > 16:
        out.append(p3)
        return
    left, right = split_cubic(seg, 0.5)
    _flatten_cubic(left, tol, out, depth + 1)
    _flatten_cubic(right, tol, out, depth + 1)


def split_cubic(seg, t):
    """De Casteljau: the two halves of a cubic segment at t."""
    p0, c1, c2, p3 = seg

    def lerp(a, b):
        return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)
    a, b, c = lerp(p0, c1), lerp(c1, c2), lerp(c2, p3)
    d, e = lerp(a, b), lerp(b, c)
    m = lerp(d, e)
    return (p0, a, d, m), (m, e, c, p3)


def flatten(subpaths, tol=FLATNESS_MM):
    """Polylines for the laser: closed subpaths repeat their first point."""
    out = []
    for sub in subpaths:
        nodes = sub["nodes"]
        if not nodes:
            continue
        pts = [(nodes[0][0], nodes[0][1])]
        for seg in segments_of(sub):
            if is_curve(seg):
                _flatten_cubic(seg, tol, pts)
            else:
                pts.append(seg[3])
        if len(pts) >= 2:
            out.append(pts)
    return out


def bounds(subpaths):
    pts = [p for poly in flatten(subpaths) for p in poly]
    if not pts:
        return 0.0, 0.0, 0.0, 0.0
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return min(xs), max(xs), min(ys), max(ys)


def translate(subpaths, dx, dy):
    out = []
    for sub in subpaths:
        nodes = []
        for n in sub["nodes"]:
            nodes.append([n[0] + dx, n[1] + dy,
                          None if n[2] is None else n[2] + dx, None if n[3] is None else n[3] + dy,
                          None if n[4] is None else n[4] + dx, None if n[5] is None else n[5] + dy])
        out.append({"closed": bool(sub.get("closed")), "nodes": nodes})
    return out


def normalized(subpaths):
    """The path moved so its outline starts at (0, 0); returns (path, (dx, dy))."""
    x0, _x1, y0, _y1 = bounds(subpaths)
    return translate(subpaths, -x0, -y0), (-x0, -y0)


def copy_path(subpaths):
    return translate(subpaths, 0.0, 0.0)


def from_polylines(polys, closed_flags):
    return [{"closed": bool(c), "nodes": [node(x, y) for x, y in p]} for p, c in zip(polys, closed_flags)]


def all_closed(subpaths):
    return bool(subpaths) and all(s.get("closed") for s in subpaths)


# ---- editing (sub = subpath index, i = node index) ------------------------------
def move_node(subpaths, sub, i, x, y):
    """Move a node; its handles move with it."""
    n = subpaths[sub]["nodes"][i]
    dx, dy = x - n[0], y - n[1]
    n[0], n[1] = x, y
    if n[2] is not None:
        n[2] += dx
        n[3] += dy
    if n[4] is not None:
        n[4] += dx
        n[5] += dy


def move_handle(subpaths, sub, i, which, x, y, keep_smooth=True):
    """Move the "in" or "out" handle of a node. A smooth node turns its other
    handle too, so the curve stays smooth through the node."""
    n = subpaths[sub]["nodes"][i]
    k, o = (2, 4) if which == "in" else (4, 2)
    other = (n[o], n[o + 1]) if n[o] is not None else None
    smooth = keep_smooth and other is not None and _is_smooth(n)
    n[k], n[k + 1] = x, y
    if smooth:
        length = math.hypot(other[0] - n[0], other[1] - n[1])
        d = math.hypot(x - n[0], y - n[1])
        if d > 0:
            n[o] = n[0] - (x - n[0]) / d * length
            n[o + 1] = n[1] - (y - n[1]) / d * length


def _is_smooth(n, tol_deg=2.0):
    if n[2] is None or n[4] is None:
        return False
    a1 = math.atan2(n[3] - n[1], n[2] - n[0])
    a2 = math.atan2(n[5] - n[1], n[4] - n[0])
    diff = abs((a1 - a2 + math.pi) % (2 * math.pi) - math.pi)
    return abs(diff - math.pi) < math.radians(tol_deg)


def _neighbours(sub, i):
    nodes = sub["nodes"]
    n = len(nodes)
    closed = sub.get("closed")
    prev = (i - 1) % n if (i > 0 or closed) else None
    nxt = (i + 1) % n if (i < n - 1 or closed) else None
    return prev, nxt


def insert_node(subpaths, sub, seg_index, t=0.5):
    """Split segment seg_index (from node seg_index) at t; returns the new node index."""
    s = subpaths[sub]
    nodes = s["nodes"]
    seg = segments_of(s)[seg_index]
    a, b = nodes[seg_index], nodes[(seg_index + 1) % len(nodes)]
    if is_curve(seg):
        left, right = split_cubic(seg, t)
        a[4], a[5] = left[1]
        b[2], b[3] = right[2]
        new = node(left[3][0], left[3][1], left[2], right[1])
    else:
        x, y = bezier_point(seg, t)
        new = node(x, y)
    nodes.insert(seg_index + 1, new)
    return seg_index + 1


def delete_node(subpaths, sub, i):
    """Remove a node (keeps at least a line, or a triangle when closed)."""
    s = subpaths[sub]
    if len(s["nodes"]) <= (3 if s.get("closed") else 2):
        return False
    del s["nodes"][i]
    return True


def make_line(subpaths, sub, i):
    """The segments next to node i become straight lines."""
    s = subpaths[sub]
    nodes = s["nodes"]
    prev, nxt = _neighbours(s, i)
    n = nodes[i]
    n[2] = n[3] = n[4] = n[5] = None
    if prev is not None:
        nodes[prev][4] = nodes[prev][5] = None
    if nxt is not None:
        nodes[nxt][2] = nodes[nxt][3] = None


def make_curve(subpaths, sub, i):
    """The segments next to node i become curves (handles at a third of the way)."""
    s = subpaths[sub]
    nodes = s["nodes"]
    prev, nxt = _neighbours(s, i)
    n = nodes[i]
    if prev is not None:
        p = nodes[prev]
        n[2], n[3] = n[0] + (p[0] - n[0]) / 3.0, n[1] + (p[1] - n[1]) / 3.0
        if p[4] is None:
            p[4], p[5] = p[0] + (n[0] - p[0]) / 3.0, p[1] + (n[1] - p[1]) / 3.0
    if nxt is not None:
        q = nodes[nxt]
        n[4], n[5] = n[0] + (q[0] - n[0]) / 3.0, n[1] + (q[1] - n[1]) / 3.0
        if q[2] is None:
            q[2], q[3] = q[0] + (n[0] - q[0]) / 3.0, q[1] + (n[1] - q[1]) / 3.0


def smooth_node(subpaths, sub, i, symmetric=False):
    """Make the curve pass smoothly through node i: both handles on one line,
    pointing from the previous to the next node (equal lengths if symmetric)."""
    s = subpaths[sub]
    nodes = s["nodes"]
    prev, nxt = _neighbours(s, i)
    n = nodes[i]
    if prev is None and nxt is None:
        return
    p = nodes[prev] if prev is not None else n
    q = nodes[nxt] if nxt is not None else n
    dx, dy = q[0] - p[0], q[1] - p[1]
    d = math.hypot(dx, dy)
    if d == 0:
        return
    ux, uy = dx / d, dy / d
    lin = math.hypot(n[0] - p[0], n[1] - p[1]) / 3.0
    lout = math.hypot(q[0] - n[0], q[1] - n[1]) / 3.0
    if symmetric:
        lin = lout = (lin + lout) / 2.0
    if prev is not None:
        n[2], n[3] = n[0] - ux * lin, n[1] - uy * lin
        if p[4] is None:
            p[4], p[5] = p[0] + (n[0] - p[0]) / 3.0, p[1] + (n[1] - p[1]) / 3.0
    if nxt is not None:
        n[4], n[5] = n[0] + ux * lout, n[1] + uy * lout
        if q[2] is None:
            q[2], q[3] = q[0] + (n[0] - q[0]) / 3.0, q[1] + (n[1] - q[1]) / 3.0


def toggle_closed(subpaths, sub):
    s = subpaths[sub]
    if not s.get("closed") and len(s["nodes"]) < 3:
        return False
    s["closed"] = not s.get("closed")
    return True


def break_at(subpaths, sub, i):
    """Open the path at node i: a closed path becomes open starting there; an
    open path is split into two."""
    s = subpaths[sub]
    nodes = s["nodes"]
    if s.get("closed"):
        first = [list(n) for n in nodes[i:] + nodes[:i]]
        first.append(list(first[0]))
        first[0][2] = first[0][3] = None           # no handle before the start
        first[-1][4] = first[-1][5] = None         # nor after the end
        subpaths[sub] = {"closed": False, "nodes": first}
        return True
    if i <= 0 or i >= len(nodes) - 1:
        return False
    a = [list(n) for n in nodes[:i + 1]]
    b = [list(n) for n in nodes[i:]]
    a[-1][4] = a[-1][5] = None
    b[0][2] = b[0][3] = None
    subpaths[sub:sub + 1] = [{"closed": False, "nodes": a}, {"closed": False, "nodes": b}]
    return True


# ---- freehand ------------------------------------------------------------------------
def simplify(points, tol):
    """Ramer-Douglas-Peucker: drop points closer than tol to the line between
    their neighbours (keeps the first and last point)."""
    if len(points) < 3:
        return list(points)
    keep = [False] * len(points)
    keep[0] = keep[-1] = True
    stack = [(0, len(points) - 1)]
    while stack:
        a, b = stack.pop()
        ax, ay = points[a]
        bx, by = points[b]
        dx, dy = bx - ax, by - ay
        length = math.hypot(dx, dy)
        best, index = -1.0, None
        for k in range(a + 1, b):
            px, py = points[k]
            d = (abs((px - ax) * dy - (py - ay) * dx) / length) if length else math.hypot(px - ax, py - ay)
            if d > best:
                best, index = d, k
        if index is not None and best > tol:
            keep[index] = True
            stack += [(a, index), (index, b)]
    return [p for p, k in zip(points, keep) if k]


def smooth_path(points, closed=False, tension=1.0 / 6.0):
    """A smooth curve through points (Catmull-Rom, as Bezier handles)."""
    n = len(points)
    if n < 3:
        return from_polylines([points], [False])
    nodes = []
    for i, (x, y) in enumerate(points):
        if closed:
            prev, nxt = points[(i - 1) % n], points[(i + 1) % n]
        else:
            prev = points[i - 1] if i > 0 else points[i]
            nxt = points[i + 1] if i < n - 1 else points[i]
        tx, ty = (nxt[0] - prev[0]) * tension, (nxt[1] - prev[1]) * tension
        hin = (x - tx, y - ty) if (closed or i > 0) else None
        hout = (x + tx, y + ty) if (closed or i < n - 1) else None
        nodes.append(node(x, y, hin, hout))
    return [{"closed": closed, "nodes": nodes}]


# ---- arcs ----------------------------------------------------------------------------
def arc_segments(cx, cy, r, start_deg, end_deg, rx=None, ry=None, rotation_deg=0.0):
    """Bezier segments of a circular (or elliptical) arc, counter-clockwise from
    start to end in a y-up system."""
    rx = r if rx is None else rx
    ry = r if ry is None else ry
    sweep = end_deg - start_deg
    if sweep <= 0:
        sweep += 360.0
    parts = max(1, int(math.ceil(sweep / 45.0 - 1e-9)))       # 45 degrees: error ~ r * 4e-6
    step = math.radians(sweep / parts)
    k = 4.0 / 3.0 * math.tan(step / 4.0)
    rot = math.radians(rotation_deg)
    cr, sr = math.cos(rot), math.sin(rot)

    def pt(x, y):
        return (cx + x * cr - y * sr, cy + x * sr + y * cr)
    out = []
    a = math.radians(start_deg)
    for _ in range(parts):
        b = a + step
        p0 = (rx * math.cos(a), ry * math.sin(a))
        p3 = (rx * math.cos(b), ry * math.sin(b))
        c1 = (p0[0] - k * rx * math.sin(a), p0[1] + k * ry * math.cos(a))
        c2 = (p3[0] + k * rx * math.sin(b), p3[1] - k * ry * math.cos(b))
        out.append((pt(*p0), pt(*c1), pt(*c2), pt(*p3)))
        a = b
    return out


def bulge_segments(x0, y0, x1, y1, bulge):
    """A DXF polyline bulge (tan of a quarter of the arc angle) as Bezier segments."""
    if bulge == 0:
        return [((x0, y0), None, None, (x1, y1))]
    theta = 4.0 * math.atan(abs(bulge))
    chord = math.hypot(x1 - x0, y1 - y0)
    if chord == 0:
        return []
    r = chord / (2.0 * math.sin(theta / 2.0))
    mx, my = (x0 + x1) / 2.0, (y0 + y1) / 2.0
    h = math.sqrt(max(r * r - (chord / 2.0) ** 2, 0.0))
    ux, uy = (x1 - x0) / chord, (y1 - y0) / chord
    # centre lies to the left of the chord for a counter-clockwise arc (bulge > 0)
    sign = 1.0 if (bulge > 0) == (theta < math.pi) else -1.0
    cx, cy = mx - uy * h * sign, my + ux * h * sign
    a0 = math.degrees(math.atan2(y0 - cy, x0 - cx))
    a1 = math.degrees(math.atan2(y1 - cy, x1 - cx))
    if bulge > 0:
        return arc_segments(cx, cy, r, a0, a1)
    segs = arc_segments(cx, cy, r, a1, a0)              # clockwise: draw it backwards
    return [(s[3], s[2], s[1], s[0]) for s in reversed(segs)]


# ---- joining segments into subpaths ------------------------------------------------
def join_segments(segments, tol=JOIN_TOLERANCE):
    """Chain loose segments (p0, c1, c2, p3) into subpaths where end points meet."""
    def close(a, b):
        return abs(a[0] - b[0]) <= tol and abs(a[1] - b[1]) <= tol

    def reverse(s):
        return (s[3], s[2], s[1], s[0])
    pending = [s for s in segments if not close(s[0], s[3]) or s[1] is not None]
    chains = []
    while pending:
        chain = [pending.pop(0)]
        grown = True
        while grown:
            grown = False
            for k, s in enumerate(pending):
                if close(chain[-1][3], s[0]):
                    chain.append(s)
                elif close(chain[-1][3], s[3]):
                    chain.append(reverse(s))
                elif close(chain[0][0], s[3]):
                    chain.insert(0, s)
                elif close(chain[0][0], s[0]):
                    chain.insert(0, reverse(s))
                else:
                    continue
                pending.pop(k)
                grown = True
                break
        chains.append(chain)
    out = []
    for chain in chains:
        closed = len(chain) > 1 and close(chain[0][0], chain[-1][3]) or \
            (len(chain) == 1 and chain[0][1] is not None and close(chain[0][0], chain[0][3]))
        nodes = [node(chain[0][0][0], chain[0][0][1])]
        for s in chain:
            if s[1] is not None:
                nodes[-1][4], nodes[-1][5] = s[1]
                nodes.append(node(s[3][0], s[3][1], hin=s[2]))
            else:
                nodes.append(node(s[3][0], s[3][1]))
        if closed and len(nodes) > 1:
            last = nodes.pop()
            nodes[0][2], nodes[0][3] = last[2], last[3]
        out.append({"closed": closed, "nodes": nodes})
    return out


# ---- reading files with their curves ------------------------------------------------
def _is_color(rgb, target, delta=10):
    return all(abs(a - b) <= delta for a, b in zip(rgb, target))


def svg_segments(filename, ppi=96.0):
    """Segments of the red (cut) and blue (engrave) strokes of an SVG, in inches,
    y down from the top of the page, as K40 Whisperer classifies colours.
    Returns {"cut": [...], "engrave": [...]}, page height in inches."""
    import svgelements as se
    svg = se.SVG.parse(filename, ppi=ppi)
    out = {"cut": [], "engrave": []}
    for el in svg.elements():
        if not isinstance(el, se.Shape) or el.values.get("visibility") == "hidden":
            continue
        stroke = el.stroke
        if stroke is None or stroke.value is None:
            continue
        rgb = (stroke.red, stroke.green, stroke.blue)
        if _is_color(rgb, (255, 0, 0)):
            kind = "cut"
        elif _is_color(rgb, (0, 0, 255)):
            kind = "engrave"
        else:
            continue
        path = abs(se.Path(el))
        for seg in path:
            if isinstance(seg, (se.Move,)) or seg.start is None or seg.end is None:
                continue
            if isinstance(seg, (se.Line, se.Close)):
                if seg.start != seg.end:
                    out[kind].append(((seg.start.x / ppi, seg.start.y / ppi), None, None,
                                      (seg.end.x / ppi, seg.end.y / ppi)))
            elif isinstance(seg, se.CubicBezier):
                out[kind].append(tuple((p.x / ppi, p.y / ppi) for p in (seg.start, seg.control1,
                                                                         seg.control2, seg.end)))
            elif isinstance(seg, se.QuadraticBezier):
                s, c, e = seg.start, seg.control, seg.end
                c1 = (s.x + 2.0 / 3.0 * (c.x - s.x), s.y + 2.0 / 3.0 * (c.y - s.y))
                c2 = (e.x + 2.0 / 3.0 * (c.x - e.x), e.y + 2.0 / 3.0 * (c.y - e.y))
                out[kind].append(((s.x / ppi, s.y / ppi), (c1[0] / ppi, c1[1] / ppi),
                                  (c2[0] / ppi, c2[1] / ppi), (e.x / ppi, e.y / ppi)))
            elif isinstance(seg, se.Arc):
                for cb in seg.as_cubic_curves():
                    out[kind].append(tuple((p.x / ppi, p.y / ppi) for p in (cb.start, cb.control1,
                                                                             cb.control2, cb.end)))
    return out


def dxf_segments(filename, scale):
    """Segments of a DXF in inches (y up, as in the file), split into cut and
    engrave exactly like K40 Whisperer's reader; arcs stay arcs."""
    from dxf import DXF_CLASS

    class CurveDXF(DXF_CLASS):
        def __init__(self):
            super().__init__()
            self.curves = {"cut": [], "engrave": []}

        def _kind(self, color, layer):
            # same rules as DXF_CLASS.add_coords (None: hidden)
            slcolor = 0
            layers = layer if isinstance(layer, list) else [layer]
            for item in layers:
                if item in self.layer_color:
                    slcolor = self.layer_color[item]
            if slcolor is not None and slcolor < 0:
                return None
            if color is None or color == 256:
                color = slcolor
            if color is not None and color < 0:
                return None
            blue = (color == 5) or (color is not None and 140 <= color <= 180)
            engrave = any(isinstance(item, str) and "ENGRAVE" in item.upper() for item in layers)
            return "engrave" if blue or engrave else "cut"

        @staticmethod
        def _place(p, offset, scale_xy, rotate):
            x, y = p[0] * scale_xy[0], p[1] * scale_xy[1]
            if abs(rotate) > 1e-12:
                r = math.radians(rotate)
                x, y = x * math.cos(r) - y * math.sin(r), x * math.sin(r) + y * math.cos(r)
            return (x + offset[0], y + offset[1])

        def add_coords(self, line, offset, scale, rotate, color=None, layer=None):
            kind = self._kind(color, layer)
            if kind is not None:
                self.curves[kind].append((self._place(line[0:2], offset, scale, rotate), None, None,
                                          self._place(line[2:4], offset, scale, rotate)))
            super().add_coords(line, offset, scale, rotate, color, layer)

        def eval_entity(self, e, bl, lin_tol=.001, offset=[0, 0], scale=[1, 1], rotate=0):
            if e.type not in ("ARC", "CIRCLE", "LWPOLYLINE"):
                return super().eval_entity(e, bl, lin_tol, offset, scale, rotate)
            color = e.data.get("62")
            layer = e.data.get("8", 0)
            if color is not None and color < 0:
                return
            kind = self._kind(color, layer)
            if kind is None:
                return
            segs = []
            if e.type == "ARC":
                segs = arc_segments(e.data["10"], e.data["20"], e.data["40"], e.data["50"], e.data["51"])
            elif e.type == "CIRCLE":
                segs = arc_segments(e.data["10"], e.data["20"], e.data["40"], 0.0, 360.0)
            else:
                xs, ys = e.data.get("10"), e.data.get("20")
                if not isinstance(xs, list):
                    xs, ys = [xs], [ys]
                bulges = e.data.get("42", 0)
                if not isinstance(bulges, list):
                    bulges = [bulges] * len(xs)
                pts = list(zip(xs, ys))
                if e.data.get("70", 0) & 1 and len(pts) > 1:
                    pts.append(pts[0])
                for k in range(len(pts) - 1):
                    b = bulges[k] if k < len(bulges) else 0
                    segs += bulge_segments(pts[k][0], pts[k][1], pts[k + 1][0], pts[k + 1][1], b or 0)
            for s in segs:
                placed = tuple(None if p is None else self._place(p, offset, scale, rotate) for p in s)
                self.curves[kind].append(placed)

    reader = CurveDXF()
    with open(filename) as fd:
        reader.GET_DXF_DATA(fd, lin_tol=.0005 / scale, get_units=False, units=None)

    def scaled(s):
        return tuple(None if p is None else (p[0] * scale, p[1] * scale) for p in s)
    return {k: [scaled(s) for s in v] for k, v in reader.curves.items()}
