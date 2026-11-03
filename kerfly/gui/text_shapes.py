"""
Text to outlines using the fonts installed on the system (through Qt).

Copyright (C) 2026 Kerfly contributors
Licensed under the GNU General Public License v3 or later. See LICENSE.
"""
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


def update_text_spec(spec):
    """Recompute a text ShapeSpec's outlines and size after its text or font changed."""
    spec.text_outlines = text_outlines(spec.text, spec.font_family, spec.font_size, spec.bold, spec.italic)
    xs = [x for p in spec.text_outlines for x, _ in p]
    ys = [y for p in spec.text_outlines for _, y in p]
    spec.width = (max(xs) - min(xs)) if xs else 0.0
    spec.height = (max(ys) - min(ys)) if ys else 0.0
    return spec
