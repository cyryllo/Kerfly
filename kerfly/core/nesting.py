"""
Nesting: parts laid out on the laser's bed as tightly as their bounding
rectangles allow (MaxRects, best short side fit), turned by 90 degrees where
that helps, on as few sheets as fit; a sheet is always the laser's bed. Used
by the box generators and by Arrange → Nest on the bed (the selected
elements, a group as one part).

Copyright (C) 2026 Kerfly contributors
Licensed under the GNU General Public License v3 or later. See LICENSE.
"""
import math

from .layout import Unit, rotate_about, selection_bounds, units

MARGIN_MM = 1.0              # from the bed's edges


def pack(sizes, bed, spacing, turn=True):
    """Places parts (w, h) in mm on as few sheets of the bed (w, h in mm) as it can: [(sheet, x, y, turned)]
    in the order given, x, y of the top-left in mm from the bed's corner. Bigger parts first, each into the
    free space of the first sheet it fits (turned by 90 degrees when only that fits, or fits better, if
    turn), a new sheet when none has room; a part larger than the bed gets a sheet of its own."""
    bw, bh = (max(10.0, float(v) - 2.0) + spacing for v in bed)     # a little room to the bed's edges
    sheets = []                                                    # free rectangles of each sheet

    def find(free, w, h):
        best = None
        for fx, fy, fw, fh in free:
            for turned, (pw, ph) in ((False, (w, h)), (True, (h, w)))[:2 if turn else 1]:
                if pw <= fw + 1e-9 and ph <= fh + 1e-9:
                    score = (min(fw - pw, fh - ph), fy, fx, turned)
                    if best is None or score < best[0]:
                        best = (score, fx, fy, turned, pw, ph)
        return best

    def place(free, x, y, w, h):
        out = []
        for fx, fy, fw, fh in free:
            if x >= fx + fw or x + w <= fx or y >= fy + fh or y + h <= fy:
                out.append((fx, fy, fw, fh))
                continue
            if x > fx:
                out.append((fx, fy, x - fx, fh))
            if x + w < fx + fw:
                out.append((x + w, fy, fx + fw - x - w, fh))
            if y > fy:
                out.append((fx, fy, fw, y - fy))
            if y + h < fy + fh:
                out.append((fx, y + h, fw, fy + fh - y - h))
        pruned = []
        for i, a in enumerate(out):
            inside = any(j != i and b[0] <= a[0] and b[1] <= a[1] and a[0] + a[2] <= b[0] + b[2]
                         and a[1] + a[3] <= b[1] + b[3] and (b != a or j < i) for j, b in enumerate(out))
            if not inside and a[2] > 1e-6 and a[3] > 1e-6:
                pruned.append(a)
        free[:] = pruned
    order = sorted(range(len(sizes)), key=lambda i: (-max(sizes[i]), -sizes[i][0] * sizes[i][1], i))
    result = [None] * len(sizes)
    for i in order:
        w, h = sizes[i][0] + spacing, sizes[i][1] + spacing
        for n, free in enumerate(sheets):
            found = find(free, w, h)
            if found:
                _score, x, y, turned, pw, ph = found
                place(free, x, y, pw, ph)
                result[i] = (n + 1, x, y, turned)
                break
        else:
            free = [(0.0, 0.0, bw, bh)]
            sheets.append(free)
            found = find(free, w, h)
            if found:
                _score, x, y, turned, pw, ph = found
                place(free, x, y, pw, ph)
                result[i] = (len(sheets), x, y, turned)
            else:                                                  # larger than the bed: on its own sheet
                free[:] = []
                result[i] = (len(sheets), 0.0, 0.0, False)
    return result


def nest(elements, bed_w, bed_h, gap_mm=2.0, turn=True):
    """Lay the elements out on the bed (inches, the elements' coordinates: x from home, y <= 0): each group
    (its outer group) moves as one part. Returns [(the part's elements, sheet)] and the number of sheets."""
    parts = [u.elements if isinstance(u, Unit) else [u] for u in units(elements)]
    sizes = []
    for els in parts:
        x0, x1, y0, y1 = selection_bounds(els)
        sizes.append(((x1 - x0) * 25.4, (y1 - y0) * 25.4))
    places = pack(sizes, (bed_w * 25.4 - 2 * MARGIN_MM + 2.0, bed_h * 25.4 - 2 * MARGIN_MM + 2.0),
                  float(gap_mm), turn)
    out = []
    for els, (sheet, x, y, turned) in zip(parts, places):
        if turned:
            x0, x1, y0, y1 = selection_bounds(els)
            rotate_about(els, -90, (x0 + x1) / 2.0, (y0 + y1) / 2.0)
        x0, x1, y0, y1 = selection_bounds(els)
        dx = (x + MARGIN_MM) / 25.4 - x0
        dy = -(y + MARGIN_MM) / 25.4 - y1
        for e in els:
            e.x += dx
            e.y += dy
        out.append((els, sheet))
    return out, max((p[0] for p in places), default=1)


