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
    active: bool = True            # in the job at first (a box's sheets 2 and on: ticked when their turn comes)
    group: tuple = ()              # groups inside the design's group, outermost first: ((key, name), ...),
    #                                e.g. (("sheet 2", "Sheet 2"), ("part 7", "Left side")) for a box


@dataclass
class Generated:
    name: str
    items: list = field(default_factory=list)
    layers: list = field(default_factory=list)
    sheets: int = 1                # sheets of material it needs (the parts that fit the bed at once)
    # the parts put together, for the 3D preview of boxes: dicts with "name", "loops" (the part's outline and
    # holes in its own frame, mm, y down), "origin", "u", "v", "n" (3D mm: where its (0, 0) is, the 3D
    # directions of its x and y, the direction of its thickness), "t"; or kind "band" (a bent wall: "path"
    # of 3D points along its inner face, "out" outward directions, "height", "t", "closed"; "strips": the flat
    # strips it is made of, {"loops" (x along the face, y down from the top), "start" (where x = 0 is along the
    # path, mm)}, "length": the path's length the strips are measured on)
    assembly: list = field(default_factory=list)


def _part_groups(sheet, sheets, sheet_name, index, label, pieces):
    """The groups of a box part's shapes: its sheet's (when there are several sheets), and its own when it
    is made of several shapes (an outline and its slots)."""
    levels = []
    if sheets > 1:
        levels.append(("sheet %d" % sheet, sheet_name % sheet))
    if pieces > 1:
        levels.append(("part %d" % index, label))
    return tuple(levels)


def _by_sheet(out):
    """The parts in the order of their sheets (sheet 1 first)."""
    def sheet_of(item):
        key = item.group[0][0] if item.group else ""
        return int(key.split()[1]) if key.startswith("sheet ") else 0
    out.items.sort(key=sheet_of)


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


def _pack_parts(sizes, bed, spacing, row_w):
    """Places parts (w, h) on as few sheets of the bed as it can: [(sheet, x, y, turned)] in the order
    given. Bigger parts first, each into the free space of the first sheet it fits (turned by 90 degrees
    when only that fits, or fits better), a new sheet when none has room (MaxRects, best short side).
    Without a bed: rows `row_w` wide, as before."""
    if bed is None:
        out, x, y, row_h = [], 0.0, 0.0, 0.0
        for w, h in sizes:
            if x > 0 and x + w > row_w:
                x, y, row_h = 0.0, y + row_h + spacing, 0.0
            out.append((1, x, y, False))
            x += w + spacing
            row_h = max(row_h, h)
        return out
    from .nesting import pack
    return pack(sizes, bed, spacing)


def _turned(points, h):
    """Points of a part w x h turned by 90 degrees (into an h x w box)."""
    return [(h - y, x) for x, y in points]


