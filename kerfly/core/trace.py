"""
Picture to vector outlines (Trace): the dark areas of a picture become closed
paths that can be cut, outlined, filled with a pattern or edited node by node,
like LightBurn's Trace Image.

1. the picture is made black and white at a threshold (optionally inverted);
2. the borders between black and white pixels are followed into closed loops
   (outer edges and holes; diagonal touches stay apart);
3. specks smaller than a given area are dropped;
4. each loop is simplified (Douglas-Peucker) to a polygon;
5. with smoothing, the polygon becomes Bezier curves through the middles of its
   sides, keeping sharp corners sharp (as potrace does, in a simple form).

No extra library is needed (Pillow only).

Copyright (C) 2026 Kerfly contributors
Licensed under the GNU General Public License v3 or later. See LICENSE.
"""
import math

MAX_SIDE = 1600                 # larger pictures are traced at this size (and scaled back)


def _no_progress(_message):
    pass


def bitmap(image, threshold=128, invert=False):
    """(width, height, rows): rows of booleans, True = dark (traced)."""
    grey = image.convert("L")
    w, h = grey.size
    data = grey.tobytes()
    rows = []
    for y in range(h):
        line = data[y * w:(y + 1) * w]
        rows.append([(v < threshold) != invert for v in line])
    return w, h, rows


def _loops(w, h, rows):
    """Closed loops of pixel corners along the borders of the dark areas: dark on the left
    when walking (outer edges counter-clockwise on screen, holes the other way)."""
    def dark(x, y):
        return 0 <= x < w and 0 <= y < h and rows[y][x]
    nxt = {}                                    # start corner -> list of end corners
    for y in range(h):
        row = rows[y]
        up = rows[y - 1] if y > 0 else None
        down = rows[y + 1] if y + 1 < h else None
        for x in range(w):
            if not row[x]:
                continue
            # each border side of a dark pixel, directed so the pixel is on the left (y down)
            if up is None or not up[x]:
                nxt.setdefault((x + 1, y), []).append((x, y))
            if down is None or not down[x]:
                nxt.setdefault((x, y + 1), []).append((x + 1, y + 1))
            if x == 0 or not row[x - 1]:
                nxt.setdefault((x, y), []).append((x, y + 1))
            if x + 1 == w or not row[x + 1]:
                nxt.setdefault((x + 1, y + 1), []).append((x + 1, y))
    loops = []
    while nxt:
        start = next(iter(nxt))
        loop = [start]
        prev = None
        cur = start
        while True:
            ends = nxt.get(cur)
            if not ends:
                break
            if len(ends) == 1:
                end = ends.pop()
            else:
                # a corner where two dark pixels touch diagonally: turn so they stay apart
                dx_in = (cur[0] - prev[0], cur[1] - prev[1]) if prev else (1, 0)
                right = (-dx_in[1], dx_in[0])
                end = next((e for e in ends if (e[0] - cur[0], e[1] - cur[1]) == right), ends[0])
                ends.remove(end)
            if not ends:
                del nxt[cur]
            prev, cur = cur, end
            if cur == start:
                break
            loop.append(cur)
        if len(loop) >= 4:
            loops.append(loop)
    return loops


def _area(poly):
    a = 0.0
    for (x1, y1), (x2, y2) in zip(poly, poly[1:] + poly[:1]):
        a += x1 * y2 - x2 * y1
    return a / 2.0


def _simplify(points, tol):
    """Douglas-Peucker on a closed loop (the first point is kept as a corner of the result)."""
    if len(points) < 4:
        return points
    # start from the point farthest from the first one, so the loop is split well
    far = max(range(len(points)), key=lambda i: (points[i][0] - points[0][0]) ** 2 + (points[i][1] - points[0][1]) ** 2)

    def dp(pts):
        if len(pts) < 3:
            return pts
        (x1, y1), (x2, y2) = pts[0], pts[-1]
        dx, dy = x2 - x1, y2 - y1
        length = math.hypot(dx, dy) or 1e-12
        best, index = -1.0, 0
        for i in range(1, len(pts) - 1):
            d = abs(dy * pts[i][0] - dx * pts[i][1] + x2 * y1 - y2 * x1) / length
            if d > best:
                best, index = d, i
        if best <= tol:
            return [pts[0], pts[-1]]
        left = dp(pts[:index + 1])
        return left[:-1] + dp(pts[index:])
    a = dp(points[:far + 1])
    b = dp(points[far:] + points[:1])
    return a[:-1] + b[:-1]


