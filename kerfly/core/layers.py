"""
Layers: groups of design parts that are cut or engraved with the same speed,
passes and power (like LightBurn's layers).

Every element has up to four parts: its raster image, vector engrave lines,
vector cut lines and G-code paths. Each part is assigned to a layer of the
matching kind; by default the first layer of that kind.

build_layers_job() runs the job generator once per layer and joins the
results exactly the way K40 Whisperer joins its raster / engrave / cut
stages, so with the three default layers the laser data is byte-identical
to a job built without layers.

Copyright (C) 2026 Kerfly contributors
Licensed under the GNU General Public License v3 or later. See LICENSE.
"""
import itertools
from dataclasses import dataclass, field, replace

from ecoords import ECoord

from . import job, raster
from .design import Design
from .estimate import estimate_times
from .layout import compile_layout

RASTER, ENGRAVE, CUT, GCODE = "raster", "engrave", "cut", "gcode"
KINDS = (RASTER, ENGRAVE, CUT, GCODE)            # also the order layers are run in
OPERATION_OF_KIND = {RASTER: job.RASTER_ENG, ENGRAVE: job.VECTOR_ENG, CUT: job.VECTOR_CUT,
                     GCODE: job.GCODE_CUT}
DEFAULT_COLORS = {RASTER: "#000000", ENGRAVE: "#1565c0", CUT: "#d32f2f", GCODE: "#6a1b9a"}
EXTRA_COLORS = ["#2e7d32", "#ef6c00", "#00838f", "#ad1457", "#6d4c41", "#5e35b1", "#9e9d24"]

_ids = itertools.count(1)


@dataclass
class Layer:
    kind: str                     # raster / engrave / cut / gcode
    name: str = ""
    color: str = ""
    speed: float = 10.0           # in the user's units (mm/s or in/min); unused for gcode
    passes: int = 1
    power: float = 0.5            # fraction of max power (M3 boards)
    enabled: bool = True
    kerf: float = 0.0             # mm, cut layers: closed outlines move out by half of it (holes in)
    id: int = field(default_factory=lambda: next(_ids))

    def copy(self):
        return replace(self)


def default_layers():
    return [Layer(RASTER, color=DEFAULT_COLORS[RASTER], speed=100.0),
            Layer(ENGRAVE, color=DEFAULT_COLORS[ENGRAVE], speed=20.0),
            Layer(CUT, color=DEFAULT_COLORS[CUT], speed=10.0),
            Layer(GCODE, color=DEFAULT_COLORS[GCODE])]


def part_present(design, kind):
    if kind == RASTER:
        return design.raster.image is not None
    if kind == ENGRAVE:
        return bool(design.vector_engrave.ecoords)
    if kind == CUT:
        return bool(design.vector_cut.ecoords)
    return bool(design.gcode.ecoords)


def layer_of(element, kind, layers):
    """The layer an element's part of this kind goes to."""
    wanted = getattr(element, "layers", {}).get(kind)
    first = None
    for layer in layers:
        if layer.kind != kind:
            continue
        if layer.id == wanted:
            return layer
        if first is None:
            first = layer
    return first


def _part_design(design, kinds):
    """A Design sharing design's data, with only the parts of the given kinds."""
    d = Design()
    d.input_dpi = design.input_dpi
    d.bounds = design.bounds
    d.raster = design.raster if RASTER in kinds else ECoord()
    d.vector_engrave = design.vector_engrave if ENGRAVE in kinds else ECoord()
    d.vector_cut = design.vector_cut if CUT in kinds else ECoord()
    d.gcode = design.gcode if GCODE in kinds else ECoord()
    return d


def layer_settings(settings, layer):
    """Job settings with the layer's speed, passes and power."""
    if layer.kind == RASTER:
        return replace(settings, raster_feed=layer.speed, raster_passes=layer.passes, raster_power=layer.power)
    if layer.kind == ENGRAVE:
        return replace(settings, vengrave_feed=layer.speed, vengrave_passes=layer.passes,
                       vengrave_power=layer.power)
    if layer.kind == CUT:
        return replace(settings, vcut_feed=layer.speed, vcut_passes=layer.passes, vcut_power=layer.power)
    return replace(settings, gcode_passes=layer.passes, gcode_power=layer.power)