def finger_box(width=100.0, depth=80.0, height=50.0, thickness=3.0, finger=10.0, kerf=0.1, lid=True,
               inside=False, spacing=4.0, names=None, bed=None, each_layer=False, cut=(10.0, 0.5, 1),
               sheet_name="Sheet %d", dividers_across=0, dividers_along=0, sliding=False, clearance=0.5):
    """A box joined with fingers: bottom, four walls and (lid) a top, laid out side by
    side. Sizes are outside sizes (inside=True: inside sizes). kerf: width of the cut;
    every part grows by half of it, so the fingers fit tightly after cutting.

    bed: (width, height) mm of the work area: the parts are laid out in rows that
    fit it, and parts that do not fit go on a next sheet, at the same place on its
    own unticked cut layer (cut sheet 1, change the material, tick sheet 2).
    each_layer: every part on its own cut layer (named after the part).
    cut: (speed, power, passes) for the new layers (those of the cut layer).
    dividers_across / dividers_along (beta): inner walls parallel to the front / to the sides,
    evenly spaced; their tabs go through slots in the walls and the bottom, crossing dividers
    are joined by slots to half their height.
    sliding (beta, with lid): a lid that slides in from the front, in a groove between two level rails
    on each side wall, held by tabs in slots of the wall (the upper rail under a strip of the wall at least
    3 mm high, for strength; the lower one below the lid); the front wall is lower, so the lid slides over
    it. clearance: play of the lid in its
    groove and between the walls (mm)."""
    t = float(thickness)
    if inside:
        width, depth, height = width + 2 * t, depth + 2 * t, height + (2 if lid else 1) * t
    W, D, H = float(width), float(depth), float(height)
    if min(W, D, H) <= 3 * t:
        raise ValueError("The box is too small for this material thickness.")
    names = names or {}
    k2 = max(0.0, float(kerf)) / 2.0
    out = Generated(name="Finger-joint box")

    def notches(w, h, edges, extra=()):
        """edges: (top, right, bottom, left), each "in" (slots where the other part's
        fingers go), "out" (fingers) or "flat". extra: more rectangular holes (slots)."""
        holes = list(extra)
        for side, kind in zip(("top", "right", "bottom", "left"), edges):
            if kind == "flat":
                continue
            full = w if side in ("top", "bottom") else h
            start, end = 0.0, full
            if isinstance(kind, tuple):            # fingers on a part of the edge only (kind, start, end)
                kind, start, end = kind
            length = end - start
            n = _fingers(length, finger)
            seg = length / n
            for s in range(n):
                notch = (s % 2 == 0) if kind == "in" else (s % 2 == 1)
                if not notch:
                    continue
                a, b = start + s * seg, start + (s + 1) * seg
                if s == 0 and start <= 0:
                    a = -1.0                       # past the corner, so the kerf does not leave a sliver
                if s == n - 1 and end >= full:
                    b = full + 1.0
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
    # dividers (beta): positions, height, their tabs and the slots that take them
    na, nb = max(0, int(dividers_across)), max(0, int(dividers_along))
    Wi, Di = W - 2 * t, D - 2 * t
    sliding = bool(sliding) and bool(lid)
    c = max(0.0, float(clearance))
    rail_w = max(2 * t, 6.0)                         # how far a rail stands out from its wall (sliding lid)
    groove = t + c                                   # the lid's groove between the two rails
    above = max(3.0, t)                              # wall left above the upper rail (a top edge, for strength)
    Hf = H - above - t - groove                      # sliding lid: the front's height (the lid slides over it)
    if sliding and H - above - 3 * t - groove - t < 3 * t:
        raise ValueError("The box is too low for a sliding lid of this material thickness.")
    if sliding:
        Hd = H - above - 2 * t - groove - t          # the dividers end below the lower rail
    else:
        Hd = H - t - (t if lid else 0.0)             # from the inside of the bottom to the lid
    top_off = H - t - Hd                             # the dividers' top, from the top of the walls
    ys = [t + Di * k / (na + 1.0) for k in range(1, na + 1)]     # across: from the front's outer face
    xs = [t + Wi * k / (nb + 1.0) for k in range(1, nb + 1)]     # along: from the left's outer face
    tab0, tab1 = Hd / 4.0, 3 * Hd / 4.0              # the side tab of a divider (from its top)

    def tab_segments(length):
        n = _fingers(length, finger)
        seg = length / n
        return [(s * seg, (s + 1) * seg) for s in range(n) if s % 2 == 1]
    wall_slots_front = [(x - t / 2, top_off + tab0, x + t / 2, top_off + tab1) for x in xs]
    wall_slots_side = [(y - t / 2, top_off + tab0, y + t / 2, top_off + tab1) for y in ys]
    bottom_slots = [(t + a, y - t / 2, t + b, y + t / 2) for y in ys for a, b in tab_segments(Wi)]
    if not na:                                       # along dividers stand on the bottom with tabs too
        bottom_slots += [(x - t / 2, t + a, x + t / 2, t + b) for x in xs for a, b in tab_segments(Di)]

    def divider(length, crossings, from_top, with_tabs):
        """A divider: length inside, its side tabs out by t through the walls, bottom tabs (with_tabs)
        through the bottom, slots to half height where it crosses the others (from the top or the bottom)."""
        w_, h_ = length + 2 * t, Hd + t
        holes = [(-1, -1, t, tab0), (-1, tab1, t, h_ + 1), (t + length, -1, w_ + 1, tab0),
                 (t + length, tab1, w_ + 1, h_ + 1)]
        # below the inside height: only the bottom tabs stay (the cuts go past the corners, so the kerf
        # leaves no sliver there)
        if with_tabs:
            last = -1.0
            for a, b in tab_segments(length):
                holes.append((last, Hd, t + a, h_ + 1))
                last = t + b
            holes.append((last, Hd, w_ + 1, h_ + 1))
        else:
            holes.append((-1.0, Hd, w_ + 1, h_ + 1))
        for c in crossings:
            holes.append((c - t / 2, -1, c + t / 2, Hd / 2.0) if from_top else (c - t / 2, Hd / 2.0, c + t / 2, h_ + 1))
        holes = [(x0 + k2, y0 + k2, x1 - k2, y1 - k2) for x0, y0, x1, y1 in holes if x1 - x0 > 2 * k2]
        return _region_outline((-k2, -k2, w_ + k2, h_ + k2), holes), w_, h_
    if sliding:
        # the front is lower: its slots for the along dividers are measured from its own top
        front_slots = [(x0, y0 - (H - Hf), x1, y1 - (H - Hf)) for x0, y0, x1, y1 in wall_slots_front]
        front_edge = ("in", H - Hf, H)               # the side walls take the front's fingers below its top
        # the rails' tabs go into slots of the side walls, the upper rail's under a strip of the wall
        # (`above`), the lower rail's under the groove
        rail_tabs = tab_segments(Di)
        rail_slots = [(t + a, above, t + b, above + t) for a, b in rail_tabs] + \
            [(t + a, above + t + groove, t + b, above + 2 * t + groove) for a, b in rail_tabs]

        def rail():
            """A level rail: Di long, rail_w wide, its tabs t deep into the wall along one long edge."""
            holes, last = [], -1.0
            for a, b in rail_tabs:
                holes.append((last, rail_w, a, rail_w + t + 1))
                last = b
            holes.append((last, rail_w, Di + 1, rail_w + t + 1))
            holes = [(x0 + k2, y0 + k2, x1 - k2, y1 - k2) for x0, y0, x1, y1 in holes if x1 - x0 > 2 * k2]
            return _region_outline((-k2, -k2, Di + k2, rail_w + t + k2), holes)
        parts = [("bottom", W, D, ("in", "in", "in", "in"), bottom_slots),
                 ("front", W, Hf, ("flat", "out", "out", "out"), front_slots),
                 ("back", W, H, ("flat", "out", "out", "out"), wall_slots_front),
                 ("left", D, H, ("flat", "in", "out", front_edge), wall_slots_side + rail_slots),
                 ("right", D, H, ("flat", front_edge, "out", "in"), wall_slots_side + rail_slots),
                 ("lid", Wi - c, D - t - c, ("flat",) * 4, ())]
        for name in ("upper rail", "upper rail", "lower rail", "lower rail"):
            parts.append((name, Di, rail_w + t, None, rail()))
    else:
        parts = [("bottom", W, D, ("in", "in", "in", "in"), bottom_slots),
                 ("front", W, H, (top_edge, "out", "out", "out"), wall_slots_front),
                 ("back", W, H, (top_edge, "out", "out", "out"), wall_slots_front),
                 ("left", D, H, (top_edge, "in", "out", "in"), wall_slots_side),
                 ("right", D, H, (top_edge, "in", "out", "in"), wall_slots_side)]
        if lid:
            parts.append(("lid", W, D, ("in", "in", "in", "in"), ()))
    for k in range(na):
        parts.append(("divider across %d" % (k + 1), Wi + 2 * t, Hd + t, None,
                      divider(Wi, xs, True, True)[0]))
    for k in range(nb):
        parts.append(("divider along %d" % (k + 1), Di + 2 * t, Hd + t, None,
                      divider(Di, ys, False, not na)[0]))
    row_w = max(2 * W + spacing, W + D + spacing) + 1
    speed, power, passes = cut
    places = _pack_parts([(p_[1], p_[2]) for p_ in parts], bed, spacing, row_w)
    n_sheets = max(p_[0] for p_ in places) if places else 1
    seen = {}

    def placement(name, w, h):
        """Where a part stands in the box (z up, x to the right, y from the front to the back)."""
        n_seen = seen.get(name, 0)
        seen[name] = n_seen + 1
        X, Y, Z = (1, 0, 0), (0, 1, 0), (0, 0, 1)
        down = (0, 0, -1)
        if name == "bottom":
            return (0, 0, 0), X, Y, Z
        if name == "lid" and sliding:
            return (t + c / 2.0, 0, Hf), X, Y, Z
        if name == "lid":
            return (0, 0, H - t), X, Y, Z
        if name == "front":
            return (0, 0, h), X, down, Y
        if name == "back":
            return (0, D - t, H), X, down, Y
        if name == "left":
            return (0, 0, H), Y, down, X
        if name == "right":
            return (W - t, D, H), (0, -1, 0), down, X
        if name.startswith("divider across"):
            k = int(name.rsplit(" ", 1)[1]) - 1
            return (0, ys[k] - t / 2.0, t + Hd), X, down, Y
        if name.startswith("divider along"):
            k = int(name.rsplit(" ", 1)[1]) - 1
            return (xs[k] - t / 2.0, 0, t + Hd), Y, down, X
        if name.endswith("rail"):
            z0 = (H - above - t) if name == "upper rail" else (H - above - 2 * t - groove)
            if n_seen == 0:                         # the left wall's
                return (t + rail_w, t, z0), Y, (-1, 0, 0), Z
            return (W - t - rail_w, t, z0), Y, (1, 0, 0), Z
        return (0, 0, 0), X, Y, Z
    for part, (sheet, x, y, turned) in zip(parts, places):
        name, w, h, edges, extra = part[:5]
        layer = ""
        if each_layer:
            layer = "part " + name
            out.layers.append(LayerSpec(layer, CUT, names.get(name, name.capitalize()), speed, power, passes,
                                        EXTRA_COLORS[len(out.layers) % len(EXTRA_COLORS)]))
        loops = notches(w, h, edges, extra) if edges is not None else extra   # a divider, a rail: its outline
        if name.startswith("divider") and name[-1].isdigit():
            base, number = name.rsplit(" ", 1)
            label = "%s %s" % (names.get(base, base.capitalize()), number)       # Divider across 1, ...
        else:
            label = names.get(name, name.capitalize())
        origin, u, v, n = placement(name, w, h)
        out.assembly.append({"name": label, "loops": [list(lp) for lp in loops], "origin": origin, "u": u,
                             "v": v, "n": n, "t": t, "slides": sliding and name == "lid"})
        if turned:
            loops = [_turned(lp, h) for lp in loops]
        groups = _part_groups(sheet, n_sheets, sheet_name, len(out.assembly), label, len(loops))
        for loop in loops:
            out.items.append(_polygon_item([(px + x, py + y) for px, py in loop], 0, 0, "cut",
                                           label, layer))  # Bottom, Front, ...
            out.items[-1].group = groups
            out.items[-1].active = sheet == 1
    out.sheets = max(p_[0] for p_ in places) if places else 1
    _by_sheet(out)
    return out


