"""
G-code for GRBL lasers (File → Save G-code): the same layers, elements and
settings as a K40 job (raster engrave, vector engrave, cut, in that order,
each layer with its speed, power and passes), written as G-code that GRBL
(and senders such as LaserGRBL or UGS) run.

- Millimetres, absolute coordinates (G21 G90); laser mode M4: the power
  follows the speed, so corners do not burn; G0 moves with the laser off.
- Power as S, 0 .. s_max (GRBL's $30, 1000 by default): a layer's power
  0..1 of it.
- Speed as F in mm/min.
- Raster: line by line, back and forth, the laser on only over the dark
  runs, an overscan before and after each line so the head is at speed.
- Air assist (a laser's setting): M8 after the start, M9 at the end (none
  without it: the G-code as before).
- Origin: "lower_left" (X right, Y up from the bed's lower left corner, as
  most GRBL lasers home) or "design" (the design's upper left corner is
  X0 Y0, Y going down negative: set the work origin there on the machine).

Copyright (C) 2026 Kerfly contributors
Licensed under the GNU General Public License v3 or later. See LICENSE.
"""
from dataclasses import dataclass

from .layers import CUT, ENGRAVE, RASTER, compile_layer, element_order, layer_settings, run_order

ORIGINS = ("lower_left", "design")


@dataclass
class GcodeOptions:
    origin: str = "lower_left"
    s_max: int = 1000
    overscan_mm: float = 2.0
    air: bool = False            # air assist: M8 during the job, M9 at its end


def bed_elements(elements, bed_w, home_upper_right):
    """Copies of the visible elements placed from the bed's left edge (an element's x is from the right edge
    with an upper right home)."""
    out = []
    for e in elements:
        if not e.visible:
            continue
        c = e.copy()
        if home_upper_right:
            c.x = bed_w - e.x - e.size[0]
        out.append(c)
    return out


def feed_mm_min(speed, units):
    """A layer's speed (mm/s, or in/min with inch units) in mm/min."""
    return float(speed) * (25.4 if units == "in" else 60.0)


def _fmt(v):
    text = ("%.3f" % v).rstrip("0").rstrip(".")
    return "0" if text in ("-0", "") else text


class _Writer:
    def __init__(self, to_xy):
        self.lines = []
        self.to_xy = to_xy
        self.feed = None
        self.power = None
        self.pos = None                 # where the head is (the G-code's numbers), to skip moves that stay

    def _move(self, code, X, Y, power=None, feed=None):
        x, y = _fmt(X), _fmt(Y)
        if (x, y) == self.pos:
            return                      # no move: nothing to write (the power is set with the next one)
        words = [code, "X" + x, "Y" + y]
        if power is not None and power != self.power:
            words.append("S%d" % power)
            self.power = power
        if feed is not None and feed != self.feed:
            words.append("F%s" % _fmt(feed))
            self.feed = feed
        self.lines.append(" ".join(words))
        self.pos = (x, y)

    def comment(self, text):
        self.lines.append("; " + text)

    def rapid(self, x, y):
        self._move("G0", *self.to_xy(x, y))

    def cut(self, x, y, power, feed):
        self._move("G1", *self.to_xy(x, y), power, feed)

    def cut_mm(self, X, Y, power, feed):
        """A move given in G-code millimetres (raster overscan)."""
        self._move("G1", X, Y, power, feed)

    def rapid_mm(self, X, Y):
        self._move("G0", X, Y)


def _polylines(rows):
    """[x, y, loop] rows -> lists of points, one per loop."""
    out, current, loop = [], [], None
    for x, y, lp in rows:
        if lp != loop and current:
            out.append(current)
            current = []
        loop = lp
        current.append((x, y))
    if current:
        out.append(current)
    return [p for p in out if len(p) > 1]


def _frame(design, origin):
    """design coordinates (inches, y up) -> bed inches (x from the left edge, y <= 0 from the top)."""
    b = design.bounds
    ox, oy = origin

    def to_bed(x, y):
        return ox + (x - b[0]), oy + (y - b[3])
    return to_bed


