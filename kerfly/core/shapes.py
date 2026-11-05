"""
Shapes drawn in Kerfly: rectangle, ellipse, regular polygon, line, polyline
(open or closed) and text.

A ShapeSpec describes a shape and what the laser does with it. build_design()
turns it into a Design (the same data a loaded file produces), so drawn
shapes are ordinary elements on the bed.

Operations:
    "cut"      outline as vector cut (red)
    "engrave"  outline as vector engrave (blue)
    "hatch"    area filled with parallel engraved lines (vector engrave)
    "fill"     area filled as a raster engraving (even-odd rule, so letters
               like "O" keep their holes)

A closed cut or outline shape can also get a pattern fill (fill_pattern,
kerfly.core.patterns): engraved lines inside it, as an extra vector engrave
part, so the outline keeps its own layer (for example: the edge is cut, the
inside gets engraved waves). fill_outline=False leaves the outline out.

Units: millimetres in the spec; designs are in inches, y up, as everywhere in
the core.

Copyright (C) 2026 Kerfly contributors
Licensed under the GNU General Public License v3 or later. See LICENSE.
"""
import math
from dataclasses import dataclass, field, replace

from .design import Design

MM = 25.4
FILL_DPI = 1000.0

KINDS = ("rectangle", "ellipse", "polygon", "line", "polyline", "path", "text")
OPERATIONS = ("cut", "engrave", "hatch", "fill")


@dataclass
class ShapeSpec:
    kind: str = "rectangle"
    width: float = 20.0           # mm (for "line": the end point relative to the start)
    height: float = 20.0          # mm
    operation: str = "cut"
    hatch_spacing: float = 0.5    # hatch: distance between lines, mm
    hatch_angle: float = 45.0     # hatch: line direction, degrees counter-clockwise
    hatch_cross: bool = False     # hatch: second set of lines at 90 degrees
    # pattern fill of a closed cut / outline shape (kerfly.core.patterns); "" = none
    fill_pattern: str = ""
    fill_spacing: float = 2.0     # mm: distance between the lines / size of one repeat
    fill_angle: float = 0.0       # degrees counter-clockwise
    fill_margin: float = 0.0      # mm kept free inside the outline
    fill_outline: bool = True     # the outline is cut / engraved too
    tabs: int = 0                 # cut: bridges per closed outline that hold the part in the sheet
    tab_width: float = 1.0        # cut: width of each bridge, mm
    corner_radius: float = 0.0    # rectangle, mm
    sides: int = 6                # polygon
    text: str = "Kerfly"          # text
    font_family: str = "DejaVu Sans"
    font_size: float = 10.0       # text: em height, mm
    bold: bool = False
    italic: bool = False
    # text outlines (list of closed polylines, mm, y down) produced by the GUI
    # from the font; kept so the design can be rebuilt without the GUI
    text_outlines: list = field(default_factory=list)
    # text on a path: the path (mm, y down, in the same frame as text_outlines), where the
    # text starts along it (mm) and whether it runs the other way (on the other side)
    text_path: list = field(default_factory=list)
    text_path_offset: float = 0.0
    text_path_flip: bool = False
    # polyline: corner points (mm, y down, relative to the top-left of their
    # bounding box) and whether the last point joins the first
    points: list = field(default_factory=list)
    closed_path: bool = False
    # path: subpaths of lines and Bezier curves (kerfly.core.curves), mm, y down
    subpaths: list = field(default_factory=list)

    def copy(self):
        from .curves import copy_path
        return replace(self, text_outlines=[list(p) for p in self.text_outlines],
                       text_path=[tuple(p) for p in self.text_path],
                       points=[tuple(p) for p in self.points], subpaths=copy_path(self.subpaths))

    @property
    def closed(self):
        if self.kind == "polyline":
            return self.closed_path
        if self.kind == "path":
            from .curves import all_closed
            return all_closed(self.subpaths)
        return self.kind != "line"


def _ellipse_points(w, h, segments=None):
    rx, ry = w / 2.0, h / 2.0
    if segments is None:
        # about 0.1 mm chord error, at least 32 segments
        r = max(rx, ry, 0.01)
        segments = max(32, min(720, int(math.ceil(math.pi / math.acos(max(-1.0, 1 - 0.1 / r))))))
    return [(rx + rx * math.cos(2 * math.pi * i / segments),
             ry + ry * math.sin(2 * math.pi * i / segments)) for i in range(segments)]