# ------------------------------------------------------------------ rounded box with a living hinge (beta)
def hinge_box(width=100.0, depth=80.0, height=50.0, radius=20.0, thickness=3.0, finger=10.0, kerf=0.1,
              lid=True, cut_len=16.0, gap=3.0, spacing=1.5, spacing_parts=4.0, names=None, bed=None,
              cut=(10.0, 0.5, 1), sheet_name="Sheet %d", rim=12.0):
    """A box with rounded corners (beta): the bottom and the lid are rounded rectangles with tabs on their
    straight sides; the wall is two equal strips that bend round the corners with a living hinge, the
    tabs going through slots in them. Sizes are outside sizes; radius is the outside corner radius.
    The plates sit one material thickness in from the wall's edges. Without a lid a rim (a ring rim mm
    wide, with the same tabs) holds the top of the wall in shape. The parts are laid out to fit the bed;
    those that do not fit go on next sheets (their cut layers unticked)."""
    import math as _m
    from .patterns import hinge_lines
    t = float(thickness)
    W, D, H, r = float(width), float(depth), float(height), float(radius)
    if r < t + 3:
        raise ValueError("The corner radius must be at least the material thickness plus 3 mm.")
    if min(W, D) < 2 * r + 2 * finger or H < 4 * t + 10:
        raise ValueError("The box is too small for this corner radius, finger width and material thickness.")
    names = names or {}
    k = max(0.0, float(kerf)) / 2.0
    Wp, Dp, rp = W - 2 * t, D - 2 * t, r - t            # the inside of the wall: the plates
    Lx, Ly, La = Wp - 2 * rp, Dp - 2 * rp, _m.pi * rp / 2.0
    out = Generated(name="Rounded box")

    def segments(length, seam):
        """Tabs (a, b) along a straight side: an odd number of segments, tabs at the odd ones; with a seam in
        the middle (front and back) the middle segment is a gap, so no tab is cut in two."""
        n = _fingers(length, finger)
        if seam and n % 4 == 3:
            n = n + 2 if n < 5 else n - 2
        seg = length / n
        return [(i * seg, (i + 1) * seg) for i in range(n) if i % 2 == 1]
    tabs_x, tabs_y = segments(Lx, True), segments(Ly, False)

    def arc(cx, cy, rad, a0, a1):
        steps = max(6, int(abs(a1 - a0) * rad / 0.5))
        return [(cx + rad * _m.cos(a0 + (a1 - a0) * i / steps), cy + rad * _m.sin(a0 + (a1 - a0) * i / steps))
                for i in range(steps + 1)]

    def plate():
        R = rp + k
        pts = [(rp, -k)]
        for a, b in tabs_x:                                     # top: tabs up
            pts += [(rp + a - k, -k), (rp + a - k, -t - k), (rp + b + k, -t - k), (rp + b + k, -k)]
        pts += arc(Wp - rp, rp, R, -_m.pi / 2, 0.0)
        for a, b in tabs_y:                                     # right: tabs to the right
            pts += [(Wp + k, rp + a - k), (Wp + t + k, rp + a - k), (Wp + t + k, rp + b + k), (Wp + k, rp + b + k)]
        pts += arc(Wp - rp, Dp - rp, R, 0.0, _m.pi / 2)
        for a, b in reversed(tabs_x):                           # bottom: tabs down, right to left
            pts += [(rp + b + k, Dp + k), (rp + b + k, Dp + t + k), (rp + a - k, Dp + t + k), (rp + a - k, Dp + k)]
        pts += arc(rp, Dp - rp, R, _m.pi / 2, _m.pi)
        for a, b in reversed(tabs_y):                           # left: tabs to the left, bottom to top
            pts += [(-k, rp + b + k), (-t - k, rp + b + k), (-t - k, rp + a - k), (-k, rp + a - k)]
        pts += arc(rp, rp, R, _m.pi, 1.5 * _m.pi)
        clean = []
        for p_ in pts:
            if not clean or abs(clean[-1][0] - p_[0]) > 1e-9 or abs(clean[-1][1] - p_[1]) > 1e-9:
                clean.append(p_)
        if abs(clean[0][0] - clean[-1][0]) < 1e-9 and abs(clean[0][1] - clean[-1][1]) < 1e-9:
            clean.pop()
        return clean

    # one wall strip: from the middle of the back, round two corners and one side, to the middle of the front
    half = Lx / 2.0
    L = 2 * half + 2 * La + Ly
    slot_s = [(a - half, b - half) for a, b in tabs_x if a >= half]                 # back, right half
    slot_s += [(half + La + a, half + La + b) for a, b in tabs_y]                   # the side
    base = half + 2 * La + Ly
    slot_s += [(base + Lx - b, base + Lx - a) for a, b in tabs_x if a >= half]       # front, right end to middle
    rows = [(H - 2 * t, H - t), (t, 2 * t)]                  # the bottom's tabs; the lid's or the rim's
    holes = [(a + k, y0 + k, b - k, y1 - k) for a, b in slot_s for y0, y1 in rows]
    strip_loops = _region_outline((-k, -k, L + k, H + k), holes)
    hinge = []
    margin = 2.0
    for z0 in (half, half + La + Ly):                                             # the two bends
        zone = [(z0 - 1.0, 0.0), (z0 + La + 1.0, 0.0), (z0 + La + 1.0, H), (z0 - 1.0, H), (z0 - 1.0, 0.0)]
        hinge += hinge_lines("straight", [zone], max(2.0, float(cut_len)), max(0.5, float(gap)),
                             max(0.3, float(spacing)), 90.0, margin)
    def rim_hole():
        """The opening of the rim: the plate's rounded rectangle, `rim` mm smaller all round."""
        rw = max(t + 2.0, min(float(rim), min(Wp, Dp) / 3.0))
        ri = max(1.0, rp - rw)
        x0, y0, x1, y1 = rw - k, rw - k, Wp - rw + k, Dp - rw + k
        pts = arc(x1 - ri, y0 + ri, ri - k, -_m.pi / 2, 0.0) + arc(x1 - ri, y1 - ri, ri - k, 0.0, _m.pi / 2) + \
            arc(x0 + ri, y1 - ri, ri - k, _m.pi / 2, _m.pi) + arc(x0 + ri, y0 + ri, ri - k, _m.pi, 1.5 * _m.pi)
        return pts
    parts = [("bottom", [plate()], None)]
    parts.append(("lid", [plate()], None) if lid else ("rim", [plate(), rim_hole()], None))
    parts += [("wall", strip_loops, hinge), ("wall", strip_loops, hinge)]
    # 3D preview: the plates t in from the wall's edges, the wall bent round them (its inner face along
    # the plates' outline)
    X, Y, Z = (1, 0, 0), (0, 1, 0), (0, 0, 1)
    for name, loops, _c in parts[:2]:
        z = t if name == "bottom" else H - 2 * t
        out.assembly.append({"name": names.get(name, name.capitalize()), "loops": [list(lp) for lp in loops],
                             "origin": (t, t, z), "u": X, "v": Y, "n": Z, "t": t})
    path, normals = [], []
    for cx, cy, a0 in ((Wp - rp, rp, -_m.pi / 2), (Wp - rp, Dp - rp, 0.0), (rp, Dp - rp, _m.pi / 2),
                       (rp, rp, _m.pi)):
        for i in range(13):
            a = a0 + (_m.pi / 2) * i / 12.0
            path.append((t + cx + rp * _m.cos(a), t + cy + rp * _m.sin(a), 0.0))
            normals.append((_m.cos(a), _m.sin(a), 0.0))
    # the two strips round the plates (their slots with them): strip 1 from the middle of the plates' first
    # straight side (half a side before the path's start), strip 2 after it; y of a strip from the top
    out.assembly.append({"kind": "band", "name": names.get("wall", "Wall"), "path": path, "out": normals,
                         "height": H, "t": t, "closed": True, "length": 2 * L,
                         "strips": [{"loops": [list(lp) for lp in strip_loops], "start": -half},
                                    {"loops": [list(lp) for lp in strip_loops], "start": L - half}]})
    shapes = []
    for name, loops, cuts in parts:
        xs_ = [p_[0] for lp in loops for p_ in lp]
        ys_ = [p_[1] for lp in loops for p_ in lp]
        x0_, y0_ = min(xs_), min(ys_)
        loops = [[(px - x0_, py - y0_) for px, py in lp] for lp in loops]
        cuts = [[(px - x0_, py - y0_) for px, py in c_] for c_ in cuts] if cuts else None
        shapes.append((name, loops, cuts, max(xs_) - x0_, max(ys_) - y0_))
    part_index = 0
    places = _pack_parts([(sh[3], sh[4]) for sh in shapes], bed, spacing_parts,
                         max(W, D) * 2 + spacing_parts + 1)
    n_sheets = max(p_[0] for p_ in places) if places else 1
    speed, power, passes = cut
    for (name, loops, cuts, w_, h_), (sheet, x, y, turned) in zip(shapes, places):
        layer = ""
        if turned:
            loops = [_turned(lp, h_) for lp in loops]
            cuts = [_turned(c_, h_) for c_ in cuts] if cuts else None
        label = names.get(name, name.capitalize())
        groups = _part_groups(sheet, n_sheets, sheet_name, part_index, label, len(loops) + (1 if cuts else 0))
        part_index += 1
        for lp in loops:
            out.items.append(_polygon_item([(px + x, py + y) for px, py in lp], 0, 0, "cut", label, layer))
            out.items[-1].group = groups
            out.items[-1].active = sheet == 1
        if cuts:
            item = _path_item([[(px + x, py + y) for px, py in c_] for c_ in cuts], 0, 0, "cut",
                              names.get("hinge", "Hinge"))
            item.layer = layer
            item.group = groups
            item.active = sheet == 1
            out.items.append(item)
    out.sheets = max(p_[0] for p_ in places) if places else 1
    _by_sheet(out)
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
