"""
Generators: ready-made designs from a few numbers (Generators group of the
toolbar). Each returns a Generated: shapes placed in millimetres (x right,
y down from the top-left of the design) and, when the design needs them, its
own layers (a material test has one layer per field). The window inserts it
as one group, as one undo step.

No Qt here: texts are given as text shapes, the window makes their outlines.

Copyright (C) 2026 Kerfly contributors
Licensed under the GNU General Public License v3 or later. See LICENSE.
"""
from dataclasses import dataclass, field

from .layers import CUT, ENGRAVE, EXTRA_COLORS, RASTER
from .shapes import ShapeSpec

KIND_OF_OPERATION = {"cut": CUT, "engrave": ENGRAVE, "fill": RASTER}


@dataclass
class LayerSpec:
    """A layer the design brings along (speed in the user's units like every layer, power 0..1)."""
    key: str
    kind: str
    name: str
    speed: float
    power: float = 0.5
    passes: int = 1
    color: str = ""
    enabled: bool = True           # unticked: e.g. the second sheet of a box, cut after the first


@dataclass
class Item:
    spec: ShapeSpec                # None for a picture (image)
    left: float                    # mm, top-left of the shape's bounding box
    top: float
    layer: str = ""                # key of a LayerSpec; "" = the default layer of its kind
    name: str = ""
    on_path_of: int = -1           # a text put on the path of item number ... (after placing)
    image: object = None           # a picture to engrave as a raster (made by the window)
    dpi: float = 0.0               # its resolution


@dataclass
class Generated:
    name: str
    items: list = field(default_factory=list)
    layers: list = field(default_factory=list)
    sheets: int = 1                # sheets of material it needs (the parts that fit the bed at once)


def _steps(lo, hi, n):
    if n <= 1:
        return [lo]
    return [lo + (hi - lo) * i / (n - 1) for i in range(n)]


def _num(v):
    return ("%.1f" % v).rstrip("0").rstrip(".")


# ------------------------------------------------------------------ material test
def material_test(operation="engrave", speed_min=10.0, speed_max=50.0, columns=5, rows_by="power",
                  power_min=20.0, power_max=60.0, passes_min=1, passes_max=3, rows=3, size=10.0, gap=3.0,
                  labels=True, speed_unit="mm/s", legend=""):
    """A grid of fields, each with its own speed (columns) and power or passes (rows),
    on a layer of its own; the values are engraved along the top and the left side.
    operation: "engrave" (outline), "cut", or "fill" (raster)."""
    columns = max(1, min(int(columns), 12))
    rows = max(1, min(int(rows), 12))
    kind = KIND_OF_OPERATION[operation]
    speeds = _steps(float(speed_min), float(speed_max), columns)
    if rows_by == "passes":
        values = [int(round(v)) for v in _steps(float(passes_min), float(passes_max), rows)]
    else:
        values = _steps(float(power_min), float(power_max), rows)
    out = Generated(name="Material test")
    label_w = 14.0 if labels else 0.0             # room for the row labels on the left
    label_h = 6.0 if labels else 0.0
    n = 0
    for r, value in enumerate(values):
        for c, speed in enumerate(speeds):
            key = "r%dc%d" % (r, c)
            if rows_by == "passes":
                text = "%s %s, %d x" % (_num(speed), speed_unit, value)
                layer = LayerSpec(key, kind, text, speed=speed, passes=value)
            else:
                text = "%s %s, %s %%" % (_num(speed), speed_unit, _num(value))
                layer = LayerSpec(key, kind, text, speed=speed, power=value / 100.0)
            layer.color = EXTRA_COLORS[n % len(EXTRA_COLORS)]
            out.layers.append(layer)
            spec = ShapeSpec(kind="rectangle", width=size, height=size, operation=operation)
            out.items.append(Item(spec, label_w + c * (size + gap), label_h + r * (size + gap), layer=key,
                                  name="Field"))
            n += 1
    if labels:
        font = max(1.5, min(3.0, size * 0.25))
        for c, speed in enumerate(speeds):
            out.items.append(Item(ShapeSpec(kind="text", text=_num(speed), font_size=font, operation="engrave"),
                                  label_w + c * (size + gap), 0.5, name="Label"))
        for r, value in enumerate(values):
            text = ("%dx" % value) if rows_by == "passes" else ("%s%%" % _num(value))
            out.items.append(Item(ShapeSpec(kind="text", text=text, font_size=font, operation="engrave"),
                                  0.0, label_h + r * (size + gap) + size / 2 - font / 2, name="Label"))
        if legend:                                    # e.g. "Speed (mm/s) / power (%)", in the user's language
            out.items.append(Item(ShapeSpec(kind="text", text=legend, font_size=font, operation="engrave"),
                                  label_w, label_h + rows * (size + gap) + 0.5, name="Label"))
    return out


