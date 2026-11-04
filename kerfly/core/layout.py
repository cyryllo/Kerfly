"""
Layout of design elements on the laser bed, and compiling them into one job.

Coordinates are bed coordinates in inches, as used for the laser head:
x grows to the right from home, y grows upwards and the bed spans
y in [-bed_height, 0] (home is the upper left corner, y = 0).

An Element is one loaded file (its Design) with a placement: scale, rotation
and the position of the top-left corner of its bounding box on the bed.

compile_layout() merges the elements into one Design for the job generator.
A single element that is not scaled or rotated is passed through unchanged,
so its laser data is byte-identical to loading the file on its own.

Copyright (C) 2026 Kerfly contributors
Licensed under the GNU General Public License v3 or later. See LICENSE.
"""
import math
from dataclasses import dataclass, field

from .design import Design


@dataclass
class Element:
    design: Design            # as loaded; never modified by the layout
    name: str = ""
    x: float = 0.0            # bed position of the bounding box top-left, inches
    y: float = 0.0            # (y <= 0, downwards is negative)
    scale_x: float = 1.0
    scale_y: float = 1.0
    rotation: float = 0.0     # degrees, counter-clockwise
    source_file: str = ""
    load_options: dict = field(default_factory=dict)   # e.g. {"dpi": 300} for images
    visible: bool = True      # hidden elements are not sent to the laser
    shape: object = None      # ShapeSpec for drawn shapes (kerfly.core.shapes), else None
    layers: dict = field(default_factory=dict)   # part kind -> layer id (missing: default layer)

    def placement(self):
        """Placement values (for undo snapshots)."""
        return (self.x, self.y, self.scale_x, self.scale_y, self.rotation, self.visible)

    def set_placement(self, p):
        self.x, self.y, self.scale_x, self.scale_y, self.rotation, self.visible = p

    def copy(self):
        """A new element sharing the same loaded design."""
        e = Element(self.design, self.name, source_file=self.source_file,
                    load_options=dict(self.load_options),
                    shape=self.shape.copy() if self.shape is not None else None,
                    layers=dict(self.layers))
        e.set_placement(self.placement())
        return e

    @property
    def centre(self):
        w, h = self.size
        return self.x + w / 2.0, self.y - h / 2.0

    def set_centre(self, cx, cy):
        w, h = self.size
        self.x, self.y = cx - w / 2.0, cy + h / 2.0

    # ---- geometry --------------------------------------------------
    @property
    def source_size(self):
        xmin, xmax, ymin, ymax = self.design.bounds
        return xmax - xmin, ymax - ymin

    @property
    def is_identity(self):
        return self.scale_x == 1.0 and self.scale_y == 1.0 and self.rotation % 360 == 0

    def _local_transform(self):
        """Function mapping source design coordinates to coordinates relative
        to the rotated, scaled element's centre."""
        xmin, xmax, ymin, ymax = self.design.bounds
        w, h = xmax - xmin, ymax - ymin
        cx, cy = xmin + w / 2.0, ymin + h / 2.0
        a = math.radians(self.rotation)
        c, s = math.cos(a), math.sin(a)
        sx, sy = self.scale_x, self.scale_y

        def f(x, y):
            u = (x - cx) * sx
            v = (y - cy) * sy
            return u * c - v * s, u * s + v * c
        return f

    def _rotated_extent(self):
        """Half width and half height of the bounding box after scale + rotation."""
        w, h = self.source_size
        w, h = w * abs(self.scale_x), h * abs(self.scale_y)
        a = math.radians(self.rotation)
        c, s = abs(math.cos(a)), abs(math.sin(a))
        return (w * c + h * s) / 2.0, (w * s + h * c) / 2.0

    @property
    def size(self):
        """(width, height) of the bounding box on the bed, inches."""
        hw, hh = self._rotated_extent()
        return 2 * hw, 2 * hh

    @property
    def bounds(self):
        """(xmin, xmax, ymin, ymax) on the bed."""
        w, h = self.size
        return self.x, self.x + w, self.y - h, self.y

    def transform(self):
        """Function mapping source design coordinates to bed coordinates."""
        local = self._local_transform()
        hw, hh = self._rotated_extent()
        cx, cy = self.x + hw, self.y - hh

        def f(x, y):
            u, v = local(x, y)
            return cx + u, cy + v
        return f

    def set_size(self, width, height):
        """Scale so the bounding box on the bed is width x height. For rotations
        by multiples of 90 degrees each axis is scaled separately; for other
        angles the element is scaled uniformly to the new width."""
        w0, h0 = self.source_size
        angle = self.rotation % 360
        if w0 <= 0 or h0 <= 0:
            return
        if angle in (0, 180):
            self.scale_x = math.copysign(width / w0, self.scale_x)
            self.scale_y = math.copysign(height / h0, self.scale_y)
        elif angle in (90, 270):
            self.scale_x = math.copysign(height / w0, self.scale_x)
            self.scale_y = math.copysign(width / h0, self.scale_y)
        else:
            cur_w, _h = self.size
            if cur_w > 0:
                self.scale_x *= width / cur_w
                self.scale_y *= width / cur_w