# ---------------------------------------------------------------------------------------------------------------
# By the real outlines (step 2): parts in each other's gaps and holes, with sparrow (spyrrow on pip: Python
# bindings of the sparrow nesting library, MIT; its geometry engine jagua-rs, MPL-2.0). sparrow packs a strip of
# fixed height as short as it can: the strip is the bed's height; what lies within the bed's width is a sheet,
# the rest is packed again for the next sheet. sparrow knows no holes in a part: each hole is joined to the
# outside by a slit too thin for any part, so the part becomes one outline with its holes open to parts.

CLIP = 1000.0                # Clipper units per mm
SIMPLIFY_MM = 0.1            # outlines simplified this much (outwards only: never closer than the gap)
SLIT_MM = 0.05               # the slit that opens a hole to the outside
CURVE_MM = 0.1               # round corners of the gap: points this close to the arc
FIT = 0.995                  # sparrow wants a part a little smaller than the strip


def outlines_available():
    """Nesting by outlines needs spyrrow and pyclipper (both installed with Kerfly)."""
    try:
        import pyclipper  # noqa: F401
        import spyrrow  # noqa: F401
    except ImportError:
        return False
    return True


def _part_paths(els):
    """The material of a part on the bed, in Clipper units (mm x CLIP, y up): (areas, lines). Only cut lines
    make a hole (the closed cut paths of all its elements together, even-odd: a cut inside a cut is a hole);
    engraved closed paths, pictures (their rectangles) and an element with nothing else (its rectangle) are
    filled; open lines stay lines."""
    from .explode import vector_loops
    import pyclipper
    cuts, fills, lines = [], [], []

    def clip(f, pts):
        out = []
        for x, y in pts:
            bx, by = f(x, y)
            p = (int(round(bx * 25.4 * CLIP)), int(round(by * 25.4 * CLIP)))
            if not out or p != out[-1]:
                out.append(p)
        return out

    for e in els:
        f = e.transform()
        found = False
        for kind, pts, is_closed in vector_loops(e.design):
            path = clip(f, pts)
            if is_closed and len(path) >= 3:
                (cuts if kind == "cut" else fills).append(path)
                found = True
            elif len(path) >= 2:
                lines.append(path)
                found = True
        loop, run = None, []
        for row in e.design.gcode.ecoords:                     # G-code moves: lines
            if row[2] != loop:
                if len(run) >= 2:
                    lines.append(clip(f, run))
                    found = True
                loop, run = row[2], []
            run.append((row[0], row[1]))
        if len(run) >= 2:
            lines.append(clip(f, run))
            found = True
        if e.design.raster.image is not None or not found:
            x0, x1, y0, y1 = e.design.bounds
            fills.append(clip(f, [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]))
    areas = []
    for paths, rule in ((cuts, pyclipper.PFT_EVENODD), (fills, pyclipper.PFT_NONZERO)):
        pc = pyclipper.Pyclipper()
        added = False
        for path in paths:
            if rule == pyclipper.PFT_NONZERO and pyclipper.Area(path) < 0:
                path = list(reversed(path))                     # each engraved outline filled, whatever its turn
            try:
                pc.AddPath(path, pyclipper.PT_SUBJECT, True)
                added = True
            except pyclipper.ClipperException:                  # a loop without area
                pass
        if added:
            try:
                areas.extend(pc.Execute(pyclipper.CT_UNION, rule, rule))
            except pyclipper.ClipperException:
                pass
    return areas, lines


def _simplify(ring, tol):
    """Douglas-Peucker on a closed ring of points (tol in its units)."""
    if len(ring) <= 4:
        return list(ring)
    # split at the point farthest from the first one, simplify both halves as open chains
    far = max(range(len(ring)), key=lambda i: (ring[i][0] - ring[0][0]) ** 2 + (ring[i][1] - ring[0][1]) ** 2)

    def chain(pts):
        keep = [False] * len(pts)
        keep[0] = keep[-1] = True
        stack = [(0, len(pts) - 1)]
        while stack:
            a, b = stack.pop()
            (ax, ay), (bx, by) = pts[a], pts[b]
            dx, dy = bx - ax, by - ay
            length = math.hypot(dx, dy)
            best, index = -1.0, None
            for i in range(a + 1, b):
                px, py = pts[i]
                d = abs(dy * (px - ax) - dx * (py - ay)) / length if length else math.hypot(px - ax, py - ay)
                if d > best:
                    best, index = d, i
            if index is not None and best > tol:
                keep[index] = True
                stack.extend(((a, index), (index, b)))
        return [p for p, k in zip(pts, keep) if k]
    first = chain(ring[:far + 1])
    second = chain(ring[far:] + [ring[0]])
    return first[:-1] + second[:-1]


