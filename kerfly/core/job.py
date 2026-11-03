"""
Job generation: turns a Design plus JobSettings into the EGV byte stream sent
to the laser.

Copyright (C) 2017-2026 Scorch (original code in K40 Whisperer)
Copyright (C) 2026 Kerfly contributors

This program is free software: you can redistribute it and/or modify it under
the terms of the GNU General Public License as published by the Free Software
Foundation, either version 3 of the License, or (at your option) any later
version. See the LICENSE file for details.
"""
from dataclasses import dataclass
from typing import List, Optional

from convex_hull import hull2D
from egv import egv

from .pathopt import optimize_paths
from .raster import make_raster_coords, _no_progress

try:
    import pyclipper
    PYCLIPPER = True
except ImportError:
    PYCLIPPER = False

# operation names (combine with "+", e.g. "Raster_Eng+Vector_Cut")
RASTER_ENG = "Raster_Eng"
VECTOR_ENG = "Vector_Eng"
VECTOR_CUT = "Vector_Cut"
TRACE_ENG = "Trace_Eng"
GCODE_CUT = "Gcode_Cut"


class NoLaserData(Exception):
    pass


@dataclass
class JobChunk:
    """Part of a job sent in one go. power is the laser power to set first
    (M3 power control), or None to leave the power unchanged."""
    data: List[int]
    power: Optional[float] = None
    stage: str = ""


def mirror_rotate_vector_coords(coords, design, settings):
    """Mirror and/or rotate 90 degrees a list of [x, y, loop] rows (returns copies)."""
    xmin = design.bounds[0]
    xmax = design.bounds[1]
    out = []
    for i in range(len(coords)):
        out.append(coords[i][:])
        if settings.mirror:
            if settings.input_csys and design.raster.image is None:
                out[i][0] = -out[i][0]
            else:
                out[i][0] = xmin + xmax - out[i][0]
        if settings.rotate:
            x = out[i][0]
            y = out[i][1]
            out[i][0] = -y
            out[i][1] = x
    return out


def scale_vector_coords(coords, startx, starty, settings):
    """Apply the X/Y (and rotary) calibration scale to coords and the start point."""
    Xscale, Yscale = settings.xy_scale
    if Xscale != 1.0 or Yscale != 1.0:
        coords_scale = []
        for i in range(len(coords)):
            coords_scale.append(coords[i][:])
            x = coords_scale[i][0]
            y = coords_scale[i][1]
            coords_scale[i][0] = x * Xscale
            coords_scale[i][1] = y * Yscale
        return coords_scale, startx * Xscale, starty * Yscale
    return coords, startx, starty


def offset_ecoords(ecoords_in, offset_val):
    """Offset a closed loop outwards by offset_val inches (needs pyclipper)."""
    if not PYCLIPPER:
        return ecoords_in

    loop_num = ecoords_in[0][2]
    pco = pyclipper.PyclipperOffset()
    ecoords_out = []
    pyclip_path = []
    for i in range(0, len(ecoords_in)):
        pyclip_path.append([ecoords_in[i][0] * 1000, ecoords_in[i][1] * 1000])

    pco.AddPath(pyclip_path, pyclipper.JT_ROUND, pyclipper.ET_CLOSEDPOLYGON)
    try:
        plot_coords = pco.Execute(offset_val * 1000.0)[0]
        plot_coords.append(plot_coords[0])
    except Exception:
        plot_coords = []

    for i in range(0, len(plot_coords)):
        ecoords_out.append([plot_coords[i][0] / 1000.0, plot_coords[i][1] / 1000.0, loop_num])
    return ecoords_out