def _rounded_rect_points(w, h, r):
    r = max(0.0, min(r, w / 2.0, h / 2.0))
    if r <= 0:
        return [(0, 0), (w, 0), (w, h), (0, h)]
    pts = []
    n = max(4, int(math.ceil(r * 2)))          # segments per corner
    for cx, cy, a0 in ((w - r, r, -90), (w - r, h - r, 0), (r, h - r, 90), (r, r, 180)):
        for i in range(n + 1):
            a = math.radians(a0 + 90.0 * i / n)
            pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return pts


def _polygon_points(w, h, sides):
    sides = max(3, int(sides))
    pts = [(math.cos(-math.pi / 2 + 2 * math.pi * i / sides), math.sin(-math.pi / 2 + 2 * math.pi * i / sides))
           for i in range(sides)]
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    sx = w / (max(xs) - min(xs))
    sy = h / (max(ys) - min(ys))
    return [((x - min(xs)) * sx, (y - min(ys)) * sy) for x, y in pts]


def outlines(spec):
    """Polylines of the shape in mm, y down, top-left of the shape at (0, 0).
    Closed polylines repeat their first point at the end."""
    w, h = abs(spec.width), abs(spec.height)
    if spec.kind == "rectangle":
        polys = [_rounded_rect_points(w, h, spec.corner_radius)]
    elif spec.kind == "ellipse":
        polys = [_ellipse_points(w, h)]
    elif spec.kind == "polygon":
        polys = [_polygon_points(w, h, spec.sides)]
    elif spec.kind == "line":
        x0 = 0.0 if spec.width >= 0 else w
        y0 = 0.0 if spec.height >= 0 else h
        return [[(x0, y0), (x0 + spec.width, y0 + spec.height)]]
    elif spec.kind == "polyline":
        pts = [tuple(p) for p in spec.points]
        if len(pts) < 2:
            return []
        return [pts + [pts[0]]] if spec.closed_path and len(pts) >= 3 else [pts]
    elif spec.kind == "path":
        from .curves import flatten
        return flatten(spec.subpaths)
    elif spec.kind == "text":
        polys = [list(p) for p in spec.text_outlines]
    else:
        raise ValueError(spec.kind)
    return [p + [p[0]] for p in polys if len(p) >= 2]


def with_tabs(poly, count, width):
    """A closed polyline (first point repeated at the end) cut into open pieces,
    leaving `count` gaps of `width` spread evenly along it (bridges)."""
    if count <= 0 or width <= 0 or len(poly) < 3:
        return [poly]
    lengths = [math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(poly, poly[1:])]
    total = sum(lengths)
    if total <= count * width * 1.5:
        return [poly]                          # too small for its bridges: leave it whole
    step = total / count
    gaps = [(step * (k + 0.5) - width / 2.0, step * (k + 0.5) + width / 2.0) for k in range(count)]

    def point_at(d):
        acc = 0.0
        for (a, b), l in zip(zip(poly, poly[1:]), lengths):
            if acc + l >= d and l > 0:
                t = (d - acc) / l
                return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)
            acc += l
        return poly[-1]
    # pieces between gaps: from the end of one gap to the start of the next (wrapping round)
    pieces = []
    for k in range(count):
        start = gaps[k][1]
        end = gaps[(k + 1) % count][0] + (total if k == count - 1 else 0.0)
        pts = [point_at(start % total)]
        acc = 0.0
        for idx, l in enumerate(lengths * 2):
            acc += l
            if start < acc < end:
                pts.append(poly[(idx + 1) % (len(poly) - 1)] if idx + 1 >= len(poly) - 1 else poly[idx + 1])
        pts.append(point_at(end % total if end > total else end))
        pieces.append(pts)
    return pieces


def _bounds_mm(polys):
    xs = [x for p in polys for x, _ in p]
    ys = [y for p in polys for _, y in p]
    if not xs:
        return 0.0, 0.0, 0.0, 0.0
    return min(xs), max(xs), min(ys), max(ys)