def build(elements, layers, settings, values, options=None, version="", progress=None):
    """The G-code of the job, as text. elements: the window's elements (inches, x from home); layers: the
    window's layers (enabled ones are run); settings: the window's JobSettings; values: its settings values
    (bed size, units). Raises ValueError when nothing would be lasered."""
    from . import config, raster
    options = options or GcodeOptions()
    progress = progress or (lambda m: None)
    bed_w, bed_h = config.bed_size_inches(values)
    units = values.get("units", "mm")
    on_bed = bed_elements(elements, bed_w, getattr(settings, "home_upper_right", False))
    if not on_bed:
        raise ValueError("Nothing to laser: no element is ticked.")
    top_left = (min(e.bounds[0] for e in on_bed), max(e.bounds[3] for e in on_bed))
    s_max = max(1, int(options.s_max))

    if options.origin == "design":
        def to_xy(x, y):
            return (x - top_left[0]) * 25.4, (y - top_left[1]) * 25.4
    else:
        def to_xy(x, y):
            return x * 25.4, (bed_h + y) * 25.4
    w = _Writer(to_xy)
    w.comment("Kerfly%s, G-code for GRBL lasers" % ((" " + version) if version else ""))
    w.comment("origin: %s; power S 0..%d; units mm" % (
        "the bed's lower left corner" if options.origin != "design" else "the design's upper left corner",
        s_max))
    w.lines += ["G21", "G90", "M4 S0"] + (["M8"] if options.air else [])
    lasered = False
    for layer in run_order(layers):
        if not layer.enabled:
            continue
        design, origin = compile_layer(on_bed, layer, layers)
        if design is None:
            continue
        s = layer_settings(settings, layer)
        feed = feed_mm_min(layer.speed, units)
        power = int(round(max(0.0, min(1.0, float(layer.power))) * s_max))
        to_bed = _frame(design, origin)
        if layer.kind == RASTER:
            raster.make_raster_coords(design, s, progress)
            rows = design.raster.ecoords
            if not rows:
                continue
            lasered = True
            for p in range(max(1, int(layer.passes))):
                w.comment("%s: raster, pass %d" % (layer.name, p + 1))
                _raster(w, design, rows, to_bed, to_xy, power, feed, options.overscan_mm)
        elif layer.kind in (ENGRAVE, CUT):
            part = design.vector_cut if layer.kind == CUT else design.vector_engrave
            if not part.ecoords:
                continue
            rows = part.ecoords
            if s.inside_first:
                ordered = element_order(part, inside_check=layer.kind == CUT,
                                        start=(design.bounds[0], design.bounds[3]))
                if ordered is not None:
                    rows = ordered
            lasered = True
            for p in range(max(1, int(layer.passes))):
                w.comment("%s: %s, pass %d" % (layer.name, "cut" if layer.kind == CUT else "engrave", p + 1))
                for line in _polylines(rows):
                    w.rapid(*to_bed(*line[0]))
                    for pt in line[1:]:
                        w.cut(*to_bed(*pt), power, feed)
    if not lasered:
        raise ValueError("Nothing to laser: no ticked layer has anything on it.")
    w.lines += ["M5 S0"] + (["M9"] if options.air else []) + ["G0 X0 Y0", "M2", ""]
    return "\n".join(w.lines)


def _raster(w, design, rows, to_bed, to_xy, power, feed, overscan_mm):
    """Raster runs ([x, y, loop] pairs, inches in the picture: x from its left edge, y up from its bottom)
    line by line, back and forth, with an overscan; the laser on (S power) only over the runs."""
    b = design.bounds
    lines = {}
    for i in range(0, len(rows) - 1, 2):
        (x0, y0, _l0), (x1, _y1, _l1) = rows[i], rows[i + 1]
        lines.setdefault(round(y0, 6), []).append((x0, x1))
    forward = True
    for y in sorted(lines, reverse=True):                  # from the top of the picture down
        runs = sorted(lines[y])
        if not forward:
            runs = [(x1, x0) for x0, x1 in reversed(runs)]
        # picture coordinates -> design coordinates: its left edge and bottom on the design's bounds
        pts = [((b[0] + a, b[2] + y), (b[0] + c, b[2] + y)) for a, c in runs]
        start = to_xy(*to_bed(*pts[0][0]))
        end = to_xy(*to_bed(*pts[-1][1]))
        step = overscan_mm if forward else -overscan_mm
        w.rapid_mm(start[0] - step, start[1])
        w.cut_mm(start[0], start[1], 0, feed)
        for (p0, p1) in pts:
            X0, Y0 = to_xy(*to_bed(*p0))
            X1, Y1 = to_xy(*to_bed(*p1))
            w.cut_mm(X0, Y0, 0, feed)
            w.cut_mm(X1, Y1, power, feed)
        w.cut_mm(end[0] + step, end[1], 0, feed)
        forward = not forward


def trace(elements, settings, values, options=None, with_laser=False, power=0.0, feed=3000.0, gap_mm=0.0):
    """The boundary trace as G-code: the rectangle round the ticked elements (gap_mm further out), from the
    design's upper left corner (the job's X0 Y0; options.origin "design") or on the bed; the laser off (G0)
    or on at `power` (0..1) and `feed` mm/min."""
    from . import config
    options = options or GcodeOptions(origin="design")
    bed_w, bed_h = config.bed_size_inches(values)
    on_bed = bed_elements(elements, bed_w, getattr(settings, "home_upper_right", False))
    if not on_bed:
        raise ValueError("Nothing to laser: no element is ticked.")
    g = gap_mm / 25.4
    x0 = min(e.bounds[0] for e in on_bed) - g
    x1 = max(e.bounds[1] for e in on_bed) + g
    y0 = min(e.bounds[2] for e in on_bed) - g
    y1 = max(e.bounds[3] for e in on_bed) + g
    left, top = x0 + g, y1 - g                       # the design's upper left corner: X0 Y0 of the job
    if options.origin == "design":
        def to_xy(x, y):
            return (x - left) * 25.4, (y - top) * 25.4
    else:
        def to_xy(x, y):
            return x * 25.4, (bed_h + y) * 25.4
    w = _Writer(to_xy)
    w.comment("Kerfly: boundary trace")
    air = options.air and with_laser                 # air assist only when the laser burns along it
    w.lines += ["G21", "G90", "M4 S0"] + (["M8"] if air else [])
    corners = [(x0, y1), (x1, y1), (x1, y0), (x0, y0), (x0, y1)]
    w.rapid(*corners[0])
    s = int(round(max(0.0, min(1.0, power)) * max(1, int(options.s_max))))
    for c in corners[1:]:
        if with_laser:
            w.cut(*c, s, feed)
        else:
            X, Y = to_xy(*c)
            w.lines.append("G1 X%s Y%s S0 F%s" % (_fmt(X), _fmt(Y), _fmt(feed)))
    back = "G0 X0 Y0" if options.origin == "design" else "G0 X%s Y%s" % tuple(_fmt(v) for v in to_xy(left, top))
    w.lines += ["M5 S0"] + (["M9"] if air else []) + [back]
    return "\n".join(w.lines) + "\n"
