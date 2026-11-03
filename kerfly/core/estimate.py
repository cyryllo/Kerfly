"""
Job time estimate (same formulas as K40 Whisperer).

Copyright (C) 2017-2026 Scorch (original code in K40 Whisperer)
Copyright (C) 2026 Kerfly contributors

This program is free software: you can redistribute it and/or modify it under
the terms of the GNU General Public License as published by the Free Software
Foundation, either version 3 of the License, or (at your option) any later
version. See the LICENSE file for details.
"""
from .job import GCODE_CUT, RASTER_ENG, VECTOR_CUT, VECTOR_ENG

RAPID_FEED = 100.0 / 25.4   # assumed rapid move speed, in/s (upstream: "to be confirmed")


def estimate_times(design, settings):
    """Estimated seconds per operation. The raster time is None until the
    raster lines have been computed (make_raster_coords)."""
    factor = 60.0 if settings.units == "in" else 25.4   # -> inches per second
    reng_feed = settings.raster_feed / factor
    veng_feed = settings.vengrave_feed / factor
    vcut_feed = settings.vcut_feed / factor

    reng, veng, vcut = design.raster, design.vector_engrave, design.vector_cut
    times = {RASTER_ENG: 0 if reng.rpaths else None, VECTOR_ENG: 0, VECTOR_CUT: 0}
    if reng.len is not None:
        # empirical acceleration time per scan line, measured upstream
        f = reng_feed * 60.0
        accel_time = 8.3264 * f ** (-0.7451) if f <= 300 else 2.5913 * f ** (-0.4795)
        times[RASTER_ENG] = (reng.len / reng_feed) * settings.raster_passes + reng.n_scanlines * accel_time
    if veng.len is not None:
        times[VECTOR_ENG] = (veng.len / veng_feed + veng.move / RAPID_FEED) * settings.vengrave_passes
    if vcut.len is not None:
        times[VECTOR_CUT] = (vcut.len / vcut_feed + vcut.move / RAPID_FEED) * settings.vcut_passes
    times[GCODE_CUT] = design.gcode.gcode_time * settings.gcode_passes
    return times


def format_time(seconds):
    """'1h 5m', '3m 20s', '45s', or '?' when unknown."""
    if seconds is None or seconds < 0:
        return "?"
    s = round(seconds)
    m, s = divmod(s, 60)
    h, m = divmod(m, 60)
    res = ""
    if h > 0:
        res = "%dh " % h
    if m > 0:
        res += "%dm " % m
    if h == 0:
        res += "%ds " % s
    return res.strip()