def _fill_image(polys, x0, y0, w, h, dpi=FILL_DPI):
    """Raster of the filled polygons (even-odd), white background."""
    from PIL import Image, ImageChops, ImageDraw
    size = (max(1, int(round(w / MM * dpi))), max(1, int(round(h / MM * dpi))))
    k = dpi / MM
    mask = Image.new("1", size, 0)
    for p in polys:
        layer = Image.new("1", size, 0)
        ImageDraw.Draw(layer).polygon([((x - x0) * k, (y - y0) * k) for x, y in p], fill=1)
        mask = ImageChops.logical_xor(mask, layer)
    return ImageChops.invert(mask.convert("L"))


def has_pattern_fill(spec):
    """A pattern fill applies: closed shape, cut or outline, a known pattern."""
    from .patterns import PATTERN_CODES
    return bool(spec.fill_pattern) and spec.fill_pattern in PATTERN_CODES and spec.closed \
        and spec.operation in ("cut", "engrave")


def build_design(spec):
    """Design for a shape. Bounds are the shape's bounding box."""
    polys = outlines(spec)
    design = Design()
    xmin, xmax, ymin, ymax = _bounds_mm(polys)
    if spec.kind in ("line", "polyline", "path") and (xmax - xmin) < 1e-9 and (ymax - ymin) < 1e-9:
        return design
    # design coordinates: inches, y up, top-left of the bounding box at (0, h)
    h_in = (ymax - ymin) / MM

    def to_design(x, y):
        return (x - xmin) / MM, h_in - (y - ymin) / MM

    if spec.operation == "hatch" and spec.closed:
        from .hatch import hatch_lines
        segments = []
        spacing = max(0.02, float(spec.hatch_spacing))
        # y down in the shape, so a positive angle turns counter-clockwise on the bed
        for (x1, y1), (x2, y2) in hatch_lines(polys, spacing, -spec.hatch_angle, spec.hatch_cross):
            a, b = to_design(x1, y1), to_design(x2, y2)
            segments.append([a[0], a[1], b[0], b[1]])
        design.vector_engrave.make_ecoords(segments, scale=1.0)
    elif spec.operation == "fill" and spec.closed:
        design.input_dpi = FILL_DPI
        design.raster.set_image(_fill_image(polys, xmin, ymin, xmax - xmin, ymax - ymin))
    else:
        segments = []
        fill_segments = []
        if has_pattern_fill(spec):
            from .patterns import pattern_lines
            # y down in the shape, so a positive angle turns counter-clockwise on the bed
            for line in pattern_lines(spec.fill_pattern, polys, max(0.05, float(spec.fill_spacing)),
                                      -float(spec.fill_angle), max(0.0, float(spec.fill_margin))):
                pts = [to_design(x, y) for x, y in line]
                for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
                    fill_segments.append([x1, y1, x2, y2])
            if not spec.fill_outline:
                polys = []
        if spec.operation == "cut" and spec.tabs > 0:
            pieces = []
            for p in polys:
                closed_poly = len(p) > 2 and p[0] == p[-1]
                pieces += with_tabs(p, int(spec.tabs), float(spec.tab_width)) if closed_poly else [p]
            polys = pieces
        for p in polys:
            pts = [to_design(x, y) for x, y in p]
            for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
                segments.append([x1, y1, x2, y2])
        if spec.operation in ("engrave", "hatch"):
            segments += fill_segments                   # outline and fill on the same outline layer
            fill_segments = []
            design.vector_engrave.make_ecoords(segments, scale=1.0)
        else:
            design.vector_cut.make_ecoords(segments, scale=1.0)
        if fill_segments:                               # cut outline: the fill is a separate engrave part
            design.vector_engrave.make_ecoords(fill_segments, scale=1.0)
    design.bounds = (0.0, (xmax - xmin) / MM, 0.0, h_in)
    return design


def element_contains(element, x, y):
    """Whether the bed point (x, y) (inches, y up) lies inside the closed
    outlines of a drawn element (even-odd: not in its holes)."""
    spec = element.shape
    if spec is None or not spec.closed:
        return False
    polys = [p for p in outlines(spec) if len(p) > 2]
    if not polys:
        return False
    xmin, _xmax, ymin, ymax = _bounds_mm(polys)
    h_in = (ymax - ymin) / MM
    f = element.transform()
    inside = False
    for poly in polys:
        pts = [f((px - xmin) / MM, h_in - (py - ymin) / MM) for px, py in poly]
        for (x1, y1), (x2, y2) in zip(pts, pts[1:] + pts[:1]):
            if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
                inside = not inside
    return inside
