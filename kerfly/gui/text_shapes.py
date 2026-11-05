"""
Text to outlines using the fonts installed on the system (through Qt).

Copyright (C) 2026 Kerfly contributors
Licensed under the GNU General Public License v3 or later. See LICENSE.
"""
import math

from PySide6.QtCore import QPointF
from PySide6.QtGui import QFont, QFontMetricsF, QPainterPath

REFERENCE_PX = 1000      # outlines are made at this size, then scaled (smooth small text)


def text_outlines(text, family, size_mm, bold=False, italic=False):
    """Closed polylines (mm, y down) of the text outlines; size_mm is the font
    em height. Several lines are separated by newlines."""
    font = QFont(family)
    font.setPixelSize(REFERENCE_PX)
    font.setBold(bold)
    font.setItalic(italic)
    metrics = QFontMetricsF(font)
    path = QPainterPath()
    y = metrics.ascent()
    for line in (text or "").split("\n"):
        path.addText(QPointF(0, y), font, line)
        y += metrics.lineSpacing()
    k = size_mm / float(REFERENCE_PX)
    polys = []
    for poly in path.toSubpathPolygons():
        pts = [(p.x() * k, p.y() * k) for p in poly]
        if len(pts) >= 2 and pts[0] == pts[-1]:
            pts = pts[:-1]
        if len(pts) >= 3:
            polys.append(pts)
    return polys


def _path_walker(points):
    """(length, at(s)) for a polyline: at(s) gives the point and the direction
    (radians, y down) at distance s from the start; before the start and past
    the end the line is continued straight."""
    pts = [(float(x), float(y)) for x, y in points]
    pts = [p for i, p in enumerate(pts) if i == 0 or p != pts[i - 1]]
    segs = []
    total = 0.0
    for a, b in zip(pts, pts[1:]):
        length = math.hypot(b[0] - a[0], b[1] - a[1])
        segs.append((total, length, a, b))
        total += length

    def at(s):
        if not segs:
            return pts[0] if pts else (0.0, 0.0), 0.0
        if s <= 0:
            start, length, a, b = segs[0]
        elif s >= total:
            start, length, a, b = segs[-1]
        else:
            lo, hi = 0, len(segs) - 1                  # the segment holding s
            while lo < hi:
                mid = (lo + hi + 1) // 2
                if segs[mid][0] <= s:
                    lo = mid
                else:
                    hi = mid - 1
            start, length, a, b = segs[lo]
        angle = math.atan2(b[1] - a[1], b[0] - a[0])
        t = s - start
        return (a[0] + math.cos(angle) * t, a[1] + math.sin(angle) * t), angle
    return total, at


def path_text_outlines(text, family, size_mm, bold, italic, path, offset=0.0, flip=False):
    """Closed polylines (mm, y down) of the text set along the polyline `path`:
    every letter stands on the path at its place (with the font's kerning),
    turned along it, starting `offset` mm from the start of the path. flip
    runs the text the other way along the same stretch of the path, so it
    stands on the other side of the line in the same place."""
    font = QFont(family)
    font.setPixelSize(REFERENCE_PX)
    font.setBold(bold)
    font.setItalic(italic)
    metrics = QFontMetricsF(font)
    k = size_mm / float(REFERENCE_PX)
    line = (text or "").replace("\n", " ")
    if flip:
        total, _at = _path_walker(path)
        path = list(reversed(path))
        offset = total - offset - metrics.horizontalAdvance(line) * k
    _length, at = _path_walker(path)
    polys = []
    for i, ch in enumerate(line):
        x0 = metrics.horizontalAdvance(line[:i])             # includes kerning with the letters before
        w = metrics.horizontalAdvance(line[:i + 1]) - x0
        if ch.isspace():
            continue
        (px, py), angle = at(offset + (x0 + w / 2.0) * k)
        c, s_ = math.cos(angle), math.sin(angle)
        glyph = QPainterPath()
        glyph.addText(QPointF(-w / 2.0, 0.0), font, ch)      # centred on its place, baseline on the path
        for poly in glyph.toSubpathPolygons():
            pts = []
            for q in poly:
                u, v = q.x() * k, q.y() * k
                pts.append((px + u * c - v * s_, py + u * s_ + v * c))
            if len(pts) >= 2 and pts[0] == pts[-1]:
                pts = pts[:-1]
            if len(pts) >= 3:
                polys.append(pts)
    return polys


def update_text_spec(spec):
    """Recompute a text ShapeSpec's outlines and size after its text or font changed.
    Text on a path: the outlines and the path are moved together so the outlines
    start at (0, 0); the caller moves the element by the same amount (the change
    of text_path[0]) so the text stays where it is on the bed."""
    if spec.text_path:
        spec.text_outlines = path_text_outlines(spec.text, spec.font_family, spec.font_size, spec.bold,
                                                spec.italic, spec.text_path, spec.text_path_offset,
                                                spec.text_path_flip)
        xs = [x for p in spec.text_outlines for x, _ in p]
        ys = [y for p in spec.text_outlines for _, y in p]
        if xs:
            mx, my = min(xs), min(ys)
            spec.text_outlines = [[(x - mx, y - my) for x, y in p] for p in spec.text_outlines]
            spec.text_path = [(x - mx, y - my) for x, y in spec.text_path]
    else:
        spec.text_outlines = text_outlines(spec.text, spec.font_family, spec.font_size, spec.bold, spec.italic)
    xs = [x for p in spec.text_outlines for x, _ in p]
    ys = [y for p in spec.text_outlines for _, y in p]
    spec.width = (max(xs) - min(xs)) if xs else 0.0
    spec.height = (max(ys) - min(ys)) if ys else 0.0
    return spec


def text_length(spec):
    """Length of the text (mm) along its line, at its font and size."""
    font = QFont(spec.font_family)
    font.setPixelSize(REFERENCE_PX)
    font.setBold(spec.bold)
    font.setItalic(spec.italic)
    return QFontMetricsF(font).horizontalAdvance((spec.text or "").replace("\n", " ")) \
        * spec.font_size / float(REFERENCE_PX)


def prepare_path(points, closed, text_len):
    """A guide path for text, and the offset to start at: an open path gets
    the text in its middle; a closed one (circle, ellipse, ...) runs clockwise
    with the text centred at its top."""
    pts = [(float(x), float(y)) for x, y in points]
    total, at = _path_walker(pts)
    if not closed or len(pts) < 4:
        return pts, max(0.0, (total - text_len) / 2.0)
    if pts[0] == pts[-1]:
        pts = pts[:-1]
    area = sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(pts, pts[1:] + pts[:1]))
    if area < 0:                                       # y down: positive area runs clockwise on screen
        pts.reverse()
    ring = pts + [pts[0]]
    total, at = _path_walker(ring)
    # distance of the topmost point from the start
    acc, top_s, top_y = 0.0, 0.0, None
    for a, b in zip(ring, ring[1:]):
        if top_y is None or a[1] < top_y:
            top_s, top_y = acc, a[1]
        acc += math.hypot(b[0] - a[0], b[1] - a[1])
    start = (top_s - text_len / 2.0) % total if total else 0.0
    # the same ring, starting at `start`
    out = [at(start)[0]]
    acc = 0.0
    for a, b in zip(ring, ring[1:]):
        acc += math.hypot(b[0] - a[0], b[1] - a[1])
        if acc > start:
            out.append(b)
    acc = 0.0
    for a, b in zip(ring, ring[1:]):
        acc += math.hypot(b[0] - a[0], b[1] - a[1])
        if acc <= start:
            out.append(b)
    out.append(out[0])
    return out, 0.0