def mirror(element, horizontal=True):
    """Mirror an element on the bed, keeping its centre: horizontal flips left
    and right, otherwise top and bottom. A mirror of a rotated element is the
    same mirror of the unrotated one with the opposite rotation."""
    cx, cy = element.centre
    if horizontal:
        element.scale_x = -element.scale_x
    else:
        element.scale_y = -element.scale_y
    element.rotation = (-element.rotation) % 360
    element.set_centre(cx, cy)


ALIGN_EDGES = ("left", "hcenter", "right", "top", "vcenter", "bottom")


def selection_bounds(elements):
    """(xmin, xmax, ymin, ymax) around all the elements."""
    return (min(e.bounds[0] for e in elements), max(e.bounds[1] for e in elements),
            min(e.bounds[2] for e in elements), max(e.bounds[3] for e in elements))


def align(elements, edge, frame):
    """Move elements so their edge (one of ALIGN_EDGES) lines up with the same
    edge of frame = (xmin, xmax, ymin, ymax) (bed inches, y up)."""
    fx0, fx1, fy0, fy1 = frame
    for e in elements:
        x0, x1, y0, y1 = e.bounds
        if edge == "left":
            e.x += fx0 - x0
        elif edge == "right":
            e.x += fx1 - x1
        elif edge == "hcenter":
            e.x += (fx0 + fx1) / 2.0 - (x0 + x1) / 2.0
        elif edge == "top":
            e.y += fy1 - y1
        elif edge == "bottom":
            e.y += fy0 - y0
        elif edge == "vcenter":
            e.y += (fy0 + fy1) / 2.0 - (y0 + y1) / 2.0
        else:
            raise ValueError(edge)


def distribute(elements, horizontal=True):
    """Spread three or more elements evenly along x (horizontal) or y.

    The two outermost elements stay where they are. The ones between get
    equal gaps between their bounding boxes. When the elements are too wide
    for gaps (they overlap along that axis), their centres are spaced evenly
    instead. Returns ("gap", inches) or ("centres", inches), or None for fewer
    than three elements."""
    if len(elements) < 3:
        return None
    axis = 0 if horizontal else 1

    def lo(e):                     # start along the axis (left, or top measured downwards)
        b = e.bounds
        return b[0] if horizontal else -b[3]

    def hi(e):
        b = e.bounds
        return b[1] if horizontal else -b[2]

    def shift(e, d):               # move forward along the axis by d
        if horizontal:
            e.x += d
        else:
            e.y -= d

    order = sorted(elements, key=lambda e: (lo(e) + hi(e)) / 2.0)
    first, last = order[0], order[-1]
    span = hi(last) - lo(first)
    sizes = sum(e.size[axis] for e in order)
    gap = (span - sizes) / (len(order) - 1)
    if gap >= 0:
        pos = hi(first) + gap
        for e in order[1:-1]:
            shift(e, pos - lo(e))
            pos = hi(e) + gap
        return ("gap", gap)
    c0 = (lo(first) + hi(first)) / 2.0
    step = ((lo(last) + hi(last)) / 2.0 - c0) / (len(order) - 1)
    for n, e in enumerate(order[1:-1], 1):
        shift(e, c0 + n * step - (lo(e) + hi(e)) / 2.0)
    return ("centres", step)


