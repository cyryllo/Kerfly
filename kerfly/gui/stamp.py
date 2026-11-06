"""
Rubber stamp generator: text lines, an optional picture and a frame, drawn at
the stamp's size, then turned into what the laser burns into the rubber: the
colours inverted (the background is burnt away, the text, picture and frame
stay raised) and mirrored left to right (a stamp prints its mirror image).
The result is a black and white raster at 1000 dpi; a cut line around it
cuts the stamp out of the sheet.

Copyright (C) 2026 Kerfly contributors
Licensed under the GNU General Public License v3 or later. See LICENSE.
"""
import os

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QImage, QPainter, QPen

from kerfly.core import generators as gen
from kerfly.core.shapes import ShapeSpec
from kerfly.i18n import N_, _

DPI = 1000
# common self-inking stamp sizes (mm)
PRESETS = [("custom", N_("Own size")), ("26x9", "26 × 9 mm"), ("38x14", "38 × 14 mm"), ("47x18", "47 × 18 mm"),
           ("58x22", "58 × 22 mm"), ("70x25", "70 × 25 mm"), ("82x25", "82 × 25 mm"), ("60x40", "60 × 40 mm"),
           ("75x38", "75 × 38 mm")]
PLACES = [("left", N_("Left of the text")), ("top", N_("Above the text"))]


def stamp_size(v):
    if v.get("preset", "custom") != "custom":
        w, h = v["preset"].split("x")
        return float(w), float(h)
    return float(v["width"]), float(v["height"])


def _load_picture(path, size_px):
    """The picture as a QImage fitting size_px (w, h), or None."""
    if not path or not os.path.isfile(path):
        return None
    if path.lower().endswith(".svg"):
        from PySide6.QtSvg import QSvgRenderer
        renderer = QSvgRenderer(path)
        if not renderer.isValid():
            return None
        d = renderer.defaultSize()
        scale = min(size_px[0] / max(d.width(), 1), size_px[1] / max(d.height(), 1))
        img = QImage(max(1, int(d.width() * scale)), max(1, int(d.height() * scale)), QImage.Format_ARGB32)
        img.fill(Qt.transparent)
        p = QPainter(img)
        renderer.render(p)
        p.end()
        return img
    img = QImage(path)
    if img.isNull():
        return None
    return img.scaled(int(size_px[0]), int(size_px[1]), Qt.KeepAspectRatio, Qt.SmoothTransformation)


def render(v, dpi=DPI):
    """The stamp as it is burnt (inverted and mirrored unless switched off): a black
    and white QImage; dark = burnt."""
    w_mm, h_mm = stamp_size(v)
    px = lambda mm: mm / 25.4 * dpi
    img = QImage(max(1, int(round(px(w_mm)))), max(1, int(round(px(h_mm)))), QImage.Format_Grayscale8)
    img.fill(QColor("white"))
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing, True)
    p.setRenderHint(QPainter.TextAntialiasing, True)
    black = QColor("black")
    frame = float(v.get("frame", 0))
    radius = float(v.get("corner", 0))
    if frame > 0:
        pen = QPen(black, px(frame))
        pen.setJoinStyle(Qt.MiterJoin)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        inset = px(frame) / 2
        p.drawRoundedRect(QRectF(inset, inset, img.width() - 2 * inset, img.height() - 2 * inset),
                          px(radius), px(radius))
    pad = px(frame + float(v.get("margin", 1.0)))
    area = QRectF(pad, pad, img.width() - 2 * pad, img.height() - 2 * pad)
    picture_path = v.get("picture", "")
    if picture_path and area.width() > 2 and area.height() > 2:
        place = v.get("place", "left")
        if place == "top":
            box = QRectF(area.left(), area.top(), area.width(), area.height() * 0.42)
            area = QRectF(area.left(), box.bottom() + px(0.5), area.width(), area.bottom() - box.bottom() - px(0.5))
        else:
            side = min(area.height(), area.width() * 0.4)
            box = QRectF(area.left(), area.top() + (area.height() - side) / 2, side, side)
            area = QRectF(box.right() + px(1.0), area.top(), area.right() - box.right() - px(1.0), area.height())
        pic = _load_picture(picture_path, (box.width(), box.height()))
        if pic is not None:
            p.drawImage(QRectF(box.left() + (box.width() - pic.width()) / 2,
                               box.top() + (box.height() - pic.height()) / 2, pic.width(), pic.height()), pic)
    lines = [l for l in str(v.get("text", "")).split("\n")]
    while lines and not lines[-1].strip():
        lines.pop()
    if lines and area.width() > 2 and area.height() > 2:
        font = QFont(v.get("font", "DejaVu Sans") or "DejaVu Sans")
        font.setBold(bool(v.get("bold", True)))
        size = float(v.get("text_size", 0))
        spacing = 1.15
        if size > 0:
            font.setPixelSize(max(1, int(px(size))))
        else:                                        # as large as fits
            size_px = area.height() / (len(lines) * spacing)
            while size_px > 4:
                font.setPixelSize(int(size_px))
                fm = QFontMetricsF(font)
                if max(fm.horizontalAdvance(l) for l in lines) <= area.width() and \
                        fm.height() * spacing * len(lines) <= area.height() * 1.02:
                    break
                size_px *= 0.95
            font.setPixelSize(max(1, int(size_px)))
        p.setFont(font)
        p.setPen(black)
        fm = QFontMetricsF(font)
        line_h = fm.height() * spacing
        top = area.top() + (area.height() - line_h * len(lines)) / 2
        for n, line in enumerate(lines):
            r = QRectF(area.left(), top + n * line_h, area.width(), line_h)
            p.drawText(r, Qt.AlignHCenter | Qt.AlignVCenter, line)
    p.end()
    if v.get("invert", True):
        img.invertPixels()
    if v.get("mirror", True):
        img = img.flipped(Qt.Horizontal)
    mono = img.convertToFormat(QImage.Format_Mono, Qt.MonoOnly | Qt.ThresholdDither)
    return mono.convertToFormat(QImage.Format_Grayscale8)