def _smooth_nodes(poly, corner_deg):
    """Curve nodes (kerfly.core.curves) through the middles of the polygon's sides; a vertex whose
    turn is sharper than corner_deg stays a sharp corner."""
    n = len(poly)
    nodes = []
    for i in range(n):
        p0, p1, p2 = poly[i - 1], poly[i], poly[(i + 1) % n]
        a = (p1[0] - p0[0], p1[1] - p0[1])
        b = (p2[0] - p1[0], p2[1] - p1[1])
        la, lb = math.hypot(*a) or 1e-12, math.hypot(*b) or 1e-12
        cos_turn = max(-1.0, min(1.0, (a[0] * b[0] + a[1] * b[1]) / (la * lb)))
        turn = math.degrees(math.acos(cos_turn))
        m_in = ((p0[0] + p1[0]) / 2.0, (p0[1] + p1[1]) / 2.0)
        m_out = ((p1[0] + p2[0]) / 2.0, (p1[1] + p2[1]) / 2.0)
        if turn > corner_deg:
            # sharp: straight to the corner and away from it
            nodes.append([m_in[0], m_in[1], None, None, None, None])
            nodes.append([p1[0], p1[1], None, None, None, None])
        else:
            # smooth: a curve from the middle of one side to the middle of the next, pulled to the vertex
            k = 2.0 / 3.0
            h_out = (m_in[0] + (p1[0] - m_in[0]) * k, m_in[1] + (p1[1] - m_in[1]) * k)
            h_in = (m_out[0] + (p1[0] - m_out[0]) * k, m_out[1] + (p1[1] - m_out[1]) * k)
            nodes.append([m_in[0], m_in[1], None, None, h_out[0], h_out[1]])
            nodes.append([m_out[0], m_out[1], h_in[0], h_in[1], None, None])
    # neighbouring nodes at the same place (the middle of a side, from both of its ends): one node
    merged = []
    for nd in nodes:
        if merged and abs(merged[-1][0] - nd[0]) < 1e-9 and abs(merged[-1][1] - nd[1]) < 1e-9:
            last = merged[-1]
            if nd[2] is not None:
                last[2], last[3] = nd[2], nd[3]
            if nd[4] is not None:
                last[4], last[5] = nd[4], nd[5]
            continue
        merged.append(list(nd))
    if len(merged) > 1 and abs(merged[0][0] - merged[-1][0]) < 1e-9 and abs(merged[0][1] - merged[-1][1]) < 1e-9:
        last = merged.pop()
        if last[2] is not None:
            merged[0][2], merged[0][3] = last[2], last[3]
        if last[4] is not None:
            merged[0][4], merged[0][5] = last[4], last[5]
    return merged


def trace(image, threshold=128, invert=False, specks=4, detail=1.0, smooth=True, corner_deg=60.0,
          progress=_no_progress):
    """Closed paths of the dark areas of a picture, in pixels of the picture (y down):
    a list of subpaths in kerfly.core.curves form. specks: smallest area kept (pixels);
    detail: largest distance (pixels) of the simplified outline from the pixel border."""
    scale = 1.0
    w, h = image.size
    if max(w, h) > MAX_SIDE:
        scale = MAX_SIDE / float(max(w, h))
        image = image.resize((max(1, int(round(w * scale))), max(1, int(round(h * scale)))))
    progress("Trace: black and white")
    bw, bh, rows = bitmap(image, threshold, invert)
    progress("Trace: following the edges")
    loops = _loops(bw, bh, rows)
    progress("Trace: smoothing %d outlines" % len(loops))
    out = []
    min_area = max(0.0, float(specks)) * scale * scale
    for loop in loops:
        if abs(_area(loop)) < max(min_area, 0.5):
            continue
        poly = _simplify(loop, max(0.3, float(detail)))
        if len(poly) < 3:
            continue
        if smooth:
            nodes = _smooth_nodes(poly, corner_deg)
        else:
            nodes = [[x, y, None, None, None, None] for x, y in poly]
        k = 1.0 / scale
        for nd in nodes:
            for i in (0, 1, 2, 3, 4, 5):
                if nd[i] is not None:
                    nd[i] *= k
        out.append({"closed": True, "nodes": nodes})
    return out
