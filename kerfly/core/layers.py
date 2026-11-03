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


def compile_layer(elements, layer, layers):
    """(design, origin) with only this layer's parts of the visible elements,
    keeping the bounds of the whole layout so all layers share one origin."""
    visible = [e for e in elements if e.visible]
    full_bounds, full_origin = layout_frame(visible)
    if full_bounds is None:
        return None, None
    parts = []
    for e in visible:
        if layer_of(e, layer.kind, layers) is layer and part_present(e.design, layer.kind):
            p = e.copy()
            p.design = _part_design(e.design, {layer.kind})
            parts.append(p)
    if not parts:
        return None, full_origin
    if len(visible) == 1 and len(parts) == 1 and visible[0].is_identity:
        return parts[0].design, full_origin       # untransformed single element: pass through
    design, origin = compile_layout(parts)
    if design is not None:
        # same bounds (and so the same job origin) as the whole layout
        if layer.kind == RASTER and design.raster.image is not None and design.bounds != full_bounds:
            design = _expand_raster(design, full_bounds)
        design.bounds = full_bounds
    return design, full_origin


def _expand_raster(design, bounds):
    """Place a layer's raster on a canvas covering the whole layout's bounds."""
    from PIL import Image
    dpi = design.input_dpi
    xmin, xmax, ymin, ymax = bounds
    canvas = Image.new("L", (max(1, int(round((xmax - xmin) * dpi))), max(1, int(round((ymax - ymin) * dpi)))), 255)
    dx = int(round((design.bounds[0] - xmin) * dpi))
    dy = int(round((ymax - design.bounds[3]) * dpi))
    canvas.paste(design.raster.image, (dx, dy))
    out = _part_design(design, set(KINDS))
    out.raster = ECoord()
    out.raster.set_image(canvas)
    return out


def run_order(layers):
    return sorted(layers, key=lambda layer: KINDS.index(layer.kind))


def build_layers_job(elements, layers, settings, progress=None, update_gui=None, stop=None,
                     cache=None):
    """Laser data for all enabled layers. Returns (chunks, origin).

    cache: optional dict {layer.id: design} reused between calls (computed
    raster lines are kept in the designs).
    """
    progress = progress or (lambda m: None)
    chunks, origin = [], None
    joined = None
    for layer in run_order(layers):
        if not layer.enabled:
            continue
        design = cache.get(layer.id) if cache is not None else None
        if design is None:
            design, origin_l = compile_layer(elements, layer, layers)
            if cache is not None and design is not None:
                cache[layer.id] = design
        else:
            origin_l = None
        if design is None:
            continue
        if origin_l is not None:
            origin = origin_l
        s = layer_settings(settings, layer)
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
        design = cache.get(layer.id)
        if design is None:
            design, _o = compile_layer(elements, layer, layers)
            if design is None:
                continue
            cache[layer.id] = design
        times = estimate_times(design, layer_settings(settings, layer))
        out[layer.id] = times.get(OPERATION_OF_KIND[layer.kind])
    return out