def part_outline(els, gap_mm):
    """The outline a part takes on the bed, the gap around it included: [(x, y)] in mm (y up), one ring (its
    empty holes opened to the outside by a thin slit), or None when it has no area. A part of separate pieces
    gets their convex hull."""
    import pyclipper
    areas, lines = _part_paths(els)
    grow = max(0.0, float(gap_mm)) / 2.0 + SIMPLIFY_MM          # simplified afterwards by SIMPLIFY_MM inwards
    pco = pyclipper.PyclipperOffset(2.0, CURVE_MM * CLIP)
    if areas:
        pco.AddPaths(areas, pyclipper.JT_ROUND, pyclipper.ET_CLOSEDPOLYGON)
    for line in lines:
        pco.AddPath(line, pyclipper.JT_ROUND, pyclipper.ET_OPENROUND)
    try:
        grown = pco.Execute(grow * CLIP)
        pc = pyclipper.Pyclipper()
        pc.AddPaths(grown, pyclipper.PT_SUBJECT, True)
        tree = pc.Execute2(pyclipper.CT_UNION, pyclipper.PFT_NONZERO, pyclipper.PFT_NONZERO)
    except pyclipper.ClipperException:
        return None
    outers = tree.Childs
    if not outers:
        return None
    tol = SIMPLIFY_MM * CLIP
    if len(outers) > 1:                                         # separate pieces: their convex hull
        return [(x / CLIP, y / CLIP) for x, y in _hull([tuple(p) for o in outers for p in o.Contour])]
    outer = outers[0]
    ring = _simplify(outer.Contour, tol)
    holes = [_simplify(h.Contour, tol) for h in outer.Childs if not h.Childs and len(h.Contour) >= 3]
    holes = [h for h in holes if len(h) >= 3 and abs(pyclipper.Area(h)) > (10 * CLIP) ** 2]   # 10 x 10 mm and more
    if holes:
        low = min(y for _x, y in ring) - CLIP
        slits = []
        for h in holes:
            hx, hy = min(h, key=lambda p: (p[1], p[0]))
            w = SLIT_MM * CLIP / 2.0
            slits.append([(hx - w, low), (hx + w, low), (hx + w, hy + 2 * w), (hx - w, hy + 2 * w)])
        pc = pyclipper.Pyclipper()
        pc.AddPath(ring, pyclipper.PT_SUBJECT, True)
        pc.AddPaths(holes, pyclipper.PT_SUBJECT, True)
        pc.AddPaths(slits, pyclipper.PT_CLIP, True)
        try:
            opened = pc.Execute(pyclipper.CT_DIFFERENCE, pyclipper.PFT_EVENODD, pyclipper.PFT_NONZERO)
        except pyclipper.ClipperException:
            opened = []
        if len(opened) == 1:
            ring = opened[0]
    if pyclipper.Area(ring) < 0:
        ring = list(reversed(ring))
    return [(x / CLIP, y / CLIP) for x, y in ring]


def _hull(points):
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


def _turned_size(ring, degrees):
    a = math.radians(degrees)
    c, s = math.cos(a), math.sin(a)
    xs = [x * c - y * s for x, y in ring]
    ys = [x * s + y * c for x, y in ring]
    return max(xs) - min(xs), max(ys) - min(ys), min(xs), min(ys)