def make_trace_path(design, settings, progress=_no_progress, stop=None):
    """Convex hull around everything in the design, offset by the trace gap,
    for running the head (optionally with the laser) around the job outline."""
    my_hull = hull2D()
    xmin, xmax, ymin, ymax = design.origin_bounds(settings)
    startx = xmin
    starty = ymax

    Vcut_coords = design.vector_cut.ecoords
    Veng_coords = design.vector_engrave.ecoords
    Gcode_coords = design.gcode.ecoords
    if settings.mirror or settings.rotate:
        Vcut_coords = mirror_rotate_vector_coords(Vcut_coords, design, settings)
        Veng_coords = mirror_rotate_vector_coords(Veng_coords, design, settings)
        Gcode_coords = mirror_rotate_vector_coords(Gcode_coords, design, settings)

    if design.raster.ecoords == []:
        # Upstream temporarily clears a set stop flag here so the raster can
        # be computed even when no job is running.
        if stop is not None and stop[0]:
            stop[0] = False
            try:
                make_raster_coords(design, settings, progress, stop)
            finally:
                stop[0] = True
        else:
            make_raster_coords(design, settings, progress, stop)

    # same operation order as upstream: (1/Y)*(1/R), not 1/(Y*R)
    Xscale = 1 / settings.x_scale
    Yscale = 1 / settings.y_scale
    if settings.rotary:
        Yscale = Yscale * (1 / settings.rotary_scale)
    RengHullCoords = []
    for point in design.raster.hull_coords:
        RengHullCoords.append([point[0] * Xscale + xmin, point[1] * Yscale, point[2]])

    all_coords = []
    all_coords.extend(Vcut_coords)
    all_coords.extend(Veng_coords)
    all_coords.extend(Gcode_coords)
    all_coords.extend(RengHullCoords)

    trace_coords = []
    if all_coords != []:
        trace_coords = my_hull.convexHullecoords(all_coords)
        gap = settings.trace_gap / settings.units_scale
        trace_coords = offset_ecoords(trace_coords, gap)

    trace_coords, startx, starty = scale_vector_coords(trace_coords, startx, starty, settings)
    return trace_coords


def _make_egv(coords, startx, starty, feed, settings, raster_step, flip_x_offset,
              rapid_feed, use_laser, update_gui, stop):
    out = []
    egv(target=lambda s: out.append(s)).make_egv_data(
        coords,
        startX=startx,
        startY=starty,
        Feed=feed,
        board_name=settings.board_name,
        Raster_step=raster_step,
        update_gui=update_gui,
        stop_calc=stop,
        FlipXoffset=flip_x_offset,
        Rapid_Feed_Rate=rapid_feed,
        use_laser=use_laser,
    )
    return out


def _join_passes(data, stage_data, passes):
    """Append stage_data `passes` times; '@' replaces the end-of-stage code
    between repetitions (upstream behaviour)."""
    for _ in range(passes):
        if len(data) > 4:
            data[-4] = ord("@")
        data.extend(stage_data)


