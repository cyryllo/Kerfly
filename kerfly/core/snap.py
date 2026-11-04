"""
Object snapping: find the nearest interesting point of other shapes.

Targets, in order of preference within the snap distance:
    "corner"   a corner of a path (vertex, also the ends of a line) or of an
               element's bounding box
    "centre"   the centre of an element's bounding box
    "middle"   the middle of a straight segment or of a bounding-box edge
    "edge"     the nearest point on a line or curve (curves are polylines)

Coordinates are whatever the caller uses (Kerfly's bed view uses scene mm).
No GUI toolkit is needed.

Copyright (C) 2026 Kerfly contributors
Licensed under the GNU General Public License v3 or later. See LICENSE.
"""
import math

CORNER, CENTRE, MIDDLE, EDGE = "corner", "centre", "middle", "edge"
ALIGNED = "aligned"              # same x and/or y as another corner (axis alignment)
_PREFERENCE = {CORNER: 0, CENTRE: 1, MIDDLE: 2}
MAX_POINTS_PER_SHAPE = 6000      # very detailed shapes (text) are thinned out


class SnapShape:
    """Snap targets of one shape: polylines plus its bounding box."""

    def __init__(self, polylines, box=None):
        """polylines: lists of (x, y); box: (xmin, ymin, xmax, ymax) or None
        to use the polylines' extent."""
        total = sum(len(p) for p in polylines)
        step = max(1, int(math.ceil(total / float(MAX_POINTS_PER_SHAPE))))
        self.points = []          # (x, y, kind)
        self.segments = []        # (x1, y1, x2, y2)
        for poly in polylines:
            pts = poly[::step] if step > 1 else list(poly)
            if step > 1 and poly and pts[-1] != poly[-1]:
                pts.append(poly[-1])
            for x, y in pts:
                self.points.append((x, y, CORNER))
            for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
                if (x1, y1) != (x2, y2):
                    self.segments.append((x1, y1, x2, y2))
                    if step == 1:                 # middles only for real straight segments
                        self.points.append(((x1 + x2) / 2.0, (y1 + y2) / 2.0, MIDDLE))
        if box is None:
            xs = [p[0] for p in self.points] or [0.0]
            ys = [p[1] for p in self.points] or [0.0]
            box = (min(xs), min(ys), max(xs), max(ys))
        x0, y0, x1, y1 = box
        self.box = box
        cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
        self.points += [(x0, y0, CORNER), (x1, y0, CORNER), (x1, y1, CORNER), (x0, y1, CORNER),
                        (cx, cy, CENTRE),
                        (cx, y0, MIDDLE), (x1, cy, MIDDLE), (cx, y1, MIDDLE), (x0, cy, MIDDLE)]
        self.segments += [(x0, y0, x1, y0), (x1, y0, x1, y1), (x1, y1, x0, y1), (x0, y1, x0, y0)]


def _nearest_on_segment(px, py, x1, y1, x2, y2):
    dx, dy = x2 - x1, y2 - y1
    length2 = dx * dx + dy * dy
    t = 0.0 if length2 == 0 else max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / length2))
    return x1 + t * dx, y1 + t * dy


def find_snap(x, y, shapes, tolerance):
    """Nearest target within tolerance: (x, y, kind) or None. Corners, centres
    and middles win over a plain point on an edge."""
    best = None                                  # (preference, distance, x, y, kind)
    for shape in shapes:
        x0, y0, x1, y1 = shape.box
        if x < x0 - tolerance or x > x1 + tolerance or y < y0 - tolerance or y > y1 + tolerance:
            continue
        for px, py, kind in shape.points:
            d = math.hypot(px - x, py - y)
            if d <= tolerance:
                key = (_PREFERENCE[kind], d)
                if best is None or key < best[:2]:
                    best = (key[0], d, px, py, kind)
    if best is not None:
        return best[2], best[3], best[4]
    edge = None
    for shape in shapes:
        x0, y0, x1, y1 = shape.box
        if x < x0 - tolerance or x > x1 + tolerance or y < y0 - tolerance or y > y1 + tolerance:
            continue
        for sx1, sy1, sx2, sy2 in shape.segments:
            nx, ny = _nearest_on_segment(x, y, sx1, sy1, sx2, sy2)
            d = math.hypot(nx - x, ny - y)
            if d <= tolerance and (edge is None or d < edge[0]):
                edge = (d, nx, ny)
    if edge is not None:
        return edge[1], edge[2], EDGE
    return None


def find_axis_snap(x, y, points, tolerance):
    """Line up with other corners: x and/or y moved onto the nearest point's
    x / y when within tolerance. Returns (x, y, guides) where guides is a list
    of (x1, y1, x2, y2) helper lines from the matched corners, or None."""
    best_x = best_y = None
    for px, py in points:
        dx, dy = abs(px - x), abs(py - y)
        if dx <= tolerance and (best_x is None or dx < best_x[0]):
            best_x = (dx, px, py)
        if dy <= tolerance and (best_y is None or dy < best_y[0]):
            best_y = (dy, px, py)
    if best_x is None and best_y is None:
        return None
    nx = best_x[1] if best_x else x
    ny = best_y[2] if best_y else y
    guides = []
    if best_x:
        guides.append((best_x[1], best_x[2], nx, ny))
    if best_y:
        guides.append((best_y[1], best_y[2], nx, ny))
    return nx, ny, guides


def snap_offset(reference_points, shapes, tolerance):
    """For moving a shape: the smallest (dx, dy, x, y, kind) that puts one of
    its reference points (corners, centre, middles) on a target, or None."""
    best = None
    for rx, ry in reference_points:
        hit = find_snap(rx, ry, shapes, tolerance)
        if hit is None or hit[2] == EDGE:
            continue                     # moving shapes snap to points, not along edges
        dx, dy = hit[0] - rx, hit[1] - ry
        d = math.hypot(dx, dy)
        if best is None or d < best[0]:
            best = (d, dx, dy, hit[0], hit[1], hit[2])
    return None if best is None else best[1:]
