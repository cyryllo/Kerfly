"""
Raster preparation: levels curve, halftoning and scan line generation.

Copyright (C) 2017-2026 Scorch (original code in K40 Whisperer)
Copyright (C) 2026 Kerfly contributors

This program is free software: you can redistribute it and/or modify it under
the terms of the GNU General Public License as published by the Free Software
Foundation, either version 3 of the License, or (at your option) any later
version. See the LICENSE file for details.
"""
from math import floor
from time import time

from PIL import Image, ImageOps

from convex_hull import hull2D
from interpolate import interpolate


class JobStopped(Exception):
    """Raised when the user stops a running preparation."""


def _no_progress(message):
    pass


def _check_stop(stop):
    if stop is not None and stop[0]:
        raise JobStopped("Action stopped by User.")


def rotate_raster(image_in):
    """Rotate a grayscale image 90 degrees (row/column 0 are left white, as upstream)."""
    wim, him = image_in.size
    im_rotated = Image.new("L", (him, wim), "white")
    image_in_np = image_in.load()
    im_rotated_np = im_rotated.load()
    for i in range(1, him):
        for j in range(1, wim):
            im_rotated_np[i, wim - j] = image_in_np[j, i]
    return im_rotated


def generate_bezier(M1, M2, w, n=100):
    """Rational quadratic Bezier levels curve from (0,0) to (255,255).
    M1/M2 are the slopes at the ends, w the weight of the middle control point."""
    if M1 == M2:
        x1 = 0
        y1 = 0
    else:
        x1 = 255 * (1 - M2) / (M1 - M2)
        y1 = M1 * x1
    x = []
    y = []
    for step in range(0, n + 1):
        t = float(step) / float(n)
        Ct = 1 / (pow(1 - t, 2) + 2 * (1 - t) * t * w + pow(t, 2))
        x.append(Ct * (2 * (1 - t) * t * w * x1 + pow(t, 2) * 255))
        y.append(Ct * (2 * (1 - t) * t * w * y1 + pow(t, 2) * 255))
    return x, y


def convert_halftoning(image, settings, progress=_no_progress):
    """Apply the levels curve, then Floyd-Steinberg dither to a 1-bit image.
    (Halftone approach originally contributed to K40 Whisperer by Isai B. Cicourel.)"""
    image = image.convert('L')
    x_lim, y_lim = image.size
    pixel = image.load()

    M1 = settings.bezier_m1
    M2 = settings.bezier_m2
    w = settings.bezier_weight

    if w > 0:
        x, y = generate_bezier(M1, M2, w)
        interp = interpolate(x, y)
        val_map = []
        # map Bezier curve to values between 0 and 255
        for val in range(0, 256):
            val_map.append(int(round(interp[val])))
        timestamp = 0
        for y in range(1, y_lim):
            stamp = int(3 * time())  # update every 1/3 of a second
            if stamp != timestamp:
                timestamp = stamp
                progress("Adjusting Image Darkness: %.1f %%" % ((100.0 * y) / y_lim))
            for x in range(1, x_lim):
                pixel[x, y] = val_map[pixel[x, y]]

    progress("Creating Halftone Image.")
    image = image.convert('1')
    return image


def make_raster_coords(design, settings, progress=_no_progress, stop=None):
    """Compute raster scan lines for design.raster (no-op if already computed).

    Sets design.raster ecoords (one [x, y, loop] pair per laser-on run, inches),
    len, n_scanlines, hull_coords and the rpaths flag.
    Raises JobStopped if stop[0] becomes True.
    """
    reng = design.raster
    if reng.rpaths:
        return
    input_dpi = design.input_dpi
    hcoords = []
    if reng.image is not None and reng.ecoords == []:
        ecoords = []
        cutoff = 128
        image_temp = reng.image.convert("L")

        if settings.negate:
            image_temp = ImageOps.invert(image_temp)

        if settings.mirror:
            image_temp = ImageOps.mirror(image_temp)

        if settings.rotate:
            image_temp = rotate_raster(image_temp)

        Xscale, Yscale = settings.xy_scale
        if Xscale != 1.0 or Yscale != 1.0:
            wim, him = image_temp.size
            nw = int(wim * Xscale)
            nh = int(him * Yscale)
            image_temp = image_temp.resize((nw, nh))

        if settings.halftone:
            ht_size_mils = round(input_dpi / settings.halftone_dpi, 1)
            npixels = int(round(ht_size_mils, 1))
            if npixels == 0:
                return
            wim, him = image_temp.size
            # convert to halftone at the halftone resolution, then scale back
            nw = int(wim / npixels)
            nh = int(him / npixels)
            image_temp = image_temp.resize((nw, nh))
            image_temp = convert_halftoning(image_temp, settings, progress)
            image_temp = image_temp.resize((wim, him))
        else:
            image_temp = image_temp.point(lambda x: 0 if x < 128 else 255, '1')

        Reng_np = image_temp.load()
        wim, him = image_temp.size
        del image_temp

        x = 0
        y = 0
        loop = 1
        LENGTH = 0
        n_scanlines = 0

        my_hull = hull2D()
        bignumber = 9999999
        Raster_step = int(settings.raster_step_mils)
        timestamp = 0
        im_height_mils = int(him / input_dpi * 1000.0)
        for i_step in range(0, im_height_mils, Raster_step):
            i = floor(i_step * input_dpi / 1000.0)
            stamp = int(3 * time())  # update every 1/3 of a second
            if stamp != timestamp:
                timestamp = stamp
                progress("Creating Scan Lines: %.1f %%" % ((100.0 * i) / him))
            _check_stop(stop)
            line = []
            cnt = 1
            LEFT = bignumber
            RIGHT = -bignumber
            for j in range(1, wim):
                if Reng_np[j, i] == Reng_np[j - 1, i]:
                    cnt = cnt + 1
                else:
                    if Reng_np[j - 1, i]:
                        laser = "U"
                    else:
                        laser = "D"
                        LEFT = min(j - cnt, LEFT)
                        RIGHT = max(j, RIGHT)
                    line.append((cnt, laser))
                    cnt = 1
            if Reng_np[j - 1, i] > cutoff:
                laser = "U"
            else:
                laser = "D"
                LEFT = min(j - cnt, LEFT)
                RIGHT = max(j, RIGHT)

            line.append((cnt, laser))
            if LEFT != bignumber and RIGHT != -bignumber:
                LENGTH = LENGTH + (RIGHT - LEFT) / input_dpi
                n_scanlines = n_scanlines + 1

            y = (im_height_mils - i_step) / 1000.0
            x = 0
            if LEFT != bignumber:
                hcoords.append([LEFT / input_dpi, y])
            if RIGHT != -bignumber:
                hcoords.append([RIGHT / input_dpi, y])
            if hcoords != []:
                hcoords = my_hull.convexHullecoords(hcoords)

            for seg in line:
                delta = seg[0] / input_dpi
                if seg[1] == "D":
                    loop = loop + 1
                    ecoords.append([x, y, loop])
                    ecoords.append([x + delta, y, loop])
                x = x + delta
        reng.set_ecoords(ecoords, data_sorted=True)
        reng.len = LENGTH
        reng.n_scanlines = n_scanlines
    # flag: raster paths have been calculated
    reng.rpaths = True
    reng.hull_coords = hcoords