def build_job(design, settings, operation_type, trace_coords=None,
              progress=_no_progress, update_gui=None, stop=None):
    """Generate the laser data for operation_type.

    Vector data are reordered in place (design.vector_cut / vector_engrave)
    the first time they are used. The raster must already be prepared with
    make_raster_coords().

    Returns a list of JobChunk. Normally one chunk with power=None. With
    settings.power_per_stage (M3 power control) one chunk per stage with the
    power to set before sending it.
    Raises NoLaserData if nothing would be sent (normal mode only).
    """
    feed_factor = settings.feed_factor
    xmin, xmax, ymin, ymax = design.origin_bounds(settings)
    startx = xmin
    starty = ymax

    if settings.home_upper_right:
        Xscale = settings.x_scale
        FlipXoffset = Xscale * xmin + Xscale * xmax
        if settings.rotate:
            startx = -xmin
    else:
        FlipXoffset = None

    Rapid_Feed = settings.rapid_feed * feed_factor if settings.rotary else 0.0

    Raster_Eng_data = []
    Vector_Eng_data = []
    Trace_Eng_data = []
    Vector_Cut_data = []
    G_code_Cut_data = []

    vcut = design.vector_cut
    if operation_type.find(VECTOR_CUT) > -1 and vcut.ecoords != []:
        Feed_Rate = settings.vcut_feed * feed_factor
        progress("Vector Cut: Determining Cut Order....")
        if not vcut.sorted and settings.inside_first:
            vcut.set_ecoords(optimize_paths(vcut.ecoords), data_sorted=True)
        progress("Generating EGV data...")
        coords = vcut.ecoords
        if settings.mirror or settings.rotate:
            coords = mirror_rotate_vector_coords(coords, design, settings)
        coords, startx, starty = scale_vector_coords(coords, startx, starty, settings)
        Vector_Cut_data = _make_egv(coords, startx, starty, Feed_Rate, settings, 0,
                                    FlipXoffset, Rapid_Feed, True, update_gui, stop)

    veng = design.vector_engrave
    if operation_type.find(VECTOR_ENG) > -1 and veng.ecoords != []:
        Feed_Rate = settings.vengrave_feed * feed_factor
        progress("Vector Engrave: Determining Cut Order....")
        if not veng.sorted and settings.inside_first:
            veng.set_ecoords(optimize_paths(veng.ecoords, inside_check=False), data_sorted=True)
        progress("Generating EGV data...")
        coords = veng.ecoords
        if settings.mirror or settings.rotate:
            coords = mirror_rotate_vector_coords(coords, design, settings)
        coords, startx, starty = scale_vector_coords(coords, startx, starty, settings)
        Vector_Eng_data = _make_egv(coords, startx, starty, Feed_Rate, settings, 0,
                                    FlipXoffset, Rapid_Feed, True, update_gui, stop)

    if operation_type.find(TRACE_ENG) > -1 and trace_coords:
        Feed_Rate = settings.trace_feed * feed_factor
        progress("Generating EGV data...")
        Trace_Eng_data = _make_egv(trace_coords, startx, starty, Feed_Rate, settings, 0,
                                   FlipXoffset, Rapid_Feed, settings.trace_with_laser,
                                   update_gui, stop)

    if operation_type.find(RASTER_ENG) > -1 and design.raster.ecoords != []:
        Feed_Rate = settings.raster_feed * feed_factor
        Raster_step = settings.raster_step_mils
        if not settings.engrave_up:
            Raster_step = -Raster_step
        raster_starty = settings.xy_scale[1] * starty
        progress("Generating EGV data...")
        egv_inst = egv(target=lambda s: Raster_Eng_data.append(s))
        egv_inst.make_egv_data(
            design.raster.ecoords,
            startX=0,
            startY=raster_starty,
            Feed=Feed_Rate,
            board_name=settings.board_name,
            Raster_step=Raster_step,
            update_gui=update_gui,
            stop_calc=stop,
            FlipXoffset=FlipXoffset,
            Rapid_Feed_Rate=Rapid_Feed,
            use_laser=True,
        )
        Raster_Eng_data = egv_inst.strip_redundant_codes(Raster_Eng_data)

    if operation_type.find(GCODE_CUT) > -1 and design.gcode.ecoords != []:
        progress("Generating EGV data...")
        coords = design.gcode.ecoords
        if settings.mirror or settings.rotate:
            coords = mirror_rotate_vector_coords(coords, design, settings)
        coords, startx, starty = scale_vector_coords(coords, startx, starty, settings)
        G_code_Cut_data = _make_egv(coords, startx, starty, None, settings, 0,
                                    FlipXoffset, Rapid_Feed, True, update_gui, stop)

    # (stage name, data, passes, power fraction) in the order they are run
    stages = [
        (TRACE_ENG, Trace_Eng_data, 1, settings.trace_power),
        (RASTER_ENG, Raster_Eng_data, settings.raster_passes, settings.raster_power),
        (VECTOR_ENG, Vector_Eng_data, settings.vengrave_passes, settings.vengrave_power),
        (VECTOR_CUT, Vector_Cut_data, settings.vcut_passes, settings.vcut_power),
        (GCODE_CUT, G_code_Cut_data, settings.gcode_passes, settings.gcode_power),
    ]

    if settings.power_per_stage:
        chunks = []
        for name, stage_data, passes, power_fraction in stages:
            if stage_data == []:
                continue
            data = [ord("I")]
            _join_passes(data, stage_data, passes)
            if power_fraction > 1:
                power_fraction = 0
            chunks.append(JobChunk(data, power_fraction * settings.max_power, name))
        return chunks

    # all stages joined into one stream; power settings are not included
    data = [ord("I")]
    for name, stage_data, passes, _ in stages:
        if stage_data != []:
            _join_passes(data, stage_data, passes)
    if len(data) < 4:
        raise NoLaserData("No laser data was generated.")
    return [JobChunk(data)]


def egv_file_bytes(data):
    """Contents of an .EGV file for job data (as written by K40 Whisperer)."""
    header = "Document type : LHYMICRO-GL file\nCreator-Software: K40 Whisperer\n\n%0%0%0%0%"
    return header.encode("latin-1") + bytes(data)