# ------------------------------------------------------------------ rectilinear outlines
def _region_outline(rect, holes):
    """Outline of a rectangle minus rectangular notches (all axis-aligned; notches may
    stick out of the rectangle). rect / holes: (x0, y0, x1, y1). Returns the closed
    outlines as point lists (the outer one first), traced on the grid of all edges."""
    xs = sorted({rect[0], rect[2]} | {v for h in holes for v in (h[0], h[2]) if rect[0] < v < rect[2]})
    ys = sorted({rect[1], rect[3]} | {v for h in holes for v in (h[1], h[3]) if rect[1] < v < rect[3]})

    def filled(i, j):
        if i < 0 or j < 0 or i >= len(xs) - 1 or j >= len(ys) - 1:
            return False
        cx, cy = (xs[i] + xs[i + 1]) / 2, (ys[j] + ys[j + 1]) / 2
        return not any(h[0] < cx < h[2] and h[1] < cy < h[3] for h in holes)
    edges = {}                                   # start (i, j) -> end, material on the right (y down)
    for i in range(len(xs) - 1):
        for j in range(len(ys) - 1):
            if not filled(i, j):
                continue
            if not filled(i, j - 1):
                edges[(i, j)] = (i + 1, j)               # top, left to right
            if not filled(i + 1, j):
                edges[(i + 1, j)] = (i + 1, j + 1)       # right, down
            if not filled(i, j + 1):
                edges[(i + 1, j + 1)] = (i, j + 1)       # bottom, right to left
            if not filled(i - 1, j):
                edges[(i, j + 1)] = (i, j)               # left, up
    loops = []
    while edges:
        start = min(edges)
        loop, p = [start], edges.pop(start)
        while p != start:
            loop.append(p)
            p = edges.pop(p)
        pts = [(xs[i], ys[j]) for i, j in loop]
        clean = []                               # drop points in the middle of straight runs
        for k, q in enumerate(pts):
            a, b = pts[k - 1], pts[(k + 1) % len(pts)]
            if (a[0] == q[0] == b[0]) or (a[1] == q[1] == b[1]):
                continue
            clean.append(q)
        loops.append(clean)
    loops.sort(key=lambda l: -(max(p[0] for p in l) - min(p[0] for p in l)))
    return loops


def _polygon_item(points, left, top, operation="cut", name="", layer=""):
    x0 = min(p[0] for p in points)
    y0 = min(p[1] for p in points)
    pts = [(x - x0, y - y0) for x, y in points]
    spec = ShapeSpec(kind="polyline", operation=operation, points=pts, closed_path=True,
                     width=max(p[0] for p in pts), height=max(p[1] for p in pts))
    return Item(spec, left + x0, top + y0, layer=layer, name=name)


def _path_item(subpaths, left, top, operation="cut", name=""):
    """Item for polylines (each a list of points; closed if first == last), as one path shape."""
    from .curves import node
    xs = [x for sp in subpaths for x, _y in sp]
    ys = [y for sp in subpaths for _x, y in sp]
    x0, y0 = min(xs), min(ys)
    paths = []
    for sp in subpaths:
        closed = len(sp) > 2 and sp[0] == sp[-1]
        pts = sp[:-1] if closed else sp
        paths.append({"nodes": [node(x - x0, y - y0) for x, y in pts], "closed": closed})
    spec = ShapeSpec(kind="path", operation=operation, subpaths=paths)
    return Item(spec, left + x0, top + y0, name=name)