BED_TOLERANCE = 0.002       # inches; rounding of positions typed in mm


def on_bed(element, bed_w, bed_h, tol=BED_TOLERANCE):
    """True when the element's bounding box lies inside the bed (inches;
    x from 0 to bed_w, y from 0 down to -bed_h)."""
    xmin, xmax, ymin, ymax = element.bounds
    return xmin >= -tol and xmax <= bed_w + tol and ymax <= tol and ymin >= -bed_h - tol


def _transform_ecoords(coords, f, loop_offset):
    out = []
    for row in coords:
        x, y = f(row[0], row[1])
        new = [x, y, row[2] + loop_offset]
        new.extend(row[3:])
        out.append(new)
    return out


def _max_loop(coords):
    return max((row[2] for row in coords), default=0)


def _transformed_raster(element, dpi):
    """The element's raster image scaled and rotated as placed, at dpi, with
    white background; returns (image, (left, top) bed position)."""
    from PIL import Image
    im = element.design.raster.image.convert("L")
    src_dpi = element.design.input_dpi
    sx, sy = abs(element.scale_x), abs(element.scale_y)
    size = (max(1, int(round(im.width / src_dpi * sx * dpi))),
            max(1, int(round(im.height / src_dpi * sy * dpi))))
    if size != im.size:
        im = im.resize(size, Image.LANCZOS)
    if element.scale_x < 0:
        im = im.transpose(Image.FLIP_LEFT_RIGHT)
    if element.scale_y < 0:
        im = im.transpose(Image.FLIP_TOP_BOTTOM)
    angle = element.rotation % 360
    if angle:
        exact = {90: Image.ROTATE_90, 180: Image.ROTATE_180, 270: Image.ROTATE_270}
        if angle in exact:
            im = im.transpose(exact[angle])
        else:
            im = im.rotate(angle, resample=Image.BICUBIC, expand=True, fillcolor=255)
    xmin, xmax, ymin, ymax = element.bounds
    return im, (xmin, ymax)


def compile_layout(elements):
    """Merge elements into one Design. Returns (design, origin) where origin is
    the bed position (x, y) of the design's top-left corner, i.e. where the
    laser head must be when the job starts. Returns (None, None) if empty."""
    elements = [e for e in elements if e is not None and e.visible]
    if not elements:
        return None, None
    if len(elements) == 1 and elements[0].is_identity:
        e = elements[0]
        return e.design, (e.x, e.y)

    from PIL import Image
    out = Design()
    out.input_dpi = max(e.design.input_dpi for e in elements)
    xmin = min(e.bounds[0] for e in elements)
    xmax = max(e.bounds[1] for e in elements)
    ymin = min(e.bounds[2] for e in elements)
    ymax = max(e.bounds[3] for e in elements)
    out.bounds = (xmin, xmax, ymin, ymax)

    vcut, veng, gcode = [], [], []
    for e in elements:
        f = e.transform()
        for target, source in ((vcut, e.design.vector_cut.ecoords),
                               (veng, e.design.vector_engrave.ecoords),
                               (gcode, e.design.gcode.ecoords)):
            if source:
                target.extend(_transform_ecoords(source, f, _max_loop(target) + 1 if target else 0))
    if vcut:
        out.vector_cut.set_ecoords(vcut)
    if veng:
        out.vector_engrave.set_ecoords(veng)
    if gcode:
        out.gcode.set_ecoords(gcode, data_sorted=True)

    rasters = [e for e in elements if e.design.raster.image is not None]
    if rasters:
        dpi = out.input_dpi
        canvas = Image.new("L", (max(1, int(round((xmax - xmin) * dpi))),
                                 max(1, int(round((ymax - ymin) * dpi)))), 255)
        for e in rasters:
            im, (left, top) = _transformed_raster(e, dpi)
            px, py = int(round((left - xmin) * dpi)), int(round((ymax - top) * dpi))
            region = canvas.crop((px, py, px + im.width, py + im.height))
            from PIL import ImageChops
            canvas.paste(ImageChops.darker(region, im), (px, py))
        out.raster.set_image(canvas)
    return out, (xmin, ymax)