def layout_frame(visible):
    """(bounds, origin) of the whole layout in the coordinates compile_layout
    uses, without building any data: a single untransformed element keeps its
    own design coordinates, several elements use bed coordinates."""
    if not visible:
        return None, None
    if len(visible) == 1 and visible[0].is_identity:
        e = visible[0]
        return e.design.bounds, (e.x, e.y)
    xmin = min(e.bounds[0] for e in visible)
    xmax = max(e.bounds[1] for e in visible)
    ymin = min(e.bounds[2] for e in visible)
    ymax = max(e.bounds[3] for e in visible)
    return (xmin, xmax, ymin, ymax), (xmin, ymax)


_kerf_cache = {}


def _kerf_cut(element, part, kerf_mm):
    """The element's cut part with kerf compensation: closed outlines moved out by
    half the kerf (holes in), so the parts come out at their drawn size. A drawn
    shape is rebuilt with its outline moved before the bridges are cut; an opened
    file has its closed loops moved. Scaled elements: the kerf is on the bed."""
    from . import offset
    scale = (abs(element.scale_x) + abs(element.scale_y)) / 2.0 or 1.0
    half_mm = kerf_mm / 2.0 / scale
    # a drawn shape by its settings; a file by its design (kept in the cache, so its id stays unique)
    key = (id(element.design), repr(element.shape), round(half_mm, 6))
    cached = _kerf_cache.get(key)
    cut = cached[1] if cached is not None and cached[0] is element.design else None
    if cut is None:
        if not offset.available():
            return part.vector_cut
        cut = ECoord()
        if element.shape is not None and element.shape.operation == "cut":
            from .shapes import build_design
            cut = build_design(element.shape, cut_offset_mm=half_mm).vector_cut
        else:
            cut.set_ecoords(offset.offset_ecoord_loops(part.vector_cut.ecoords, half_mm / 25.4))
        if len(_kerf_cache) > 300:
            _kerf_cache.clear()
        _kerf_cache[key] = (element.design, cut)
    return cut


def compile_layer(elements, layer, layers):
    """(design, origin) with only this layer's parts of the visible elements,
    in the frame of the whole layout so all layers share one origin."""
    visible = [e for e in elements if e.visible]
    full_bounds, full_origin = layout_frame(visible)
    if full_bounds is None:
        return None, None
    parts = []
    for e in visible:
        if layer_of(e, layer.kind, layers) is layer and part_present(e.design, layer.kind):
            p = e.copy()
            p.design = _part_design(e.design, {layer.kind})
            if layer.kind == CUT and getattr(layer, "kerf", 0.0) > 0:
                p.design.vector_cut = _kerf_cut(e, p.design, float(layer.kerf))
            parts.append(p)
    if not parts:
        return None, full_origin
    if len(visible) == 1 and len(parts) == 1 and visible[0].is_identity:
        return parts[0].design, full_origin       # untransformed single element: pass through
    # the frame of the whole layout (a lone untransformed part must not keep its own
    # design coordinates: it would be cut at the wrong place)
    design, _origin = compile_layout(parts, passthrough=False, frame=full_bounds)
    return design, full_origin


def element_order(ecoord, inside_check, start=None):
    """Rows of a layer built from the element list, in the order of that list:
    each element's own paths are ordered as K40 Whisperer does (inside shapes
    first, short travel), but the elements are not mixed, so they are cut in
    the order the user set. Loop numbers stay unique. With `start` (the head
    position, design coordinates) an open line is cut from its end nearer to
    the head. None when the data do not come from the element list (a single
    opened file: K40 Whisperer's order, byte-identical)."""
    from .pathopt import optimize_paths
    import copy
    starts = getattr(ecoord, "element_starts", None)
    rows = ecoord.ecoords
    if not starts or not rows:
        return None
    out = []
    for a, b in zip(starts, starts[1:] + [len(rows)]):
        part = copy.deepcopy(rows[a:b])
        if not part:
            continue
        part = optimize_paths(part, inside_check=inside_check)
        base = min(r[2] for r in part)
        offset = (max(r[2] for r in out) + 1) if out else 0
        for r in part:
            out.append([r[0], r[1], r[2] - base + offset] + list(r[3:]))
    if start is not None:
        out = _open_lines_from_near_end(out, start)
    return out


def _open_lines_from_near_end(rows, start):
    """Reverse each open line (first point != last) whose far end is nearer to
    where the head is: no run along the line to its other end first."""
    import math
    loops = []
    for r in rows:
        if loops and loops[-1][0][2] == r[2]:
            loops[-1].append(r)
        else:
            loops.append([r])
    out = []
    head = start
    for loop in loops:
        first, last = loop[0], loop[-1]
        closed = math.hypot(first[0] - last[0], first[1] - last[1]) < 1e-6
        if not closed and math.hypot(last[0] - head[0], last[1] - head[1]) \
                < math.hypot(first[0] - head[0], first[1] - head[1]):
            loop = loop[::-1]
        out.extend(loop)
        head = (loop[-1][0], loop[-1][1])
    return out