def make(v, window):
    w_mm, h_mm = stamp_size(v)
    if w_mm < 3 or h_mm < 3:
        raise ValueError(_("The stamp is too small."))
    out = gen.Generated(name="Stamp")
    out.items.append(gen.Item(None, 0.0, 0.0, name="Stamp", image=render(v), dpi=DPI))
    if v.get("outline", True):
        out.items.append(gen.Item(ShapeSpec(kind="rectangle", width=w_mm, height=h_mm,
                                            corner_radius=float(v.get("corner", 0)), operation="cut"),
                                  0.0, 0.0, name="Stamp outline"))
    return out


FIELDS = [
    ("preset", N_("Stamp size"), "choice", "47x18", PRESETS,
     N_("A usual size of self-inking stamps, or your own size below")),
    ("width", N_("Width"), "float", 50.0, (5, 300, 1, "mm"), N_("Width of the stamp (own size)")),
    ("height", N_("Height"), "float", 20.0, (5, 300, 1, "mm"), N_("Height of the stamp (own size)")),
    ("text", N_("Text"), "multiline", N_("YOUR COMPANY\nStreet 1, 00-000 City\nphone 123 456 789"), None,
     N_("The lines of the stamp")),
    ("font", N_("Font"), "font", "DejaVu Sans", None, N_("Font of the text")),
    ("bold", N_("Bold"), "bool", True, None, N_("Bold letters stamp more clearly")),
    ("text_size", N_("Text height"), "float", 0.0, (0, 50, 1, "mm"),
     N_("Height of the letters (0: as large as fits)")),
    ("picture", N_("Picture"), "file", "", None, N_("A logo or picture (PNG, JPG or SVG); empty: none")),
    ("place", N_("Picture place"), "choice", "left", PLACES, N_("Where the picture goes")),
    ("frame", N_("Frame"), "float", 0.6, (0, 5, 1, "mm"), N_("Width of the raised frame around it (0: none)")),
    ("corner", N_("Corner radius"), "float", 1.0, (0, 20, 1, "mm"), N_("Rounded corners of the frame and outline")),
    ("margin", N_("Margin"), "float", 1.0, (0, 10, 1, "mm"), N_("Space between the frame and the text")),
    ("invert", N_("Invert (for rubber)"), "bool", True, None,
     N_("Burn the background away so the text stays raised (off: burn the text itself)")),
    ("mirror", N_("Mirror"), "bool", True, None, N_("A stamp prints its mirror image: mirror it left to right")),
    ("outline", N_("Cut the outline"), "bool", True, None, N_("Cut the stamp out of the sheet")),
]
