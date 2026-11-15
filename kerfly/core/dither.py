"""
Ways to turn a grayscale picture into laser dots (Settings → Raster → Dithering).
Floyd-Steinberg is K40 Whisperer's (Pillow's, the default); the others give a
different grain: Atkinson keeps light areas clean and contrast high (good on
wood), Jarvis, Stucki, Burkes and Sierra spread the error wider (smoother
gradients), the ordered (Bayer) pattern gives a regular cross-hatch texture
that engraves evenly, Threshold is plain black and white.

Copyright (C) 2026 Kerfly contributors
Licensed under the GNU General Public License v3 or later. See LICENSE.
"""
from time import time

from PIL import Image, ImageChops

from kerfly.i18n import N_

# (code, English name: translated in the GUI)
METHODS = (("floyd", "Floyd-Steinberg"), ("atkinson", "Atkinson"), ("jarvis", "Jarvis-Judice-Ninke"),
           ("stucki", "Stucki"), ("burkes", "Burkes"), ("sierra", "Sierra"), ("bayer", N_("Ordered (Bayer)")),
           ("threshold", N_("Threshold")))
CODES = tuple(code for code, _name in METHODS)
DEFAULT = "floyd"

# error diffusion: (dx, dy, weight), divisor
KERNELS = {
    "atkinson": ([(1, 0, 1), (2, 0, 1), (-1, 1, 1), (0, 1, 1), (1, 1, 1), (0, 2, 1)], 8),
    "jarvis": ([(1, 0, 7), (2, 0, 5), (-2, 1, 3), (-1, 1, 5), (0, 1, 7), (1, 1, 5), (2, 1, 3),
                (-2, 2, 1), (-1, 2, 3), (0, 2, 5), (1, 2, 3), (2, 2, 1)], 48),
    "stucki": ([(1, 0, 8), (2, 0, 4), (-2, 1, 2), (-1, 1, 4), (0, 1, 8), (1, 1, 4), (2, 1, 2),
                (-2, 2, 1), (-1, 2, 2), (0, 2, 4), (1, 2, 2), (2, 2, 1)], 42),
    "burkes": ([(1, 0, 8), (2, 0, 4), (-2, 1, 2), (-1, 1, 4), (0, 1, 8), (1, 1, 4), (2, 1, 2)], 32),
    "sierra": ([(1, 0, 5), (2, 0, 3), (-2, 1, 2), (-1, 1, 4), (0, 1, 5), (1, 1, 4), (2, 1, 2),
                (-1, 2, 2), (0, 2, 3), (1, 2, 2)], 32),
}

BAYER8 = [[0, 32, 8, 40, 2, 34, 10, 42], [48, 16, 56, 24, 50, 18, 58, 26],
          [12, 44, 4, 36, 14, 46, 6, 38], [60, 28, 52, 20, 62, 30, 54, 22],
          [3, 35, 11, 43, 1, 33, 9, 41], [51, 19, 59, 27, 49, 17, 57, 25],
          [15, 47, 7, 39, 13, 45, 5, 37], [63, 31, 55, 23, 61, 29, 53, 21]]


def _no_progress(_message):
    pass


def _diffuse(image, kernel, divisor, progress):
    w, h = image.size
    px = [float(v) for v in image.tobytes()]
    out = bytearray(w * h)
    taps = [(dx, dy, dy * w + dx, wt / float(divisor)) for dx, dy, wt in kernel]
    stamp = 0
    for y in range(h):
        now = int(3 * time())
        if now != stamp:
            stamp = now
            progress("Creating halftone image: %.1f %%" % (100.0 * y / max(1, h)))
        row = y * w
        for x in range(w):
            i = row + x
            old = px[i]
            new = 255 if old >= 128 else 0
            out[i] = new
            err = old - new
            if err:
                for dx, dy, di, f in taps:
                    xx = x + dx
                    if 0 <= xx < w and y + dy < h:
                        px[i + di] += err * f
    return Image.frombytes("L", (w, h), bytes(out)).convert("1")


def _bayer(image):
    w, h = image.size
    tile = Image.new("L", (8, 8))
    tile.putdata([int((v + 0.5) * 256 / 64) for row in BAYER8 for v in row])
    row = Image.new("L", (w, 8))
    for x in range(0, w, 8):
        row.paste(tile, (x, 0))
    thresholds = Image.new("L", (w, h))
    for y in range(0, h, 8):
        thresholds.paste(row, (0, y))
    # white where the picture is lighter than the threshold of its place in the 8 x 8 pattern
    return ImageChops.subtract(image, thresholds).point(lambda v: 255 if v > 0 else 0).convert("1")


def dither(image, method=DEFAULT, progress=_no_progress):
    """A grayscale ('L') picture -> a 1-bit picture with the chosen method."""
    image = image.convert("L")
    if method == "floyd" or method not in CODES:
        return image.convert("1")                     # Pillow's Floyd-Steinberg, as K40 Whisperer
    if method == "threshold":
        return image.point(lambda v: 255 if v >= 128 else 0).convert("1")
    if method == "bayer":
        return _bayer(image)
    kernel, divisor = KERNELS[method]
    return _diffuse(image, kernel, divisor, progress)