def run_order(layers):
    return sorted(layers, key=lambda layer: KINDS.index(layer.kind))


def _signature(elements, layer=None, layers=None):
    """What a compiled design depends on: every visible element (its loaded
    design, place, size, turn) and, for a layer, which of them go to it."""
    parts = []
    for e in elements:
        if not e.visible:
            continue
        target = None
        if layer is not None:
            found = layer_of(e, layer.kind, layers)
            target = found.id if found is not None else None
        parts.append((id(e.design), e.placement(), target))
    head = None if layer is None else (layer.id, layer.kind, round(float(getattr(layer, "kerf", 0.0)), 6))
    return head, tuple(parts)


def cached_layer(cache, elements, layer, layers):
    """(design, origin) of a layer, reused from cache only when it was compiled
    from exactly these elements, places and layer choices (origin None then).
    A design compiled from other elements was sent to the laser after a new
    file was opened, an element moved to another layer or left out of the job.
    The cache keeps the loaded designs alive, so their ids stay unique."""
    sig = _signature(elements, layer, layers)
    hit = cache.get(layer.id) if cache is not None else None
    if hit is not None and hit[0] == sig:
        return hit[1], None
    design, origin = compile_layer(elements, layer, layers)
    if cache is not None:
        if design is not None:
            cache[layer.id] = (sig, design, [e.design for e in elements if e.visible])
        else:
            cache.pop(layer.id, None)
    return design, origin


def build_layers_job(elements, layers, settings, progress=None, update_gui=None, stop=None,
                     cache=None):
    """Laser data for all enabled layers. Returns (chunks, origin).

    cache: optional dict {layer.id: (signature, design, kept)} reused between
    calls while the elements stay the same (computed raster lines are kept in
    the designs); see cached_layer.
    """
    progress = progress or (lambda m: None)
    chunks, origin = [], None
    joined = None
    for layer in run_order(layers):
        if not layer.enabled:
            continue
        design, origin_l = cached_layer(cache, elements, layer, layers)
        if design is None:
            continue
        if origin_l is not None:
            origin = origin_l
        s = layer_settings(settings, layer)
        if s.inside_first and layer.kind in (CUT, ENGRAVE):
            part = design.vector_cut if layer.kind == CUT else design.vector_engrave
            if not part.sorted:
                # the head starts at the design's top-left corner (rotated / mirrored jobs: no turning)
                start = None if (s.rotate or s.mirror) else (design.bounds[0], design.bounds[3])
                rows = element_order(part, inside_check=layer.kind == CUT, start=start)
                if rows is not None:
                    part.set_ecoords(rows, data_sorted=True)
                    part.sorted = True        # what build_job checks (set_ecoords only sets data_sorted)
        if layer.kind == RASTER:
            raster.make_raster_coords(design, s, progress, stop)
            if not design.raster.ecoords:
                continue
        try:
            part = job.build_job(design, s, OPERATION_OF_KIND[layer.kind], progress=progress,
                                 update_gui=update_gui, stop=stop)
        except job.NoLaserData:
            continue
        for c in part:
            c.stage = layer.name or c.stage
        if settings.power_per_stage:
            chunks.extend(part)
        elif joined is None:
            joined = part[0]
        else:
            # same joining as K40 Whisperer between stages: '@' continues the job
            if len(joined.data) > 4:
                joined.data[-4] = ord("@")
            joined.data.extend(part[0].data[1:])
            r = job.Reach()
            r.merge(joined.reach)
            r.merge(part[0].reach)
            joined.reach = r.box
    if not settings.power_per_stage and joined is not None:
        chunks = [joined]
    if not chunks:
        raise job.NoLaserData("No laser data was generated.")
    if origin is None:
        _b, origin = layout_frame([e for e in elements if e.visible])
    return chunks, origin


def layer_times(elements, layers, settings, cache):
    """{layer.id: seconds or None (raster not prepared yet)} for layers with data."""
    out = {}
    for layer in layers:
        design, _o = cached_layer(cache, elements, layer, layers)
        if design is None:
            continue
        times = estimate_times(design, layer_settings(settings, layer))
        out[layer.id] = times.get(OPERATION_OF_KIND[layer.kind])
    return out