def _cell_outlines(cells):
    """Outlines (with holes) of the filled cells of a grid (rows of booleans), in cell
    units: the dark parts become whole shapes, with no seams between touching cells."""
    rows, cols = len(cells), len(cells[0]) if cells else 0

    def filled(i, j):
        return 0 <= j < rows and 0 <= i < cols and cells[j][i]
    edges = {}
    for j in range(rows):
        for i in range(cols):
            if not filled(i, j):
                continue
            if not filled(i, j - 1):
                edges.setdefault((i, j), []).append((i + 1, j))
            if not filled(i + 1, j):
                edges.setdefault((i + 1, j), []).append((i + 1, j + 1))
            if not filled(i, j + 1):
                edges.setdefault((i + 1, j + 1), []).append((i, j + 1))
            if not filled(i - 1, j):
                edges.setdefault((i, j + 1), []).append((i, j))
    loops = []
    while edges:
        start = min(edges)
        loop, p = [start], edges[start].pop()
        if not edges[start]:
            del edges[start]
        while p != start:
            loop.append(p)
            nxt = edges[p].pop()
            if not edges[p]:
                del edges[p]
            p = nxt
        clean = [q for k, q in enumerate(loop)
                 if not ((loop[k - 1][0] == q[0] == loop[(k + 1) % len(loop)][0]) or
                         (loop[k - 1][1] == q[1] == loop[(k + 1) % len(loop)][1]))]
        loops.append(clean)
    return loops


# ------------------------------------------------------------------ finger-joint box
def _fingers(length, finger):
    n = int(length / max(finger, 0.5))
    n = n if n % 2 else n - 1
    return max(3, n)


