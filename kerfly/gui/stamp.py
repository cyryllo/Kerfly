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

from PySide6.QtCore import QPointF, QRectF, Qt
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
        _draw_picture(p, picture_path, box)
    _draw_lines(p, _lines(v.get("text", "")), area, v, px(float(v.get("text_size", 0))))
    p.end()
    return _finish(img, v)


def _lines(text):
    lines = [l for l in str(text).split("\n")]
    while lines and not lines[-1].strip():
        lines.pop()
    return lines


def _font(v):
    font = QFont(v.get("font", "DejaVu Sans") or "DejaVu Sans")
    font.setBold(bool(v.get("bold", True)))
    return font


def _draw_picture(p, path, box):
    """The picture centred in box (QRectF, pixels), as large as fits."""
    pic = _load_picture(path, (box.width(), box.height()))
    if pic is not None:
        p.drawImage(QRectF(box.left() + (box.width() - pic.width()) / 2,
                           box.top() + (box.height() - pic.height()) / 2, pic.width(), pic.height()), pic)


def _draw_lines(p, lines, area, v, size_px=0.0):
    """Text lines centred in area (QRectF, pixels); size_px: letter height
    (0: as large as fits)."""
    if not lines or area.width() <= 2 or area.height() <= 2:
        return
    font = _font(v)
    spacing = 1.15
    if size_px > 0:
        font.setPixelSize(max(1, int(size_px)))
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
    p.setPen(QColor("black"))
    fm = QFontMetricsF(font)
    line_h = fm.height() * spacing
    top = area.top() + (area.height() - line_h * len(lines)) / 2
    for n, line in enumerate(lines):
        r = QRectF(area.left(), top + n * line_h, area.width(), line_h)
        p.drawText(r, Qt.AlignHCenter | Qt.AlignVCenter, line)


def _finish(img, v):
    """Inverted and mirrored as asked, then pure black and white."""
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


# ---------------------------------------------------------------- round stamp
# common round self-inking stamps (diameter, mm)
ROUND_PRESETS = [("custom", N_("Own size")), ("30", "Ø 30 mm"), ("40", "Ø 40 mm"), ("42", "Ø 42 mm"),
                 ("45", "Ø 45 mm"), ("50", "Ø 50 mm")]


def round_diameter(v):
    if v.get("preset", "custom") != "custom":
        return float(v["preset"])
    return float(v["diameter"])


def _ring_font(v, cap_px):
    """The font whose capital letters are cap_px high."""
    font = _font(v)
    font.setPixelSize(100)
    cap = QFontMetricsF(font).capHeight() or 70.0
    font.setPixelSize(max(1, int(round(100.0 * cap_px / cap))))
    return font


def _arc_widths(text, font, spacing_px):
    fm = QFontMetricsF(font)
    widths = [fm.horizontalAdvance(ch) for ch in text]
    return widths, sum(widths) + spacing_px * max(0, len(text) - 1)


def _fit_arc(text, font, mid_r, spacing_px, max_deg):
    """The font's pixel size at which text along a circle of radius mid_r takes
    at most max_deg degrees."""
    import math
    size = font.pixelSize()
    for _attempt in range(40):
        f = QFont(font)
        f.setPixelSize(size)
        _w, total = _arc_widths(text, f, spacing_px)
        angle = math.degrees(total / mid_r)
        if angle <= max_deg or size <= 4:
            break
        size = max(4, int(size * max_deg / angle * 0.98))
    return size


def _arc_text(p, text, font, cx, cy, baseline_r, mid_r, spacing_px, top):
    """Letters along a circle: top=True across the top reading left to right
    (letters point outwards), False across the bottom (letters point to the
    centre). Returns the angle the text takes (degrees)."""
    import math
    if not text:
        return 0.0
    widths, total = _arc_widths(text, font, spacing_px)
    angle = math.degrees(total / mid_r)
    p.setFont(font)
    p.setPen(QColor("black"))
    start = -90.0 - angle / 2 if top else 90.0 + angle / 2
    done = 0.0
    for ch, w in zip(text, widths):
        theta = start + math.degrees((done + w / 2) / mid_r) * (1 if top else -1)
        t = math.radians(theta)
        p.save()
        p.translate(cx + baseline_r * math.cos(t), cy + baseline_r * math.sin(t))
        p.rotate(theta + 90 if top else theta - 90)
        p.drawText(QPointF(-w / 2, 0), ch)
        p.restore()
        done += w + spacing_px
    return angle


