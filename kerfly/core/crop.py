"""
Cut a piece out of a picture (the Cut out of picture tool): the part of the
picture inside a rectangle or an ellipse drawn over it stays, the rest goes
(made white, which is not engraved), and the picture is trimmed to it.

Copyright (C) 2026 Kerfly contributors
Licensed under the GNU General Public License v3 or later. See LICENSE.
"""
import math

from PIL import Image, ImageDraw


def outline_points(x0, y0, x1, y1, shape="rect", segments=72):
    """The outline of the cut (any coordinates): a rectangle's four corners or an ellipse's points."""
    if shape == "ellipse":
        cx, cy, rx, ry = (x0 + x1) / 2.0, (y0 + y1) / 2.0, abs(x1 - x0) / 2.0, abs(y1 - y0) / 2.0
        return [(cx + rx * math.cos(2 * math.pi * i / segments), cy + ry * math.sin(2 * math.pi * i / segments))
                for i in range(segments)]
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]


def cut_out(image, polygon):
    """(new picture, (left, top) of it in the old one's pixels) or None when nothing is left.
    polygon: the outline in the picture's pixels (y down); outside it the picture becomes white."""
    w, h = image.size
    xs = [p[0] for p in polygon]
    ys = [p[1] for p in polygon]
    left, top = max(0, int(math.floor(min(xs)))), max(0, int(math.floor(min(ys))))
    right, bottom = min(w, int(math.ceil(max(xs)))), min(h, int(math.ceil(max(ys))))
    if right - left < 2 or bottom - top < 2:
        return None
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).polygon([(float(x), float(y)) for x, y in polygon], fill=255)
    mode = image.mode
    white = Image.new(mode, (w, h), "white")
    kept = Image.composite(image, white, mask)
    return kept.crop((left, top, right, bottom)), (left, top)