def finger_box(width=100.0, depth=80.0, height=50.0, thickness=3.0, finger=10.0, kerf=0.1, lid=True,
               inside=False, spacing=4.0, names=None, bed=None, each_layer=False, cut=(10.0, 0.5, 1),
               sheet_name="Sheet %d"):
    """A box joined with fingers: bottom, four walls and (lid) a top, laid out side by
    side. Sizes are outside sizes (inside=True: inside sizes). kerf: width of the cut;
    every part grows by half of it, so the fingers fit tightly after cutting.

    bed: (width, height) mm of the work area: the parts are laid out in rows that
    fit it, and parts that do not fit go on a next sheet, at the same place on its
    own unticked cut layer (cut sheet 1, change the material, tick sheet 2).
    each_layer: every part on its own cut layer (named after the part).
    cut: (speed, power, passes) for the new layers (those of the cut layer)."""
    t = float(thickness)
    if inside:
        width, depth, height = width + 2 * t, depth + 2 * t, height + (2 if lid else 1) * t
    W, D, H = float(width), float(depth), float(height)
    if min(W, D, H) <= 3 * t:
        raise ValueError("The box is too small for this material thickness.")
    names = names or {}
    k2 = max(0.0, float(kerf)) / 2.0
    out = Generated(name="Finger-joint box")

    def notches(w, h, edges):
        """edges: (top, right, bottom, left), each "in" (slots where the other part's
        fingers go), "out" (fingers) or "flat"."""
        holes = []
        for side, kind in zip(("top", "right", "bottom", "left"), edges):
            if kind == "flat":
                continue
            length = w if side in ("top", "bottom") else h
            n = _fingers(length, finger)
            seg = length / n
            for s in range(n):
                notch = (s % 2 == 0) if kind == "in" else (s % 2 == 1)
                if not notch:
                    continue
                a, b = s * seg, (s + 1) * seg
                if s == 0:
                    a = -1.0                       # past the corner, so the kerf does not leave a sliver
                if s == n - 1:
                    b = length + 1.0
                if side == "top":
                    holes.append((a, -1, b, t))
                elif side == "bottom":
                    holes.append((a, h - t, b, h + 1))
                elif side == "left":
                    holes.append((-1, a, t, b))
                else:
                    holes.append((w - t, a, w + 1, b))
        # the kerf: the part grows by half a cut, the notches shrink by as much
        holes = [(x0 + k2, y0 + k2, x1 - k2, y1 - k2) for x0, y0, x1, y1 in holes if x1 - x0 > 2 * k2]
        return _region_outline((-k2, -k2, w + k2, h + k2), holes)

    top_edge = "out" if lid else "flat"
    parts = [("bottom", W, D, ("in", "in", "in", "in")),
             ("front", W, H, (top_edge, "out", "out", "out")),
             ("back", W, H, (top_edge, "out", "out", "out")),
             ("left", D, H, (top_edge, "in", "out", "in")),
             ("right", D, H, (top_edge, "in", "out", "in"))]
    if lid:
        parts.append(("lid", W, D, ("in", "in", "in", "in")))
    row_w = max(2 * W + spacing, W + D + spacing) + 1
    if bed is not None:
        bed_w, bed_h = (max(10.0, float(v) - 2.0) for v in bed)     # a little room to the bed's edges
        row_w = min(row_w, bed_w)
    else:
        bed_w = bed_h = float("inf")
    speed, power, passes = cut
    sheet, x, y, row_h = 1, 0.0, 0.0, 0.0
    sheet_keys = {}
    for name, w, h, edges in parts:
        if x > 0 and x + w > row_w:                                 # next row
            x, y, row_h = 0.0, y + row_h + spacing, 0.0
        if y > 0 and y + h > bed_h:                                 # does not fit: next sheet, same place
            sheet, x, y, row_h = sheet + 1, 0.0, 0.0, 0.0
        layer = ""
        if each_layer:
            layer = "part " + name
            out.layers.append(LayerSpec(layer, CUT, names.get(name, name.capitalize()), speed, power, passes,
                                        EXTRA_COLORS[len(out.layers) % len(EXTRA_COLORS)], enabled=sheet == 1))
        elif sheet > 1:
            layer = sheet_keys.get(sheet)
            if layer is None:
                layer = sheet_keys[sheet] = "sheet %d" % sheet
                out.layers.append(LayerSpec(layer, CUT, sheet_name % sheet, speed, power, passes,
                                            EXTRA_COLORS[(sheet - 2) % len(EXTRA_COLORS)], enabled=False))
        for loop in notches(w, h, edges):
            out.items.append(_polygon_item([(px + x, py + y) for px, py in loop], 0, 0, "cut",
                                           names.get(name, name.capitalize()), layer))  # Bottom, Front, ...
        x += w + spacing
        row_h = max(row_h, h)
    out.sheets = sheet
    return out


# ------------------------------------------------------------------ kerf test
def kerf_test(length=50.0, pieces=10, strip=10.0, thickness=3.0, fit_from=-0.20, fit_to=0.10, fits=7,
              slot_depth=10.0, labels=True, note=""):
    """A comb cut into pieces (push them together and measure: kerf = (length - measured) /
    pieces) and a plate with slots for the material's thickness plus a clearance each,
    to see which fit holds a strip of the comb."""
    pieces = max(2, min(int(pieces), 30))
    fits = max(1, min(int(fits), 12))
    out = Generated(name="Kerf test")
    out.items.append(Item(ShapeSpec(kind="rectangle", width=length, height=strip, operation="cut"), 0, 0,
                          name="Comb"))
    step = length / pieces
    for n in range(1, pieces):
        out.items.append(Item(ShapeSpec(kind="line", width=0, height=strip, operation="cut"), n * step, 0,
                              name="Comb cut"))
    clearances = _steps(float(fit_from), float(fit_to), fits)
    pitch = max(thickness + 6.0, 8.0)
    plate_w = fits * pitch + 4.0
    plate_h = slot_depth + 12.0
    top = strip + (10.0 if labels else 6.0)
    holes = []
    for n, c in enumerate(clearances):
        w = max(0.2, thickness + c)
        cx = 2.0 + pitch * (n + 0.5)
        holes.append((cx - w / 2, -1, cx + w / 2, slot_depth))
    for loop in _region_outline((0, 0, plate_w, plate_h), holes):
        out.items.append(_polygon_item([(px, py + top) for px, py in loop], 0, 0, "cut", "Slot plate"))
    if labels:
        for n, c in enumerate(clearances):
            text = "0.00" if abs(c) < 0.005 else ("%+.2f" % c).replace("+0.", "+.").replace("-0.", "-.")
            out.items.append(Item(ShapeSpec(kind="text", text=text, font_size=2.2, operation="engrave"),
                                  2.0 + pitch * n + 0.5, top + slot_depth + 2.0, name="Label"))
        if note:
            out.items.append(Item(ShapeSpec(kind="text", text=note, font_size=2.5, operation="engrave"),
                                  0, strip + 2.0, name="Label"))
    return out


