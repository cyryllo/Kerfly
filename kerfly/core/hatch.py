"""
Hatch fill: closed outlines filled with parallel lines (vector engraving)
instead of a raster image. Holes are kept (even-odd rule, so letters like "O"
stay open).

Units are whatever the polygons use (Kerfly passes millimetres).

Copyright (C) 2026 Kerfly contributors
Licensed under the GNU General Public License v3 or later. See LICENSE.
"""
import math


def hatch_lines(polygons, spacing, angle_deg=0.0, cross=False):
    """Line segments [((x1, y1), (x2, y2)), ...] filling the closed polygons,
    every `spacing` units at `angle_deg`; cross adds a second set at +90
    degrees. Neighbouring lines run in opposite directions (zigzag order)."""
    if spacing <= 0:
        raise ValueError("hatch spacing must be positive")
    out = _one_direction(polygons, spacing, angle_deg)
    if cross:
        out += _one_direction(polygons, spacing, angle_deg + 90.0)
    return out


def _one_direction(polygons, spacing, angle_deg):
    a = math.radians(angle_deg)
    c, s = math.cos(a), math.sin(a)

    def rot(x, y):            # into the hatch frame: lines become horizontal
        return x * c + y * s, -x * s + y * c

    def unrot(x, y):
        return x * c - y * s, x * s + y * c
    edges = []
    ys = []
    for poly in polygons:
        pts = [rot(x, y) for x, y in poly]
        if len(pts) < 3:
            continue
        if pts[0] != pts[-1]:
            pts.append(pts[0])
        for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
            if y1 != y2:
                edges.append((x1, y1, x2, y2))
            ys += [y1, y2]
    if not edges:
        return []
    y0, y1 = min(ys), max(ys)
    # lines at the middle of each band, so a shape exactly n spacings tall gets n lines
    first = math.floor(y0 / spacing) * spacing + spacing / 2.0
    out = []
    k = 0
    y = first
    while y < y1:
        xs = []
        for ex1, ey1, ex2, ey2 in edges:
            lo, hi = (ey1, ey2) if ey1 < ey2 else (ey2, ey1)
            if lo <= y < hi:                      # half-open: a vertex is counted once
                xs.append(ex1 + (y - ey1) * (ex2 - ex1) / (ey2 - ey1))
        xs.sort()
        pairs = list(zip(xs[0::2], xs[1::2]))
        if k % 2:
            pairs = [(b, a_) for a_, b in reversed(pairs)]
        for xa, xb in pairs:
            if abs(xb - xa) > 1e-9:
                out.append((unrot(xa, y), unrot(xb, y)))
        k += 1
        y += spacing
    return out