def plan_outlines(rings, bed_mm, turn=True, seconds=10, progress=None, stop=None):
    """Lays parts out by their outlines (rings from part_outline, mm, y up) on sheets of the bed (w, h in mm,
    the margin already taken off): [(sheet, degrees, (cx, cy), (tx, ty))] in the order given: the part turned
    by degrees (counter-clockwise) about (cx, cy), then (cx, cy) moved to (tx, ty) (mm from the bed area's
    lower left corner); None for a ring that is None. A part that fits in no way goes on a sheet of its own at
    the corner, as it is. progress(sheet) before each sheet's search; stop() true before a sheet: None (nothing
    planned)."""
    import spyrrow
    bw, bh = (float(v) for v in bed_mm)
    angles = [0.0, 90.0, 180.0, 270.0] if turn else [0.0]
    result = [None] * len(rings)
    fitting, sheet = [], 0
    for i, ring in enumerate(rings):
        if ring is None:
            continue
        xs, ys = [p[0] for p in ring], [p[1] for p in ring]
        centre = ((min(xs) + max(xs)) / 2.0, (min(ys) + max(ys)) / 2.0)
        if any(w <= bw * FIT and h <= bh * FIT for w, h, _x, _y in (_turned_size(ring, a) for a in angles)):
            fitting.append((i, centre))
        else:                                                   # larger than the bed: alone, as it is
            sheet += 1
            result[i] = (sheet, 0.0, centre, ((max(xs) - min(xs)) / 2.0, bh - (max(ys) - min(ys)) / 2.0))
    while fitting:
        if stop is not None and stop():
            return None
        sheet += 1
        if progress is not None:
            progress(sheet)
        items = [spyrrow.Item(str(n), [(x - c[0], y - c[1]) for x, y in rings[i]], 1, angles)
                 for n, (i, c) in enumerate(fitting)]
        config = spyrrow.StripPackingConfig(early_termination=True, total_computation_time=max(1, int(seconds)),
                                            seed=1)
        try:
            solution = spyrrow.StripPackingInstance("kerfly", bh, items).solve(config)
        except BaseException as e:                              # (a panic of the library is no Exception)
            if isinstance(e, (KeyboardInterrupt, SystemExit)):
                raise
            raise RuntimeError("sparrow: %s" % e) from None
        placed = {}
        for p in solution.placed_items:
            n = int(p.id)
            i, c = fitting[n]
            w, h, x0, _y0 = _turned_size([(x - c[0], y - c[1]) for x, y in rings[i]], p.rotation)
            right = p.translation[0] + x0 + w
            placed[n] = (p.rotation, p.translation, right)
        here = [n for n, (_r, _t, right) in placed.items() if right <= bw + 1e-6]
        if not here:                                            # (cannot be: each fits alone) the first alone
            n = min(placed)
            i, c = fitting[n]
            r = placed[n][0]
            _w, _h, x0, y0 = _turned_size([(x - c[0], y - c[1]) for x, y in rings[i]], r)
            placed[n], here = (r, (-x0, -y0), 0.0), [n]
        for n in here:
            i, c = fitting[n]
            r, t, _right = placed[n]
            result[i] = (sheet, float(r), c, (float(t[0]), float(t[1])))
        fitting = [f for n, f in enumerate(fitting) if n not in set(here)]
    return result


def nest_outlines(elements, bed_w, bed_h, gap_mm=2.0, turn=True, seconds=10, progress=None, stop=None):
    """nest() by the parts' real outlines: parts in each other's gaps and holes. Same result: [(the part's
    elements, sheet)] and the number of sheets; None when stopped (nothing moved)."""
    parts, plan = plan_nest_outlines(elements, bed_w, bed_h, gap_mm, turn, seconds, progress, stop)
    return None if plan is None else apply_outline_plan(parts, plan, bed_h)


def plan_nest_outlines(elements, bed_w, bed_h, gap_mm=2.0, turn=True, seconds=10, progress=None, stop=None):
    """The planning half of nest_outlines (nothing moved: it may run in a thread): (parts, plan)."""
    parts = [u.elements if isinstance(u, Unit) else [u] for u in units(elements)]
    rings = [part_outline(els, gap_mm) for els in parts]
    area = (bed_w * 25.4 - 2 * MARGIN_MM, bed_h * 25.4 - 2 * MARGIN_MM)
    return parts, plan_outlines(rings, area, turn, seconds, progress, stop)


def apply_outline_plan(parts, plan, bed_h):
    """Moves the parts as plan_outlines planned (bed_h in inches); a part without an outline goes on the
    first sheet as it is. Returns [(the part's elements, sheet)] and the number of sheets."""
    out = []
    for els, step in zip(parts, plan):
        if step is None:
            out.append((els, 1))
            continue
        sheet, degrees, (cx, cy), (tx, ty) = step
        if degrees % 360:
            rotate_about(els, degrees, cx / 25.4, cy / 25.4)
        # the bed area's lower left corner: MARGIN_MM in from the bed's left and lower edges (y up, <= 0)
        dx = (MARGIN_MM + tx - cx) / 25.4
        dy = (MARGIN_MM + ty - cy) / 25.4 - bed_h
        for e in els:
            e.x += dx
            e.y += dy
        out.append((els, sheet))
    return out, max((s for _e, s in out), default=1)