# ------------------------------------------------------------------ gear
def gear(teeth=20, module=2.0, pressure_angle=20.0, bore=5.0, points_per_flank=8):
    """A spur gear with involute teeth: teeth, module (pitch diameter = module x teeth),
    pressure angle; a round hole for the axle (0: none)."""
    import math
    z = max(6, min(int(teeth), 200))
    m = float(module)
    alpha = math.radians(pressure_angle)
    r = m * z / 2.0
    rb = r * math.cos(alpha)
    ra = r + m
    rf = max(r - 1.25 * m, 0.5)

    def inv(a):
        return math.tan(a) - a
    # half the tooth's angular thickness at the base circle
    half_base = math.pi / (2 * z) + inv(alpha)
    pts = []
    r_start = max(rb, rf)
    for k in range(z):
        centre = 2 * math.pi * k / z
        flank = []
        for i in range(points_per_flank + 1):
            rr = r_start + (ra - r_start) * i / points_per_flank
            phi = math.acos(min(1.0, rb / rr))
            flank.append((rr, half_base - inv(phi)))
        left = [(rr, centre - a) for rr, a in flank]
        right = [(rr, centre + a) for rr, a in reversed(flank)]
        tooth = [(rf, centre - half_base - (math.pi / z - half_base) * 0.5)] + left + right + \
            [(rf, centre + half_base + (math.pi / z - half_base) * 0.5)]
        pts += tooth
    poly = [(ra + rr * math.cos(a), ra + rr * math.sin(a)) for rr, a in pts]
    out = Generated(name="Gear")
    out.items.append(_polygon_item(poly, 0, 0, "cut", "Gear"))
    if bore > 0:
        out.items.append(Item(ShapeSpec(kind="ellipse", width=bore, height=bore, operation="cut"),
                              ra - bore / 2, ra - bore / 2, name="Axle hole"))
    return out


