"""
Offsetting closed outlines: the Offset command, kerf compensation of cut
layers and the concentric fill pattern.

Closed outlines are first joined even-odd (so a hole inside a part is known
as a hole), then moved out by a distance: the outside of a part grows and
its holes shrink; a negative distance does the opposite. Uses pyclipper
(installed with Kerfly; optional when running from source).

Copyright (C) 2026 Kerfly contributors
Licensed under the GNU General Public License v3 or later. See LICENSE.
"""
try:
    import pyclipper
except ImportError:                         # optional library
    pyclipper = None

SCALE = 10000.0                             # units -> integers for Clipper (0.1 µm in mm)
JOINS = ("round", "miter")


def available():
    return pyclipper is not None


def _closed(polys):
    out = []
    for p in polys:
        pts = [(float(x), float(y)) for x, y in p]
        if len(pts) > 2 and abs(pts[0][0] - pts[-1][0]) < 1e-9 and abs(pts[0][1] - pts[-1][1]) < 1e-9:
            pts = pts[:-1]
        if len(pts) >= 3:
            out.append(pts)
    return out


def offset_polygons(polys, distance, join="round", tolerance=0.01):
    """Closed polylines `polys` (first point repeated or not) moved out by
    `distance` (negative: in), holes the other way. join: "round" or "miter"
    (sharp corners). tolerance: how closely round corners follow the arc.
    Returns closed polylines with the first point repeated at the end."""
    if pyclipper is None:
        raise RuntimeError("offsetting needs the pyclipper library")
    rings = [[(int(round(x * SCALE)), int(round(y * SCALE))) for x, y in p] for p in _closed(polys)]
    if not rings:
        return []
    clip = pyclipper.Pyclipper()
    clip.AddPaths(rings, pyclipper.PT_SUBJECT, True)
    joined = clip.Execute(pyclipper.CT_UNION, pyclipper.PFT_EVENODD, pyclipper.PFT_EVENODD)
    if abs(distance) < 1e-12:
        result = joined
    else:
        off = pyclipper.PyclipperOffset()
        off.ArcTolerance = max(1.0, tolerance * SCALE)
        off.MiterLimit = 4.0
        jt = pyclipper.JT_MITER if join == "miter" else pyclipper.JT_ROUND
        off.AddPaths(joined, jt, pyclipper.ET_CLOSEDPOLYGON)
        result = off.Execute(distance * SCALE)
    out = []
    for ring in result:
        if len(ring) < 3:
            continue
        pts = [(x / SCALE, y / SCALE) for x, y in ring]
        out.append(pts + [pts[0]])
    return out


def concentric_rings(polys, spacing, margin=0.0, tolerance=0.01, limit=2000):
    """Rings following the outline inwards, one every `spacing`, the first
    `margin` + half a spacing inside it (the concentric fill pattern)."""
    if spacing <= 0:
        raise ValueError("spacing must be positive")
    rings = []
    k = 0
    while k < limit:
        step = offset_polygons(polys, -(margin + (k + 0.5) * spacing), "round", tolerance)
        if not step:
            break
        rings += step
        k += 1
    return rings


def offset_ecoord_loops(rows, distance_in, join="round"):
    """Kerf compensation of a design part (ECoord rows [x, y, loop] in inches):
    closed loops are offset by distance_in (inches), open lines are kept.
    Returns new rows; loop numbers start after the kept open lines."""
    loops = {}
    order = []
    for x, y, loop in rows:
        if loop not in loops:
            loops[loop] = []
            order.append(loop)
        loops[loop].append((x, y))
    closed, kept = [], []
    for loop in order:
        pts = loops[loop]
        if len(pts) > 3 and abs(pts[0][0] - pts[-1][0]) < 1e-7 and abs(pts[0][1] - pts[-1][1]) < 1e-7:
            closed.append(pts)
        else:
            kept.append(pts)
    out = []
    n = 0
    for pts in kept:
        n += 1
        out += [[x, y, n] for x, y in pts]
    for ring in offset_polygons(closed, distance_in, join, tolerance=0.0004):
        n += 1
        out += [[x, y, n] for x, y in ring]
    return out
