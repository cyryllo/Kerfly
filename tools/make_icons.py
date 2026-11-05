#!/usr/bin/env python3
"""
Render Kerfly's logo (kerfly/gui/icons/kerfly.svg) to the bitmap icons:
kerfly.png (256 px, Linux desktop entry, README) and kerfly.ico (Windows,
16-256 px), and copy the SVG to the project website (docs/assets/logo.svg).
Run after changing the SVG:

    python tools/make_icons.py

Copyright (C) 2026 Kerfly contributors
Licensed under the GNU General Public License v3 or later. See LICENSE.
"""
import io
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ICONS = os.path.join(ROOT, "kerfly", "gui", "icons")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image  # noqa: E402
from PySide6.QtCore import QBuffer, QIODevice, QRectF, Qt  # noqa: E402
from PySide6.QtGui import QImage, QPainter  # noqa: E402
from PySide6.QtSvg import QSvgRenderer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402


def render(renderer, size):
    img = QImage(size, size, QImage.Format_ARGB32)
    img.fill(Qt.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing, True)
    renderer.render(p, QRectF(0, 0, size, size))
    p.end()
    buf = QBuffer()
    buf.open(QIODevice.WriteOnly)
    img.save(buf, "PNG")
    return Image.open(io.BytesIO(bytes(buf.data()))).convert("RGBA")


def main():
    QApplication.instance() or QApplication(sys.argv[:1])
    renderer = QSvgRenderer(os.path.join(ICONS, "kerfly.svg"))
    if not renderer.isValid():
        sys.exit("kerfly.svg could not be read")
    sizes = (16, 24, 32, 48, 64, 128, 256)
    images = {s: render(renderer, s) for s in sizes}
    images[256].save(os.path.join(ICONS, "kerfly.png"))
    # each size drawn from the SVG (sharper than scaling one bitmap down)
    images[256].save(os.path.join(ICONS, "kerfly.ico"), sizes=[(s, s) for s in sizes],
                     append_images=[images[s] for s in sizes if s != 256])
    import shutil
    shutil.copyfile(os.path.join(ICONS, "kerfly.svg"), os.path.join(ROOT, "docs", "assets", "logo.svg"))
    print("kerfly.png, kerfly.ico written in", ICONS, "and docs/assets/logo.svg updated")


if __name__ == "__main__":
    main()