# ------------------------------------------------------------------ jigsaw puzzle
def puzzle(width=150.0, height=100.0, columns=5, rows=4, tab=0.22, seed=1, outline=True):
    """A jigsaw puzzle: inner cuts with round tabs (direction from the seed), and the
    outline. Each inner edge is one line, so the laser does not cut twice."""
    import random
    rnd = random.Random(int(seed))
    columns = max(2, min(int(columns), 40))
    rows = max(2, min(int(rows), 40))
    cw, ch = width / columns, height / rows

    def knob(jitter_u, jitter_r):
        """A classic tab in edge units (u along the edge 0..1, v to the side): a narrow
        neck and a round head that turns back under itself, 0.29 high."""
        import math

        def bezier(p0, c1, c2, p3, n=8):
            out = []
            for i in range(1, n + 1):
                t = i / n
                a, b_, c, d = (1 - t) ** 3, 3 * (1 - t) ** 2 * t, 3 * (1 - t) * t * t, t ** 3
                out.append((a * p0[0] + b_ * c1[0] + c * c2[0] + d * p3[0],
                            a * p0[1] + b_ * c1[1] + c * c2[1] + d * p3[1]))
            return out
        cu = 0.5 + jitter_u                         # the head's centre along the edge
        r = 0.125 * jitter_r                        # the head's radius
        cv = 0.29 - r                               # its centre to the side (the top stays at 0.29)
        neck = 0.06 * jitter_r                      # half the neck's width where it meets the head
        nv = cv - math.sqrt(max(r * r - neck * neck, 0.0))     # where the neck meets the circle
        a0 = math.atan2(nv - cv, -neck)             # lower left of the head
        a1 = math.atan2(nv - cv, neck) + 2 * math.pi            # lower right, after going over the top
        pts = [(0.0, 0.0), (cu - 0.14, 0.0)]
        # a soft shoulder into the neck (it widens towards the edge)
        pts += bezier((cu - 0.14, 0.0), (cu - 0.06, 0.0), (cu - neck + 0.005, nv * 0.35), (cu - neck, nv))
        steps = 28                                  # the head, from lower left over the top to lower right
        start, end = a0, a1 - 2 * math.pi
        if start < end:
            start += 2 * math.pi
        for i in range(1, steps + 1):
            ang = start + (end - start) * i / steps
            pts.append((cu + r * math.cos(ang), cv + r * math.sin(ang)))
        pts += bezier((cu + neck, nv), (cu + neck - 0.005, nv * 0.35), (cu + 0.06, 0.0), (cu + 0.14, 0.0))
        pts.append((1.0, 0.0))
        return pts

    def edge(p0, p1, size):
        """Points of one edge from p0 to p1 with a round tab to one side."""
        (x0, y0), (x1, y1) = p0, p1
        dx, dy = x1 - x0, y1 - y0
        nx, ny = -dy, dx                           # a side of the edge
        side = 1 if rnd.random() < 0.5 else -1
        shape = knob(rnd.uniform(-0.04, 0.04), rnd.uniform(0.92, 1.08))     # a little different each time
        k = side * size / 0.29
        return [(x0 + dx * u + nx * v * k, y0 + dy * u + ny * v * k) for u, v in shape]
    lines = []
    for c in range(1, columns):
        x = c * cw
        pts = []
        for r in range(rows):
            seg = edge((x, r * ch), (x, (r + 1) * ch), tab)
            pts += seg if not pts else seg[1:]
        lines.append(pts)
    for r in range(1, rows):
        y = r * ch
        pts = []
        for c in range(columns):
            seg = edge((c * cw, y), ((c + 1) * cw, y), tab)
            pts += seg if not pts else seg[1:]
        lines.append(pts)
    out = Generated(name="Puzzle")
    out.items.append(_path_item(lines, 0, 0, "cut", "Puzzle cuts"))
    if outline:
        out.items.append(Item(ShapeSpec(kind="rectangle", width=width, height=height, operation="cut"), 0, 0,
                              name="Puzzle outline"))
    return out


