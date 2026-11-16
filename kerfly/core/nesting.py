"""
Nesting: parts laid out on the laser's bed as tightly as their bounding
rectangles allow (MaxRects, best short side fit), turned by 90 degrees where
that helps, on as few sheets as fit; a sheet is always the laser's bed. Used
by the box generators and by Arrange → Nest on the bed (the selected
elements, a group as one part).

Copyright (C) 2026 Kerfly contributors
Licensed under the GNU General Public License v3 or later. See LICENSE.
"""
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
