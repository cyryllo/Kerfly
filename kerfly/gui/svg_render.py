"""
Built-in SVG raster renderer (Qt SVG), used for the raster part of SVG files
when Inkscape is not installed.

Copyright (C) 2026 Kerfly contributors
Licensed under the GNU General Public License v3 or later. See LICENSE.
"""
from PIL import Image
from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QImage, QPainter
from PySide6.QtSvg import QSvgRenderer

STRIP_ROWS = 1024        # render in strips so big pages at 1000 dpi stay small in memory


def render_svg(svg_bytes, width, height):
    """Render a whole SVG page into a width x height grayscale PIL image on white."""
    renderer = QSvgRenderer(QByteArray(svg_bytes))
    if not renderer.isValid():
        raise ValueError("The SVG file could not be read by the built-in renderer.")
    renderer.setAspectRatioMode(Qt.IgnoreAspectRatio)       # the page is mapped exactly, like Inkscape
    out = Image.new("L", (width, height), 255)
    for y0 in range(0, height, STRIP_ROWS):
        rows = min(STRIP_ROWS, height - y0)
        strip = QImage(width, rows, QImage.Format_RGB32)
        strip.fill(Qt.white)
        p = QPainter(strip)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setRenderHint(QPainter.SmoothPixmapTransform, True)
        p.translate(0, -y0)
        renderer.render(p, QRectF(0, 0, width, height))
        p.end()
        gray = strip.convertToFormat(QImage.Format_Grayscale8)
        data = bytes(gray.constBits())[:gray.bytesPerLine() * rows]
        part = Image.frombuffer("L", (width, rows), data, "raw", "L", gray.bytesPerLine(), 1)
        out.paste(part, (0, y0))
    return out
