"""
Job simulation: the laser head's moves in the order the job will run them,
with how long each takes, for the bed view to play back.

Layers run as in a job (raster, outline engrave, cut, G-code), vector paths in
the order the job uses (inside first). A raster is shown as its scan lines,
one line per millimetre (each standing for all the scan lines in that
millimetre).

Copyright (C) 2026 Kerfly contributors
Licensed under the GNU General Public License v3 or later. See LICENSE.
"""
import copy
import math
from dataclasses import dataclass

from .layers import CUT, ENGRAVE, GCODE, RASTER, compile_layer, run_order
from .pathopt import optimize_paths

RAPID_MM_S = 150.0               # travel speed between cuts (approximate)


@dataclass
class Step:
    x0: float                    # bed millimetres, y down from home
    y0: float
    x1: float
    y1: float
    burn: bool                   # laser on (False: travel)
    kind: str                    # layer kind
    seconds: float
    layer: str = ""


def _speed_mm_s(speed, units):
    return speed if units == "mm" else speed * 25.4 / 60.0


def timeline(elements, layers, settings, units="mm", start=(0.0, 0.0)):
    """Steps of the whole job, starting from `start` (bed mm). Returns the list
    of Steps; the total time is the sum of their seconds."""
    steps = []
    head = start
    for layer in run_order(layers):
        if not layer.enabled:
            continue
        design, origin = compile_layer(elements, layer, layers)
        if design is None or origin is None:
            continue
        xmin, _xmax, _ymin, ymax = design.bounds

        def bed(x, y):
            return ((x - xmin + origin[0]) * 25.4, -(y - ymax + origin[1]) * 25.4)
        speed = max(_speed_mm_s(layer.speed, units), 0.01)
        passes = max(1, int(layer.passes))
        if layer.kind == RASTER:
            paths = _raster_rows(design, bed, settings)
        else:
            source = {CUT: design.vector_cut, ENGRAVE: design.vector_engrave,
                      GCODE: design.gcode}[layer.kind].ecoords
            coords = copy.deepcopy(source)
            if coords and settings.inside_first and layer.kind != GCODE:
                coords = optimize_paths(coords, inside_check=layer.kind == CUT)
            paths = _loops(coords, bed)
        for _p in range(passes):
            for path, step_factor in paths:
                if not path:
                    continue
                if path[0] != head:
                    steps.append(_step(head, path[0], False, layer, RAPID_MM_S))
                for a, b in zip(path, path[1:]):
                    steps.append(_step(a, b, True, layer, speed / step_factor))
                head = path[-1]
    return steps


def _step(a, b, burn, layer, speed):
    length = math.hypot(b[0] - a[0], b[1] - a[1])
    return Step(a[0], a[1], b[0], b[1], burn, layer.kind, length / speed if speed > 0 else 0.0, layer.name)


def _loops(coords, bed):
    out, loop, current = [], None, []
    for row in coords:
        if row[2] != loop:
            if current:
                out.append((current, 1.0))
            loop, current = row[2], []
        current.append(bed(row[0], row[1]))
    if current:
        out.append((current, 1.0))
    return out


def _raster_rows(design, bed, settings):
    """Scan lines across the dark part of the raster, one per millimetre,
    zigzag. Each stands for all the real scan lines in that millimetre, so it
    is played more slowly by that many times."""
    im = design.raster.image
    if im is None:
        return []
    gray = im.convert("L")
    w, h = gray.size
    dpi = design.input_dpi or 1000.0
    xmin, _xmax, _ymin, ymax = design.bounds
    step_mm = max(float(settings.raster_step) * 25.4, 0.01)
    lines_per_row = max(1.0, 1.0 / step_mm)
    px_per_mm = dpi / 25.4
    rows = []
    k = 0
    y_mm = 0.5
    while y_mm * px_per_mm < h:
        py = int(y_mm * px_per_mm)
        line = gray.crop((0, py, w, py + 1)).point(lambda v: 255 if v < 128 else 0)
        box = line.getbbox()
        if box is not None:
            x0 = xmin + box[0] / dpi
            x1 = xmin + box[2] / dpi
            y = ymax - py / dpi
            a, b = bed(x0, y), bed(x1, y)
            rows.append(([a, b] if k % 2 == 0 else [b, a], lines_per_row))
            k += 1
        y_mm += 1.0
    return rows


def total_seconds(steps):
    return sum(s.seconds for s in steps)