# ------------------------------------------------------------------ ruler
def ruler(length=150.0, width=25.0, outline=True, numbers=True, unit="mm"):
    """A ruler: a mark every millimetre (longer every 5 and 10), numbers every 10 mm,
    engraved; the outline cut."""
    length = max(10.0, float(length))
    marks = []
    for n in range(int(length) + 1):
        mm = 1.0 * n
        h = 6.0 if n % 10 == 0 else (4.5 if n % 5 == 0 else 3.0)
        marks.append([(5.0 + mm, 0.0), (5.0 + mm, h)])
    out = Generated(name="Ruler")
    out.items.append(_path_item(marks, 0, 1.0 if outline else 0.0, "engrave", "Marks"))
    if numbers:
        for n in range(0, int(length) + 1, 10):
            text = str(n // 10) if unit == "cm" else str(n)
            out.items.append(Item(ShapeSpec(kind="text", text=text, font_size=3.0, operation="engrave"),
                                  5.0 + n - 0.8 * len(text), 9.0, name="Number"))
    if outline:
        out.items.append(Item(ShapeSpec(kind="rectangle", width=length + 10.0, height=width, corner_radius=2,
                                        operation="cut"), 0, 0, name="Ruler outline"))
    return out


# ------------------------------------------------------------------ laser test card
def test_card():
    """The laser test card: every operation on a piece of 3 mm plywood of about
    160 x 100 mm (what to measure: DEVELOPMENT.md, "Laser test card")."""
    from .curves import node
    out = Generated(name="Test card")
    add = out.items.append
    add(Item(ShapeSpec(kind="rectangle", width=50, height=50, operation="cut"), 5, 5, name="Square 50 mm"))
    add(Item(ShapeSpec(kind="ellipse", width=20, height=20, operation="cut"), 20, 20, name="Hole 20 mm"))
    ruler_paths = [{"nodes": [node(0, 0), node(100, 0)], "closed": False}]
    for n in range(11):
        ruler_paths.append({"nodes": [node(10 * n, 0), node(10 * n, 4 if n % 5 else 6)], "closed": False})
    add(Item(ShapeSpec(kind="path", operation="engrave", subpaths=ruler_paths), 62, 6, name="Ruler 100 mm"))
    add(Item(ShapeSpec(kind="text", text="100 mm", font_size=3, operation="engrave"), 104, 13, name="Label"))
    add(Item(ShapeSpec(kind="rectangle", width=30, height=10, corner_radius=2, operation="fill"), 62, 22,
             name="Raster block"))
    add(Item(ShapeSpec(kind="text", text="Kerfly", font_size=8, bold=True, operation="fill"), 98, 22,
             name="Raster text"))
    for n, pattern in enumerate(("lines", "honeycomb", "waves", "circles")):
        add(Item(ShapeSpec(kind="rectangle", width=18, height=18, operation="cut", fill_pattern=pattern,
                           fill_spacing=2.0, fill_margin=0.5), 62 + 22 * n, 38, name="Pattern fill"))
    add(Item(ShapeSpec(kind="rectangle", width=60, height=30, corner_radius=2, operation="cut",
                       hinge_pattern="straight", hinge_cut=12, hinge_gap=2.5, hinge_spacing=1.5, hinge_margin=3),
             5, 62, name="Living hinge"))
    circle = len(out.items)
    add(Item(ShapeSpec(kind="ellipse", width=30, height=30, operation="cut"), 75, 62, name="Circle"))
    add(Item(ShapeSpec(kind="text", text="KERFLY TEST", font_size=4, operation="engrave", text_path_distance=1),
             75, 100, name="Text on a path", on_path_of=circle))
    add(Item(ShapeSpec(kind="rectangle", width=25, height=18, operation="cut", tabs=2, tab_width=1.5), 112, 62,
             name="Bridges"))
    add(Item(ShapeSpec(kind="polygon", width=16, height=16, sides=5, operation="engrave"), 114, 84,
             name="Pentagon"))
    add(Item(ShapeSpec(kind="line", width=60, height=0, operation="cut"), 5, 100, name="Open line"))
    return out


# ------------------------------------------------------------------ QR code
def qr_code(text="https://cyryllo.github.io/Kerfly/", size=30.0, error="m", border=2):
    """A QR code to engrave as a raster: one shape, the dark modules joined into
    rows. size: width of the code with its border (mm); error: l, m, q or h (more
    can be scratched off and still read); border: free modules around it."""
    if not text:
        raise ValueError("Type the text or address the QR code should hold.")
    try:
        import segno
    except ImportError:
        raise ValueError("QR codes need the segno library (pip install segno).")
    matrix = segno.make(text, error=error, micro=False).matrix
    n = len(matrix)
    border = max(0, int(border))
    cell = float(size) / (n + 2 * border)
    loops = _cell_outlines([[bool(v) for v in row] for row in matrix])
    paths = [[((border + x) * cell, (border + y) * cell) for x, y in loop + loop[:1]] for loop in loops]
    out = Generated(name="QR code")
    out.items.append(_path_item(paths, 0, 0, "fill", "QR code"))
    return out