def render_round(v, dpi=DPI):
    """A round stamp as it is burnt: an outer ring, text around the top and the
    bottom, an inner ring, and a picture and/or text lines in the middle."""
    d_mm = round_diameter(v)
    px = lambda mm: mm / 25.4 * dpi
    size = max(1, int(round(px(d_mm))))
    img = QImage(size, size, QImage.Format_Grayscale8)
    img.fill(QColor("white"))
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing, True)
    p.setRenderHint(QPainter.TextAntialiasing, True)
    black = QColor("black")
    c = size / 2.0
    r = size / 2.0
    frame = px(float(v.get("frame", 0)))
    gap = px(float(v.get("margin", 0.6)))
    if frame > 0:
        p.setPen(QPen(black, frame))
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(QPointF(c, c), r - frame / 2, r - frame / 2)
    top_text = str(v.get("top_text", "")).strip()
    bottom_text = str(v.get("bottom_text", "")).strip()
    inner_r = r - frame - gap                      # what is left inside the outer ring
    if top_text or bottom_text:
        text_h = px(float(v.get("ring_text_size", 0))) or 0.12 * px(d_mm)
        band_out = inner_r
        band_in = band_out - text_h
        mid = band_in + text_h / 2
        spacing = px(float(v.get("letter_spacing", 0.3)))
        both = bool(top_text and bottom_text)
        # one letter size for both texts: the smaller of what fits each arc
        font = _ring_font(v, text_h)
        size = font.pixelSize()
        if top_text:
            size = min(size, _fit_arc(top_text, font, mid, spacing, 200.0 if both else 330.0))
        if bottom_text:
            size = min(size, _fit_arc(bottom_text, font, mid, spacing, 120.0 if both else 330.0))
        font.setPixelSize(size)
        # the band as high as the letters that fit, the inner ring close under them
        cap = min(text_h, QFontMetricsF(font).capHeight())
        band_in = band_out - cap
        mid = band_in + cap / 2
        text_h = cap
        a_top = _arc_text(p, top_text, font, c, c, band_in, mid, spacing, True)
        a_bottom = _arc_text(p, bottom_text, font, c, c, band_out, mid, spacing, False)
        if both and v.get("dots", True) and a_top + a_bottom < 340:
            # a dot on each side, between the two texts
            import math
            p.setPen(Qt.NoPen)
            p.setBrush(black)
            gap_mid = ((-90 + a_top / 2) + (90 - a_bottom / 2)) / 2.0     # right side
            for t in (gap_mid, 180.0 - gap_mid):
                t = math.radians(t)
                p.drawEllipse(QPointF(c + mid * math.cos(t), c + mid * math.sin(t)), text_h * 0.28, text_h * 0.28)
            p.setBrush(Qt.NoBrush)
        inner_r = band_in - gap
        ring = px(float(v.get("inner_ring", 0)))
        if ring > 0:
            p.setPen(QPen(black, ring))
            p.setBrush(Qt.NoBrush)
            p.drawEllipse(QPointF(c, c), inner_r - ring / 2, inner_r - ring / 2)
            inner_r -= ring + gap
    # the middle: a box inside the inner circle
    lines = _lines(v.get("text", ""))
    picture_path = v.get("picture", "")
    if inner_r > 2:
        half_w, half_h = inner_r * 0.8, inner_r * 0.6
        area = QRectF(c - half_w, c - half_h, 2 * half_w, 2 * half_h)
        if picture_path:
            if lines:
                box = QRectF(area.left(), area.top(), area.width(), area.height() * 0.55)
                area = QRectF(area.left(), box.bottom() + px(0.3), area.width(),
                              area.bottom() - box.bottom() - px(0.3))
            else:
                side = inner_r * 1.35
                box = QRectF(c - side / 2, c - side / 2, side, side)
            _draw_picture(p, picture_path, box)
        _draw_lines(p, lines, area, v, px(float(v.get("text_size", 0))))
    p.end()
    return _finish(img, v)


def make_round(v, window):
    d_mm = round_diameter(v)
    if d_mm < 8:
        raise ValueError(_("The stamp is too small."))
    out = gen.Generated(name="Stamp")
    out.items.append(gen.Item(None, 0.0, 0.0, name="Stamp", image=render_round(v), dpi=DPI))
    if v.get("outline", True):
        out.items.append(gen.Item(ShapeSpec(kind="ellipse", width=d_mm, height=d_mm, operation="cut"),
                                  0.0, 0.0, name="Stamp outline"))
    return out


ROUND_FIELDS = [
    ("preset", N_("Stamp size"), "choice", "40", ROUND_PRESETS,
     N_("A usual size of round self-inking stamps, or your own size below")),
    ("diameter", N_("Diameter"), "float", 40.0, (10, 300, 1, "mm"), N_("Diameter of the stamp (own size)")),
    ("top_text", N_("Text at the top"), "text", N_("YOUR COMPANY NAME"), None,
     N_("Text around the top of the stamp, reading left to right")),
    ("bottom_text", N_("Text at the bottom"), "text", N_("CITY"), None,
     N_("Text around the bottom of the stamp, reading left to right (empty: none)")),
    ("ring_text_size", N_("Ring text height"), "float", 0.0, (0, 30, 1, "mm"),
     N_("Height of the capital letters around the stamp (0: about an eighth of the diameter)")),
    ("letter_spacing", N_("Letter spacing"), "float", 0.3, (0, 5, 1, "mm"),
     N_("Extra space between the letters around the stamp")),
    ("dots", N_("Dots between the texts"), "bool", True, None,
     N_("A dot on each side between the top and the bottom text")),
    ("text", N_("Text in the middle"), "multiline", N_("No. 123"), None, N_("The lines in the middle (empty: none)")),
    ("text_size", N_("Text height"), "float", 0.0, (0, 50, 1, "mm"),
     N_("Height of the letters in the middle (0: as large as fits)")),
    ("font", N_("Font"), "font", "DejaVu Sans", None, N_("Font of the text")),
    ("bold", N_("Bold"), "bool", True, None, N_("Bold letters stamp more clearly")),
    ("picture", N_("Picture"), "file", "", None,
     N_("A logo or picture in the middle (PNG, JPG or SVG); empty: none")),
    ("frame", N_("Outer ring"), "float", 1.0, (0, 5, 1, "mm"), N_("Width of the raised outer ring (0: none)")),
    ("inner_ring", N_("Inner ring"), "float", 0.5, (0, 5, 1, "mm"),
     N_("Width of the ring inside the text (0: none)")),
    ("margin", N_("Margin"), "float", 0.6, (0, 5, 1, "mm"), N_("Space between the rings and the text")),
    ("invert", N_("Invert (for rubber)"), "bool", True, None,
     N_("Burn the background away so the text stays raised (off: burn the text itself)")),
    ("mirror", N_("Mirror"), "bool", True, None, N_("A stamp prints its mirror image: mirror it left to right")),
    ("outline", N_("Cut the outline"), "bool", True, None, N_("Cut the stamp out of the sheet")),
]
