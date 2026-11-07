#!/usr/bin/env python3
"""
Runs the GUI-independent kerfly.core directly (no Tk, no display) and checks
that it produces the same EGV bytes as the baseline recorded from the
unmodified K40 Whisperer 0.71.

Usage:
    .venv/bin/python tests/test_core.py
"""
import hashlib
import json
import os
import shutil
import sys
import tempfile
from dataclasses import replace

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(TESTS_DIR)
sys.path.insert(0, ROOT_DIR)
sys.path.insert(0, TESTS_DIR)

from kerfly.core.design import Design          # noqa: E402
from kerfly.core.settings import JobSettings   # noqa: E402
from kerfly.core import config, job, loaders, raster  # noqa: E402
from regression import synthetic_image, SVG, DXF, NGC, MANIFEST  # noqa: E402

INKSCAPE = shutil.which("inkscape")

# baseline case name -> (source, operation, JobSettings overrides)
CASES = {
    "png_reng_halftone":      ("png", "Raster_Eng", {}),
    "png_reng_grayscale":     ("png", "Raster_Eng", {"halftone": False}),
    "png_reng_negate":        ("png", "Raster_Eng", {"negate": True}),
    "png_reng_rotate_mirror": ("png", "Raster_Eng", {"rotate": True, "mirror": True}),
    "png_reng_up_step":       ("png", "Raster_Eng", {"engrave_up": True, "raster_step": 0.004}),
    "png_reng_feed":          ("png", "Raster_Eng", {"raster_feed": 200.0}),
    "ngc_gcode":              ("ngc", "Gcode_Cut",  {}),
    "dxf_vcut":               ("dxf", "Vector_Cut", {}),
    "dxf_veng":               ("dxf", "Vector_Eng", {}),
    "svg_vcut":               ("svg", "Vector_Cut", {}),
    "svg_raster_vector_cut":  ("svg", "Raster_Eng+Vector_Eng+Vector_Cut", {}),
    "svg_vcut_no_inside_first": ("svg", "Vector_Cut", {"inside_first": False}),
    "svg_all_b1":             ("svg", "Raster_Eng+Vector_Eng+Vector_Cut", {"board_name": "LASER-B1"}),
}

# Settings given as a K40 Whisperer settings file (upstream spacing quirks
# included), read back through kerfly.core.config.
SETTINGS_FILE_CASES = {
    "svg_vcut_rotate_mirror": ("svg", "Vector_Cut", [
        "( K40 Whisperer Settings: 0.71 )",
        "(k40_whisperer_set mirror        1 )",
        "(k40_whisperer_set rotate        1 )",
        "(k40_whisperer_set designfile    \"/tmp/rotate/mirror/halftone.svg\" )",
    ]),
    "svg_vcut_passes2": ("svg", "Vector_Cut", [
        "(k40_whisperer_set Vcut_passes   2 )",
        "(k40_whisperer_set rapid_feed   0.0 )",
    ]),
    "png_reng_up_step": ("png", "Raster_Eng", [
        "(k40_whisperer_set engraveUP     1 )",
        "(k40_whisperer_set rast_step     0.004 )",
    ]),
}


def load_png(design):
    im = synthetic_image()
    design.reset()
    design.input_dpi = 1000.0
    w, h = im.size
    design.bounds = (0.0, w / design.input_dpi, 0.0, h / design.input_dpi)
    design.raster.set_image(im)


def run_case(name, source, operation, settings, baseline):
    design = Design()
    if source == "png":
        load_png(design)
    elif source == "ngc":
        loaders.load_gcode(NGC, design)
    elif source == "dxf":
        loaders.load_dxf(DXF, design)
    elif source == "svg":
        loaders.load_svg(SVG, design, inkscape_path=INKSCAPE)
    if "Raster_Eng" in operation:
        raster.make_raster_coords(design, settings)
    chunks = job.build_job(design, settings, operation)
    data = job.egv_file_bytes(chunks[0].data)
    digest = hashlib.sha256(data).hexdigest()
    if digest == baseline[name]["sha256"]:
        print("OK    %-26s %8d B" % (name, len(data)))
        return 0
    print("DIFF  %-26s %8d B (baseline %d B)" % (name, len(data), baseline[name]["size"]))
    return 1


def test_settings_file():
    """Round trip and parsing quirks of the settings file."""
    errors = []
    values = {"mirror": True, "rotate": 0, "Vcut_feed": "12.5", "Gcode_power": "0.4",
              "designfile": "/home/u/mirror rotate/a b.svg", "units": "mm"}
    lines = config.format_settings(values, "test")
    back = config.parse_settings(lines)
    expected = {"mirror": "1", "rotate": "0", "Vcut_feed": "12.5", "Gcode_power": "0.4",
                "designfile": "/home/u/mirror rotate/a b.svg", "units": "mm"}
    if back != expected:
        errors.append("round trip: %r" % back)
    s = config.job_settings_from_values(back)
    if not (s.mirror and not s.rotate and s.vcut_feed == 12.5 and s.gcode_power == 0.4):
        errors.append("job settings: %r" % s)
    try:
        config.job_settings_from_values({"Vcut_feed": "abc"})
        errors.append("invalid number accepted")
    except ValueError as e:
        if "Vcut_feed" not in str(e):
            errors.append("error does not name the setting: %s" % e)
    if config.job_settings_from_values({}) != JobSettings():
        errors.append("empty settings differ from defaults")
    for e in errors:
        print("ERROR settings file: " + e)
    if not errors:
        print("OK    settings file parse/format/round trip")
    return len(errors)


def test_images(baseline):
    """Bitmap import: a 1000 dpi PNG must give exactly the baseline laser data;
    transparency, resolution and EXIF orientation are handled."""
    from PIL import Image
    errors = 0
    tmp = tempfile.mkdtemp()
    png = os.path.join(tmp, "synthetic.png")
    synthetic_image().save(png, dpi=(1000, 1000))
    w, h, dpi = loaders.read_image_info(png)
    for name, overrides in (("png_reng_halftone", {}), ("png_reng_grayscale", {"halftone": False}),
                            ("png_reng_negate", {"negate": True})):
        design = Design()
        loaders.load_image(png, design, dpi)
        settings = JobSettings(**overrides)
        raster.make_raster_coords(design, settings)
        data = job.egv_file_bytes(job.build_job(design, settings, "Raster_Eng")[0].data)
        ok = hashlib.sha256(data).hexdigest() == baseline[name]["sha256"]
        print("%-5s image import %-17s == baseline" % ("OK" if ok else "DIFF", name))
        errors += 0 if ok else 1

    # transparency counts as white; 300 dpi image is resampled to 1000 dpi
    rgba = Image.new("RGBA", (300, 150), (0, 0, 0, 0))
    for x in range(100):
        for y in range(150):
            rgba.putpixel((x, y), (0, 0, 0, 255))
    path = os.path.join(tmp, "alpha.png")
    rgba.save(path, dpi=(300, 300))
    design = Design()
    loaders.load_image(path, design, loaders.read_image_info(path)[2])
    im = design.raster.image
    ok = (im.size == (1000, 500) and im.getpixel((100, 250)) == 0 and im.getpixel((900, 250)) == 255
          and abs(design.bounds[1] - 1.0) < 1e-9 and abs(design.bounds[3] - 0.5) < 1e-9)
    print("%-5s image import: transparency is white, 300 dpi -> 1 x 0.5 in at 1000 dpi" % ("OK" if ok else "FAIL"))
    errors += 0 if ok else 1

    # EXIF orientation 6 (rotate 90 degrees) swaps width and height
    jpg = os.path.join(tmp, "rotated.jpg")
    exif = Image.Exif()
    exif[0x0112] = 6
    Image.new("RGB", (200, 100), "white").save(jpg, exif=exif, dpi=(100, 100))
    info = loaders.read_image_info(jpg)
    design = Design()
    loaders.load_image(jpg, design, 100)
    ok = info[:2] == (100, 200) and design.raster.image.size == (1000, 2000)
    print("%-5s image import: EXIF rotation applied %s" % ("OK" if ok else "FAIL", info))
    errors += 0 if ok else 1
    shutil.rmtree(tmp)
    return errors


def test_layout(baseline):
    """Element placement and compiling several elements into one job."""
    from kerfly.core.layout import Element, compile_layout
    errors = 0

    def check(name, ok, detail=""):
        nonlocal errors
        print("%-5s layout: %s %s" % ("OK" if ok else "FAIL", name, detail))
        errors += 0 if ok else 1

    # a single unchanged element is passed through: identical laser data
    d = Design()
    loaders.load_dxf(DXF, d)
    e = Element(d, x=1.0, y=-2.0)
    out, origin = compile_layout([e])
    data = job.egv_file_bytes(job.build_job(out, JobSettings(), "Vector_Cut")[0].data)
    check("single element passes through", out is d and origin == (1.0, -2.0)
          and hashlib.sha256(data).hexdigest() == baseline["dxf_vcut"]["sha256"])

    # geometry: 60 x 40 mm DXF rotated 90 degrees -> 40 x 60 mm, corners mapped
    d = Design()
    loaders.load_dxf(DXF, d)
    w0, h0 = d.bounds[1] - d.bounds[0], d.bounds[3] - d.bounds[2]
    e = Element(d, x=0.5, y=-0.5, rotation=90)
    w, h = e.size
    f = e.transform()
    xmin, xmax, ymin, ymax = d.bounds
    tl = f(xmin, ymax)        # source top-left -> after +90 (ccw) it is bottom-left
    check("rotate 90 swaps size", abs(w - h0) < 1e-9 and abs(h - w0) < 1e-9, "(%.3f x %.3f in)" % (w, h))
    check("rotate 90 maps corner", abs(tl[0] - 0.5) < 1e-9 and abs(tl[1] - (-0.5 - h)) < 1e-9, "(%s)" % (tl,))
    e.set_size(2.0, 1.0)
    check("set_size with 90 degree rotation", abs(e.size[0] - 2.0) < 1e-9 and abs(e.size[1] - 1.0) < 1e-9)

    # two elements: union bounds, loops kept apart, rasters composited
    a = Design()
    loaders.load_dxf(DXF, a)
    b = Design()
    load_png(b)                               # 0.6 x 0.4 in raster at 1000 dpi
    ea = Element(a, x=0.0, y=0.0)
    eb = Element(b, x=3.0, y=-1.0, scale_x=2.0, scale_y=2.0)
    out, origin = compile_layout([ea, eb])
    # the merged design has its own frame from (0, 0), like a loaded file; origin = bed top-left
    xmin, ymax = origin
    w, h = out.bounds[1] - out.bounds[0], out.bounds[3] - out.bounds[2]
    ymin = ymax - h
    cut_loops = len({row[2] for row in out.vector_cut.ecoords})
    src_loops = len({row[2] for row in a.vector_cut.ecoords})
    im = out.raster.image
    ok_bounds = out.bounds[0] == 0.0 and out.bounds[2] == 0.0 and abs(xmin) < 1e-9 \
        and abs(w - 4.2) < 1e-9 and abs(ymax) < 1e-9 and abs(ymin - min(-1.8, ea.bounds[2])) < 1e-9
    check("two elements: bounds", ok_bounds, "(%s, origin %s)" % (out.bounds, origin))
    check("two elements: vector loops kept", cut_loops == src_loops)
    # the dark disc of the synthetic image (centre 300,200 px) lands at
    # x = 3.0 + 2*0.3 in, y = -1.0 - 2*0.2 in
    px = int(round((3.6 - xmin) * 1000))
    py = int(round((ymax - (-1.4)) * 1000))
    check("two elements: raster placed and scaled", im.size == (4200, max(1800, int(round(-ea.bounds[2] * 1000))))
          and im.getpixel((px, py)) == 0 and im.getpixel((100, 100)) == 255, "(%s)" % (im.size,))
    settings = JobSettings()
    raster.make_raster_coords(out, settings)
    chunks = job.build_job(out, settings, "Raster_Eng+Vector_Eng+Vector_Cut")
    check("two elements: job generated", len(chunks) == 1 and len(chunks[0].data) > 1000)
    return errors


def test_shapes():
    """Drawn shapes: sizes, operations, even-odd fill, job generation."""
    import math
    from kerfly.core.shapes import ShapeSpec, build_design
    errors = 0

    def check(name, ok, detail=""):
        nonlocal errors
        print("%-5s shapes: %s %s" % ("OK" if ok else "FAIL", name, detail))
        errors += 0 if ok else 1

    def size_mm(d):
        b = d.bounds
        return round((b[1] - b[0]) * 25.4, 6), round((b[3] - b[2]) * 25.4, 6)

    d = build_design(ShapeSpec("rectangle", 40, 20, corner_radius=5))
    check("rectangle 40 x 20 mm, rounded, cut", size_mm(d) == (40.0, 20.0) and d.vector_cut.ecoords
          and not d.vector_engrave.ecoords)
    d = build_design(ShapeSpec("ellipse", 30, 10, operation="engrave"))
    check("ellipse 30 x 10 mm, engrave", size_mm(d) == (30.0, 10.0) and d.vector_engrave.ecoords)
    d = build_design(ShapeSpec("polygon", 25, 25, sides=6))
    loops = {row[2] for row in d.vector_cut.ecoords}
    check("hexagon: one closed loop with 7 points", len(loops) == 1 and len(d.vector_cut.ecoords) == 7)
    d = build_design(ShapeSpec("line", 30, -10))
    check("line 30 x 10 mm (up-right)", size_mm(d) == (30.0, 10.0) and len(d.vector_cut.ecoords) == 2)
    outer = [(10 + 10 * math.cos(a / 60 * 2 * math.pi), 10 + 10 * math.sin(a / 60 * 2 * math.pi)) for a in range(60)]
    inner = [(10 + 4 * math.cos(a / 60 * 2 * math.pi), 10 + 4 * math.sin(a / 60 * 2 * math.pi)) for a in range(60)]
    d = build_design(ShapeSpec("text", operation="fill", text_outlines=[outer, inner]))
    im = d.raster.image
    check("fill keeps holes (even-odd)", im.getpixel((im.width // 2, im.height // 2)) == 255
          and im.getpixel((im.width // 2, int(im.height * 0.15))) == 0)
    settings = JobSettings()
    raster.make_raster_coords(d, settings)
    check("filled shape gives a raster job", len(job.build_job(d, settings, "Raster_Eng")[0].data) > 100)
    tri = [(0.0, 0.0), (30.0, 0.0), (15.0, 20.0)]
    closed = build_design(ShapeSpec(kind="polyline", points=tri, closed_path=True))
    opened = build_design(ShapeSpec(kind="polyline", points=tri, closed_path=False))
    filled = build_design(ShapeSpec(kind="polyline", points=tri, closed_path=True, operation="fill"))
    no_fill_open = build_design(ShapeSpec(kind="polyline", points=tri, closed_path=False, operation="fill"))
    check("polyline: closed has 3 sides, open 2, closed can be filled, open cannot",
          len(closed.vector_cut.ecoords) == 4 and len(opened.vector_cut.ecoords) == 3
          and filled.raster.image is not None and no_fill_open.raster.image is None
          and abs(size_mm(closed)[0] - 30) < 1e-6 and abs(size_mm(closed)[1] - 20) < 1e-6,
          "(points: closed %d, open %d)" % (len(closed.vector_cut.ecoords), len(opened.vector_cut.ecoords)))
    return errors


def test_layers(baseline):
    """Default layers give byte-identical laser data; extra layers add stages."""
    from kerfly.core.layers import CUT, Layer, build_layers_job, default_layers
    from kerfly.core.layout import Element
    errors = 0

    def check(name, ok, detail=""):
        nonlocal errors
        print("%-5s layers: %s %s" % ("OK" if ok else "FAIL", name, detail))
        errors += 0 if ok else 1

    def run(source, settings, layers=None, extra=None):
        d = Design()
        if source == "svg":
            loaders.load_svg(SVG, d, inkscape_path=INKSCAPE)
        elif source == "dxf":
            loaders.load_dxf(DXF, d)
        elif source == "png":
            load_png(d)
        elements = [Element(d, x=1.0, y=-1.0)]
        if extra is not None:
            extra(elements, layers)
        return build_layers_job(elements, layers or default_layers(), settings)

    def egv_digest(chunks):
        return hashlib.sha256(job.egv_file_bytes(chunks[0].data)).hexdigest()

    if INKSCAPE:
        chunks, origin = run("svg", JobSettings())
        check("default layers, SVG raster+engrave+cut == baseline",
              egv_digest(chunks) == baseline["svg_raster_vector_cut"]["sha256"] and origin == (1.0, -1.0))
        layers = default_layers()
        for layer in layers:
            layer.power = {"raster": 0.3, "engrave": 0.6, "cut": 0.9, "gcode": 0.5}[layer.kind]
        chunks, _o = run("svg", JobSettings(power_per_stage=True), layers)
        expected = open(os.path.join(TESTS_DIR, "baseline", "usb_m3_power_levels.usb"), "rb").read()
        sent = b"".join(bytes(c.data) for c in chunks)
        powers = [round(c.power, 6) for c in chunks]
        check("M3 power per layer matches baseline data", powers == [9.0, 18.0, 27.0]
              and all(bytes(c.data) in expected for c in chunks) and len(sent) > 1000)
    chunks, _o = run("dxf", JobSettings(), default_layers())
    check("default layers, DXF == baseline (cut + engrave stages)",
          egv_digest(chunks) == hashlib.sha256(job.egv_file_bytes(
              job.build_job(_dxf_design(), JobSettings(), "Vector_Eng+Vector_Cut")[0].data)).hexdigest())
    chunks, _o = run("png", JobSettings())
    check("default layers, PNG raster == baseline", egv_digest(chunks) == baseline["png_reng_halftone"]["sha256"])

    # two cut layers: a second element on its own, slower cut layer
    def two_cut_layers(elements, layers):
        d2 = Design()
        loaders.load_dxf(DXF, d2)
        e2 = Element(d2, x=4.0, y=-1.0)
        slow = Layer(CUT, name="slow", speed=3.0, passes=2)
        layers.append(slow)
        e2.layers[CUT] = slow.id
        elements.append(e2)
    layers = default_layers()
    chunks, origin = run("dxf", JobSettings(), layers, two_cut_layers)
    data = bytes(chunks[0].data)
    check("two cut layers: one job, both stages, origin at the layout corner",
          len(chunks) == 1 and origin == (1.0, -1.0) and data.count(b"@") >= 2, "(%d bytes)" % len(data))
    # a layer with one untransformed element among others: its data in bed coordinates
    from kerfly.core.layers import compile_layer, default_layers
    from kerfly.core.shapes import ShapeSpec, build_design
    c = ShapeSpec(kind="ellipse", width=20, height=20, operation="cut")
    r = ShapeSpec(kind="rectangle", width=40, height=10, operation="engrave")
    ce = Element(build_design(c), x=1.0, y=-3.0, shape=c)
    re_ = Element(build_design(r), x=4.0, y=-0.5, shape=r)
    lay = default_layers()
    cut_layer = [l for l in lay if l.kind == "cut"][0]
    d, o = compile_layer([ce, re_], cut_layer, lay)
    # design frame -> bed: the design's top-left corner is at the origin
    xs = [row[0] - d.bounds[0] + o[0] for row in d.vector_cut.ecoords]
    ys = [row[1] - d.bounds[3] + o[1] for row in d.vector_cut.ecoords]
    ok = abs(min(xs) - 1.0) < 1e-6 and abs(max(ys) + 3.0) < 1e-6 and d.bounds[0] == 0.0 and o == (1.0, -0.5)
    print("%-5s layers: lone untransformed part of a bigger layout keeps its bed position %s"
          % ("OK" if ok else "FAIL", (round(min(xs), 4), round(max(ys), 4))))
    errors += 0 if ok else 1
    return errors


def test_job_position():
    """The laser data put every part where the layout shows it. The raster scan
    lines are measured from the bottom of the image, so a merged layout whose
    frame does not start at y = 0 was engraved too high (real laser test,
    November 2026: the head ran up into the frame)."""
    from PIL import Image
    from kerfly.core.layers import RASTER, compile_layer, default_layers
    from kerfly.core.layout import Element, compile_layout
    errors = 0

    def check(name, ok, detail=""):
        nonlocal errors
        print("%-5s job position: %s %s" % ("OK" if ok else "FAIL", name, detail))
        errors += 0 if ok else 1

    def photo(x, y, **kw):
        d = Design()
        d.input_dpi = 1000.0
        d.raster.set_image(Image.new("L", (1000, 500), 0))          # 1 x 0.5 in, all black
        d.bounds = (0.0, 1.0, 0.0, 0.5)
        return Element(d, x=x, y=y, **kw)

    def cut(x, y):
        d = Design()
        d.vector_cut.set_ecoords([[0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1], [0, 0, 1]])
        d.bounds = (0.0, 1.0, 0.0, 1.0)
        return Element(d, x=x, y=y)

    layers = default_layers()
    raster_layer = [l for l in layers if l.kind == RASTER][0]
    settings = JobSettings()
    cases = [("photo alone", [photo(2.0, -3.0)]),
             ("photo below a cut shape", [photo(2.0, -2.0), cut(4.0, -1.0)]),
             ("scaled photo", [photo(2.0, -3.0, scale_x=0.5, scale_y=0.5)]),
             ("rotated photo with a cut shape", [photo(2.0, -3.0, rotation=90), cut(0.5, -0.5)])]
    for name, elements in cases:
        d, origin = compile_layer(elements, raster_layer, layers)
        raster.make_raster_coords(d, settings)
        xmin, _xmax, _ymin, ymax = d.origin_bounds(settings)
        # where the job sends the head for the first scan line (as build_job / egv do it)
        first_y = origin[1] + d.raster.ecoords[0][1] - ymax
        first_x = origin[0] + min(r[0] for r in d.raster.ecoords)
        top, left = elements[0].bounds[3], elements[0].bounds[0]
        check("raster starts at the photo: " + name,
              abs(first_y - top) < 0.003 and abs(first_x - left) < 0.003,
              "(head %.3f, %.3f in; photo top-left %.3f, %.3f in)" % (first_x, first_y, left, top))

    # trace boundary of a photo and a cut shape stays around them (it used to reach far above)
    elements = [photo(2.0, -2.0), cut(4.0, -1.0)]
    d, origin = compile_layout(elements)
    raster.make_raster_coords(d, settings)
    trace = job.make_trace_path(d, settings)
    xmin, _xmax, _ymin, ymax = d.origin_bounds(settings)
    ys = [origin[1] + p[1] - ymax for p in trace]
    check("trace stays within the layout", max(ys) < -1.0 + 0.003 and min(ys) > -2.5 - 0.003,
          "(y %.3f .. %.3f in, layout -2.500 .. -1.000)" % (min(ys), max(ys)))

    # the trace loop starts at the corner where the head is (top-left), with and without
    # pyclipper (pyclipper started it at the upper right: the head ran along the top edge first)
    rect = Design()
    rect.vector_cut.set_ecoords([[0, 0, 1], [2, 0, 1], [2, 1, 1], [0, 1, 1], [0, 0, 1]])
    rect.bounds = (0.0, 2.0, 0.0, 1.0)
    starts = []
    saved = job.PYCLIPPER
    for clip in (False, saved):
        job.PYCLIPPER = clip
        try:
            t = job.make_trace_path(rect, replace(settings, trace_from_corner=True))
        finally:
            job.PYCLIPPER = saved
        starts.append((round(t[0][0], 3), round(t[0][1], 3)) + ((t[0][:2] == t[-1][:2]),))
    check("trace starts at the top-left corner", all(st == (0.0, 1.0, True) for st in starts),
          "(start, closed: %s)" % (starts,))

    # safety check before sending: the whole job stays on a 12 x 8 in bed ...
    from kerfly.core.layers import build_layers_job
    chunks, origin = build_layers_job([photo(2.0, -2.0), cut(4.0, -1.0)], default_layers(), settings)
    reach = chunks[0].reach
    check("safety check: a correct job passes", reach is not None
          and job.reach_problem(reach, origin, 12.0, 8.0, settings) is None
          and abs(origin[1] + reach[3] - (-1.0)) < 0.003, "(reach %s)" % (reach,))
    # ... and stops the old fault: a raster design in bed coordinates (bottom not at 0)
    bad = Design()
    bad.input_dpi = 1000.0
    bad.raster.set_image(Image.new("L", (1000, 500), 0))
    bad.bounds = (2.0, 3.0, -2.5, -2.0)
    raster.make_raster_coords(bad, settings)
    reach = job.build_job(bad, settings, job.RASTER_ENG)[0].reach
    problem = job.reach_problem(reach, (2.0, -2.0), 12.0, 8.0, settings)
    # bug report form address (field ids of .github/ISSUE_TEMPLATE/*.yml)
    from urllib.parse import parse_qs, urlparse
    from kerfly.core import diag
    q = parse_qs(urlparse(diag.issue_url("laser", "9.9.9", "LASER-M3")).query)
    forms = os.path.join(ROOT_DIR, ".github", "ISSUE_TEMPLATE")
    ok = q.get("template") == ["laser_problem.yml"] and q.get("version") == ["9.9.9"] \
        and q.get("board") == ["LASER-M3"] and q.get("system", [""])[0] != ""
    for kind, fname in diag.ISSUE_TEMPLATES.items():
        text = open(os.path.join(forms, fname), encoding="utf-8").read()
        ok = ok and all("id: %s\n" % f in text for f in ("version", "system", "board", "report"))
    check("bug report form: version, system and board filled in", ok, "(%s)" % q)
    # the user guide address points to a page that exists in docs/ (the website)
    pages = {lang: diag.guide_url(lang)[len(diag.WEBSITE_URL):] for lang in ("en", "pl", "de")}
    check("user guide: page in the language, English otherwise",
          pages == {"en": "guide.html", "pl": "pl/guide.html", "de": "guide.html"}
          and all(os.path.exists(os.path.join(ROOT_DIR, "docs", p.replace(".html", ".md"))) for p in pages.values()),
          "(%s)" % pages)
    check("safety check: a job running above the bed is refused",
          problem is not None and problem[0] == "top", "(%s)" % (problem,))
    return errors


def test_materials():
    """Material library: export, import, merge by name."""
    from kerfly.core import materials as ml
    tmp = tempfile.mkdtemp()
    path = os.path.join(tmp, "lib.json")
    lib = ml.example_materials()
    ml.export_library(lib, path)
    back = ml.import_library(path)
    same = [(m.name, m.thickness_mm, {k: vars(v) for k, v in m.settings.items()}) for m in lib] == \
        [(m.name, m.thickness_mm, {k: vars(v) for k, v in m.settings.items()}) for m in back]
    changed = ml.import_library(path)
    changed[0].settings["cut"].speed = 99.0
    changed.append(ml.Material("MDF 3 mm", 3.0))
    changed[0].name = changed[0].name.upper()            # same name, other case: replaces
    merged, added, replaced = ml.merge_materials(lib, changed)
    ok = same and added == 1 and replaced == len(lib) and len(merged) == len(lib) + 1 \
        and merged[0].settings["cut"].speed == 99.0
    print("%-5s materials: export / import / merge (added %d, replaced %d)" % ("OK" if ok else "FAIL", added, replaced))
    shutil.rmtree(tmp)
    return 0 if ok else 1


def _dxf_design():
    d = Design()
    loaders.load_dxf(DXF, d)
    return d


def test_arrange():
    """Mirror, align and distribute elements on the bed."""
    from PIL import Image, ImageChops
    from kerfly.core.layout import Element, align, compile_layout, distribute, mirror, selection_bounds
    errors = 0

    def check(name, ok, detail=""):
        nonlocal errors
        print("%-5s arrange: %s %s" % ("OK" if ok else "FAIL", name, detail))
        errors += 0 if ok else 1

    def near(a, b, tol=1e-9):
        return all(abs(p - q) < tol for p, q in zip(a, b))

    d = Design()
    loaders.load_dxf(DXF, d)
    e = Element(d, x=1.0, y=-1.0, rotation=30)
    before = e.bounds
    def bed_rows(design, origin):                              # design frame -> bed coordinates
        return [(r[0] - design.bounds[0] + origin[0], r[1] - design.bounds[3] + origin[1])
                for r in design.vector_cut.ecoords]
    plain, o1 = compile_layout([Element(d, x=1.0, y=-1.0, rotation=30, scale_x=1.0000001)])
    mirror(e, horizontal=True)
    flipped, o2 = compile_layout([e])
    # every point is reflected about the vertical line through the centre
    cx = (before[0] + before[1]) / 2.0
    a = sorted((round(2 * cx - x, 6), round(y, 6)) for x, y in bed_rows(plain, o1))
    b = sorted((round(x, 6), round(y, 6)) for x, y in bed_rows(flipped, o2))
    check("horizontal mirror of a rotated element reflects every point", near(e.bounds, before, 1e-6)
          and len(a) == len(b) and all(near(p, q, 1e-5) for p, q in zip(a, b)))
    mirror(e, horizontal=True)
    check("mirroring twice gives the original placement",
          near((e.x, e.y, e.scale_x, e.scale_y, e.rotation), (1.0, -1.0, 1.0, 1.0, 30.0), 1e-9))

    img = Image.new("L", (40, 20), 255)
    img.paste(0, (0, 0, 10, 20))                              # black stripe on the left quarter
    png = os.path.join(tempfile.mkdtemp(), "stripe.png")
    img.save(png, dpi=(100, 100))
    r = Design()
    loaders.load_image(png, r, 100)                          # 0.4 x 0.2 in
    re = Element(r, x=0.5, y=-0.5)
    mirror(re, horizontal=True)
    out, _o = compile_layout([re, Element(d, x=3.0, y=-0.5)])  # two elements: the raster is redrawn
    im = out.raster.image
    px = im.width * 0.4 / (out.bounds[1] - out.bounds[0])    # pixels across the image element
    row = int(im.height * 0.1 / (out.bounds[3] - out.bounds[2]))   # 0.1 in below the top: inside the image
    black = [x for x in range(int(px)) if im.getpixel((x, row)) < 128]
    check("raster mirror moves the stripe to the right", bool(black) and min(black) >= 0.7 * px
          and max(black) <= px + 2, "(stripe %s..%s of %d px)" % (min(black or [0]), max(black or [0]), px))

    a1, a2, a3 = Element(d, x=0.2, y=-0.3), Element(d, x=1.7, y=-1.1, scale_x=0.5), Element(d, x=4.0, y=-0.6)
    frame = selection_bounds([a1, a2, a3])
    align([a1, a2, a3], "left", frame)
    left_ok = all(abs(e.bounds[0] - 0.2) < 1e-9 for e in (a1, a2, a3))
    align([a1, a2, a3], "vcenter", (0.0, 10.0, -8.0, 0.0))
    mid_ok = all(abs((e.bounds[2] + e.bounds[3]) / 2.0 + 4.0) < 1e-9 for e in (a1, a2, a3))
    check("align left and to the middle of a frame", left_ok and mid_ok)

    b1, b2, b3 = Element(d, x=0.0, y=-1.0), Element(d, x=3.5, y=-1.0, scale_x=0.5), Element(d, x=6.0, y=-1.0)
    distribute([b3, b1, b2], horizontal=True)
    g1 = b2.bounds[0] - b1.bounds[1]
    g2 = b3.bounds[0] - b2.bounds[1]
    check("distribute: equal gaps, ends stay", abs(g1 - g2) < 1e-9 and b1.x == 0.0 and b3.x == 6.0,
          "(gaps %.4f, %.4f in)" % (g1, g2))
    c1, c2, c3 = Element(d, x=0.0, y=0.0), Element(d, x=0.5, y=-2.0), Element(d, x=3.0, y=-4.0)
    how = distribute([c1, c2, c3], horizontal=True)          # too wide for gaps: centres spaced evenly
    cs = [(e.bounds[0] + e.bounds[1]) / 2.0 for e in (c1, c2, c3)]
    check("distribute overlapping elements by their centres", how[0] == "centres"
          and abs((cs[1] - cs[0]) - (cs[2] - cs[1])) < 1e-9 and c1.x == 0.0 and c3.x == 3.0)
    s1, s2, s3 = Element(d, x=1.0, y=0.0), Element(d, x=1.0, y=-2.0), Element(d, x=1.0, y=-4.0)
    check("distribute along a line they are centred on: nothing moves",
          distribute([s1, s2, s3], horizontal=True) == ("in_line", 0.0) and (s1.x, s2.x, s3.x) == (1.0, 1.0, 1.0))
    from kerfly.core.layout import mirror_about, rotate_about, units
    g1, g2, lone = Element(d, x=0.0, y=0.0, group="g"), Element(d, x=3.0, y=0.0, group="g"), Element(d, x=6.0, y=-2.0)
    parts = units([g1, lone, g2])
    check("units: a group is one unit", len(parts) == 2 and hasattr(parts[0], "elements"))
    align(parts, "bottom", (0.0, 10.0, -5.0, 0.0))
    check("align moves a group as a whole", abs(g1.y - g2.y) < 1e-12 and abs(min(g1.bounds[2], g2.bounds[2]) + 5) < 1e-9
          and abs(lone.bounds[2] + 5) < 1e-9)
    c0 = (g1.centre, g2.centre)
    rotate_about([g1, g2], 90, 3.0, -1.0)
    rotate_about([g1, g2], -90, 3.0, -1.0)
    back = all(abs(a - b) < 1e-9 for p, q in zip(c0, (g1.centre, g2.centre)) for a, b in zip(p, q))
    mirror_about([g1, g2], True, 0.0, 0.0)
    mirrored = abs(g1.centre[0] + c0[0][0]) < 1e-9 and g1.scale_x < 0
    check("rotate a group about a point and back; mirror about an axis", back and mirrored)
    return errors


def test_curves():
    """Paths with Bezier curves: arcs, node edits, joining, reading SVG / DXF curves."""
    import math
    from kerfly.core import curves as C
    from kerfly.core.shapes import ShapeSpec, build_design
    errors = 0

    def check(name, ok, detail=""):
        nonlocal errors
        print("%-5s curves: %s %s" % ("OK" if ok else "FAIL", name, detail))
        errors += 0 if ok else 1

    circle = C.join_segments(C.arc_segments(0, 0, 10, 0, 360), 1e-9)
    err = max(abs(math.hypot(x, y) - 10) for x, y in C.flatten(circle)[0])
    check("circle from Bezier arcs is round and closed", circle[0]["closed"] and err < 0.025, "(error %.4f mm)" % err)
    b = C.bulge_segments(0, 0, 2, 0, 1.0)
    bottom = b[len(b) // 2 - 1][3]                                   # half way round
    check("DXF bulge +1 is a half circle below the chord", abs(b[-1][3][0] - 2) < 1e-9
          and abs(bottom[0] - 1) < 1e-9 and abs(bottom[1] + 1) < 1e-9)
    sq = C.from_polylines([[(0, 0), (10, 0), (10, 10), (0, 10)]], [True])
    i = C.insert_node(sq, 0, 0, 0.5)
    check("insert a node in a line", i == 1 and sq[0]["nodes"][1][:2] == [5.0, 0.0])
    C.make_curve(sq, 0, 1)
    curvy = C.segments_of(sq[0])
    check("make curve gives handles", C.is_curve(curvy[0]) and C.is_curve(curvy[1]))
    C.smooth_node(sq, 0, 1, symmetric=True)
    n = sq[0]["nodes"][1]
    check("symmetric node: handles in line, same length", C._is_smooth(n)
          and abs(math.hypot(n[2] - n[0], n[3] - n[1]) - math.hypot(n[4] - n[0], n[5] - n[1])) < 1e-9)
    C.move_handle(sq, 0, 1, "out", n[0] + 3, n[1] + 3)
    check("moving one handle of a smooth node turns the other", C._is_smooth(sq[0]["nodes"][1]))
    seg = C.segments_of(sq[0])[0]
    left, right = C.split_cubic(seg, 0.3)
    check("splitting a curve keeps its shape", all(
        math.hypot(*(a - b for a, b in zip(C.bezier_point(left, t), C.bezier_point(seg, 0.3 * t)))) < 1e-9
        for t in (0.0, 0.5, 1.0)))
    C.make_line(sq, 0, 1)
    check("make line removes the handles", not any(C.is_curve(s) for s in C.segments_of(sq[0])[:2]))
    check("delete keeps at least a triangle", C.delete_node(sq, 0, 1) and not C.delete_node(
        C.from_polylines([[(0, 0), (1, 0), (0, 1)]], [True]), 0, 0))
    C.break_at(sq, 0, 2)
    check("break a closed path opens it at the node", not sq[0]["closed"] and len(sq[0]["nodes"]) == 5)
    line = [(x * 0.1, 0.001 * ((-1) ** x)) for x in range(100)]
    check("simplify drops points on a straight line", len(C.simplify(line, 0.01)) == 2)
    sm = C.smooth_path([(0, 0), (10, 5), (20, 0), (30, 5)], False)
    check("smooth path passes through the points", [n[:2] for n in sm[0]["nodes"]] == [[0, 0], [10, 5], [20, 0], [30, 5]]
          and sm[0]["nodes"][1][4] is not None)
    from kerfly.core.hatch import hatch_lines
    sq = [[(0, 0), (10, 0), (10, 10), (0, 10)]]
    ring = sq + [[(3, 3), (7, 3), (7, 7), (3, 7)]]
    lines = hatch_lines(sq, 1.0, 0)
    check("hatch: 10 mm square, 1 mm spacing -> 10 lines, zigzag", len(lines) == 10
          and lines[0][0][0] < lines[0][1][0] and lines[1][0][0] > lines[1][1][0])
    holed = hatch_lines(ring, 1.0, 0)
    check("hatch keeps holes empty", len(holed) == 14 and not any(3 < (a[0] + b[0]) / 2 < 7 and 3 < a[1] < 7
                                                                  for a, b in holed))
    hd = build_design(ShapeSpec(kind="rectangle", width=10, height=10, operation="hatch",
                                hatch_spacing=1.0, hatch_angle=0.0))
    check("hatched rectangle: engrave lines, no cut, no raster", hd.vector_engrave.ecoords and not hd.vector_cut.ecoords
          and hd.raster.image is None and abs(hd.bounds[1] * 25.4 - 10) < 1e-9)
    from kerfly.core.shapes import with_tabs
    pieces = with_tabs([(0, 0), (10, 0), (10, 10), (0, 10), (0, 0)], 4, 1.0)
    cut_len = sum(math.hypot(b[0] - a[0], b[1] - a[1]) for p in pieces for a, b in zip(p, p[1:]))
    check("bridges: 4 x 1 mm leave 36 mm of a 40 mm square", len(pieces) == 4 and abs(cut_len - 36) < 1e-9)
    tabbed = build_design(ShapeSpec(kind="rectangle", width=10, height=10, operation="cut", tabs=4, tab_width=1.0))
    loops = {r[2] for r in tabbed.vector_cut.ecoords}
    check("rectangle with bridges is cut in 4 pieces", len(loops) == 4)
    design = build_design(ShapeSpec(kind="path", subpaths=circle, operation="fill"))
    check("a closed path can be filled", design.raster.image is not None)
    found = C.svg_segments(SVG)
    check("SVG curves: red and blue strokes", len(found["cut"]) > 4 and len(found["engrave"]) > 2)
    dx = C.dxf_segments(DXF, 1 / 25.4)
    check("DXF curves: arcs stay curves", any(s[1] is not None for s in dx["cut"] + dx["engrave"]))
    return errors


def test_pattern_fill():
    """Pattern fills: every pattern stays inside the shape, out of its holes and
    `margin` away from the outline; the outline keeps its own part; saved in projects."""
    import math
    from kerfly.core import patterns, project
    from kerfly.core.layout import Element
    from kerfly.core.shapes import ShapeSpec, build_design, element_contains
    errors = 0

    def check(name, ok, detail=""):
        nonlocal errors
        print("%-5s pattern fill: %s %s" % ("OK" if ok else "FAIL", name, detail))
        errors += 0 if ok else 1

    outer = [(0, 0), (100, 0), (100, 60), (0, 60), (0, 0)]
    hole = [(30, 20), (70, 20), (70, 40), (30, 40), (30, 20)]

    def dist_to_outline(x, y):
        best = 1e9
        for ring in (outer, hole):
            for (x1, y1), (x2, y2) in zip(ring, ring[1:]):
                ex, ey = x2 - x1, y2 - y1
                t = max(0.0, min(1.0, ((x - x1) * ex + (y - y1) * ey) / (ex * ex + ey * ey)))
                best = min(best, math.hypot(x1 + t * ex - x, y1 + t * ey - y))
        return best

    for code in patterns.PATTERN_CODES:
        for margin in (0.0, 2.0):
            lines = patterns.pattern_lines(code, [outer, hole], 5.0, 20.0, margin)
            pts = [p for line in lines for p in line]
            # points on the polylines and in the middle of every piece
            mids = [((a[0] + b[0]) / 2, (a[1] + b[1]) / 2) for line in lines for a, b in zip(line, line[1:])]
            bad_hole = [p for p in mids if 30 < p[0] < 70 and 20 < p[1] < 40]
            bad_out = [p for p in pts + mids if not (-1e-6 <= p[0] <= 100 + 1e-6 and -1e-6 <= p[1] <= 60 + 1e-6)]
            near = min((dist_to_outline(*p) for p in pts + mids), default=0.0)
            ok = len(lines) > 3 and not bad_hole and not bad_out and (margin == 0 or near >= margin - 0.02)
            check("%s, margin %g mm: inside, holes empty" % (code, margin), ok,
                  "(%d lines, closest %.3f mm)" % (len(lines), near))

    # shapes: the cut outline stays a cut part, the pattern is an engrave part
    cut = build_design(ShapeSpec(kind="ellipse", width=60, height=40, operation="cut",
                                 fill_pattern="waves", fill_spacing=3.0))
    plain = build_design(ShapeSpec(kind="ellipse", width=60, height=40, operation="cut"))
    no_outline = build_design(ShapeSpec(kind="ellipse", width=60, height=40, operation="cut",
                                        fill_pattern="waves", fill_spacing=3.0, fill_outline=False))
    line = build_design(ShapeSpec(kind="line", width=30, height=0, operation="cut", fill_pattern="waves"))
    check("cut outline + engraved pattern; outline can be left out",
          cut.vector_cut.ecoords == plain.vector_cut.ecoords and len(cut.vector_engrave.ecoords) > 100
          and not no_outline.vector_cut.ecoords and len(no_outline.vector_engrave.ecoords) > 100
          and not line.vector_engrave.ecoords and cut.bounds == plain.bounds)

    # the Fill tool finds shapes by point, not inside their holes
    ring = ShapeSpec(kind="path", subpaths=[], operation="cut")
    rect = ShapeSpec(kind="rectangle", width=20, height=10, operation="cut")
    e = Element(build_design(rect), x=1.0, y=-1.0, shape=rect)
    check("point inside a shape", element_contains(e, 1.2, -1.1) and not element_contains(e, 0.9, -1.1)
          and not element_contains(Element(build_design(ring), shape=ring), 0.0, 0.0))

    # hatch shapes (0.4-0.16) became "lines / cross-hatch without the outline": same laser data,
    # and old projects open as such
    from kerfly.core.shapes import hatch_as_fill
    same = True
    for cross in (False, True):
        h = ShapeSpec(kind="ellipse", width=40, height=25, operation="hatch", hatch_spacing=0.3,
                      hatch_angle=30.0, hatch_cross=cross)
        a, b = build_design(h), build_design(hatch_as_fill(h))
        same = same and a.vector_engrave.ecoords == b.vector_engrave.ecoords and not b.vector_cut.ecoords
    old = project._shape_from_dict({"kind": "rectangle", "operation": "hatch", "hatch_spacing": 0.4,
                                    "hatch_angle": 15.0, "hatch_cross": True})
    check("old hatch: same laser data as cross-hatch / lines without outline, opens as a fill", same
          and (old.operation, old.fill_pattern, old.fill_spacing, old.fill_angle, old.fill_outline)
          == ("engrave", "cross", 0.4, 15.0, False))

    # living hinges: cuts stay inside with a solid border, are cut before the outline (the part must
    # not fall out first), are cut even when the outline is engraved; open lines get none
    rect = [(0, 0), (120, 0), (120, 60), (0, 60), (0, 0)]
    for code in patterns.HINGE_CODES:
        cuts = patterns.hinge_lines(code, [rect], 20.0, 3.0, 1.5, 90.0, 4.0)
        pts = [p for line in cuts for p in line]
        inside = all(4.0 - 0.02 <= x <= 116.0 + 0.02 and 4.0 - 0.02 <= y <= 56.0 + 0.02 for x, y in pts)
        lengths = [sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(l, l[1:])) for l in cuts]
        check("hinge %s: cuts inside, solid border" % code, len(cuts) > 100 and inside and max(lengths) >= 19.9,
              "(%d cuts)" % len(cuts))
    hspec = ShapeSpec(kind="rectangle", width=120, height=60, operation="cut", hinge_pattern="straight")
    hd = build_design(hspec)
    plain_cut = build_design(ShapeSpec(kind="rectangle", width=120, height=60, operation="cut"))
    first_loop = hd.vector_cut.ecoords[0][2]
    outline_rows = [r for r in hd.vector_cut.ecoords if r[2] == max(q[2] for q in hd.vector_cut.ecoords)]
    he = build_design(ShapeSpec(kind="rectangle", width=120, height=60, operation="engrave", hinge_pattern="wave"))
    hl = build_design(ShapeSpec(kind="line", width=50, height=0, operation="cut", hinge_pattern="straight"))
    check("hinge: cut before the outline, engraved outline still cut hinge, none on lines, same size",
          len(hd.vector_cut.ecoords) > len(plain_cut.vector_cut.ecoords) and len(outline_rows) >= 4
          and first_loop != outline_rows[0][2] and he.vector_engrave.ecoords and he.vector_cut.ecoords
          and not hl.vector_cut.ecoords[5:] and hd.bounds == plain_cut.bounds)
    # a hinge band: only part of the shape, its middle moved right (upright cuts) or left
    spans = []
    for offset in (0.0, 30.0, -30.0):
        sp = ShapeSpec(kind="rectangle", width=120, height=60, operation="cut", hinge_pattern="straight",
                       hinge_band=40.0, hinge_band_offset=offset)
        cuts = patterns.hinge_lines("straight", [rect], 20.0, 3.0, 1.5, -sp.hinge_angle, 4.0, 40.0, offset)
        xs = [p[0] for line in cuts for p in line]
        spans.append((round(min(xs)), round(max(xs))))
    check("hinge band: 40 mm wide, in the middle, moved right and left",
          all(abs(a - b) <= 1 for s1, s2 in zip(spans, [(40, 80), (70, 110), (10, 50)]) for a, b in zip(s1, s2)),
          "(%s)" % spans)
    back = project._shape_from_dict(project._shape_to_dict(ShapeSpec(kind="ellipse", hinge_pattern="zigzag",
                                                                     hinge_cut=15.0, hinge_spacing=2.0)))
    check("hinge settings saved in projects", (back.hinge_pattern, back.hinge_cut, back.hinge_spacing)
          == ("zigzag", 15.0, 2.0))

    # saved and opened with a project
    spec = ShapeSpec(kind="rectangle", operation="engrave", fill_pattern="honeycomb", fill_spacing=4.5,
                     fill_angle=30.0, fill_margin=1.0, fill_outline=False)
    back = project._shape_from_dict(project._shape_to_dict(spec))
    check("fill settings saved in projects", (back.fill_pattern, back.fill_spacing, back.fill_angle, back.fill_margin,
                                              back.fill_outline) == ("honeycomb", 4.5, 30.0, 1.0, False))
    return errors


def test_cut_order():
    """Within a layer the elements are cut in the order of the element list
    (K40 Whisperer's path sorting mixed them by distance: triangle, rectangle,
    ellipse instead of triangle, ellipse, rectangle on the second laser test).
    Inside an element, inner shapes still come first."""
    from kerfly.core.layers import CUT, build_layers_job, default_layers
    from kerfly.core.layout import Element
    from kerfly.core.shapes import ShapeSpec, build_design
    errors = 0
    specs = [("triangle", ShapeSpec(kind="polygon", width=30, height=30, sides=3), 60, 50),
             ("ellipse", ShapeSpec(kind="ellipse", width=25, height=25), 220, 20),
             ("rectangle", ShapeSpec(kind="rectangle", width=20, height=20), 100, 90)]
    elements = [Element(build_design(sp), x=x / 25.4, y=-y / 25.4, shape=sp) for _n, sp, x, y in specs]
    # a ring (outer and inner circle) as one element: the inner circle must be cut first
    ring = Element(build_design(ShapeSpec(kind="ellipse", width=40, height=40)), x=150 / 25.4, y=-120 / 25.4)
    hole = build_design(ShapeSpec(kind="ellipse", width=10, height=10)).vector_cut.ecoords
    ring.design.vector_cut.set_ecoords(ring.design.vector_cut.ecoords
                                       + [[r[0] + 10 / 25.4, r[1] + 10 / 25.4, r[2] + 100] for r in hole])
    elements.append(ring)
    layers = default_layers()
    cache = {}
    build_layers_job(elements, layers, JobSettings(), cache=cache)
    cut_layer = [l for l in layers if l.kind == CUT][0]
    rows = cache[cut_layer.id].vector_cut.ecoords
    loops = []
    for r in rows:
        if not loops or loops[-1][0] != r[2]:
            loops.append((r[2], []))
        loops[-1][1].append(r)
    names = []
    for _loop, pts in loops:
        w = (max(p[0] for p in pts) - min(p[0] for p in pts)) * 25.4
        names.append({30: "triangle", 25: "ellipse", 20: "rectangle", 10: "ring hole", 40: "ring outside"}.get(round(w),
                                                                                           "ring outside"))
    expected = ["triangle", "ellipse", "rectangle", "ring hole", "ring outside"]
    ok = names == expected and len({l for l, _p in loops}) == len(loops)
    print("%-5s cut order: as in the element list, holes first inside an element %s"
          % ("OK" if ok else "FAIL", names))
    errors += 0 if ok else 1

    # an open line drawn from right to left is cut from its left end, the one nearer to where
    # the head starts (the design's top-left corner), not after a run to its right end
    line = ShapeSpec(kind="polyline", points=[(80, 0), (40, 15), (0, 5)], closed_path=False)
    box = ShapeSpec(kind="rectangle", width=10, height=10)
    elements = [Element(build_design(box), x=0.0, y=0.0, shape=box),
                Element(build_design(line), x=0.0, y=-1.0, shape=line)]
    cache = {}
    build_layers_job(elements, layers, JobSettings(), cache=cache)
    rows = cache[cut_layer.id].vector_cut.ecoords
    line_rows = [r for r in rows if r[2] == rows[-1][2]]
    ok = line_rows[0][0] < line_rows[-1][0]
    print("%-5s cut order: an open line starts at its end nearer the head (x %.2f -> %.2f in)"
          % ("OK" if ok else "FAIL", line_rows[0][0], line_rows[-1][0]))
    errors += 0 if ok else 1

    # trace boundary as the bounding rectangle (Kerfly), the hull in K40 Whisperer
    from dataclasses import replace as _replace
    import math
    d = Design()
    d.vector_cut.set_ecoords([[i / 10.0, 1 - math.sin(i / 20.0 * math.pi) * 0.8, 1] for i in range(21)])
    d.bounds = (0, 2, 0.2, 1)
    rect = job.make_trace_path(d, _replace(JobSettings(), trace_from_corner=True, trace_rectangle=True))
    hull = job.make_trace_path(d, JobSettings())
    ok = [(round(p[0], 3), round(p[1], 3)) for p in rect] == [(0, 1), (2, 1), (2, 0.2), (0, 0.2), (0, 1)] \
        and len(hull) > 5
    print("%-5s trace: rectangle in Kerfly, outline (hull) as in K40 Whisperer" % ("OK" if ok else "FAIL"))
    errors += 0 if ok else 1
    return errors


def test_usblib():
    """Windows: libusb0.dll is looked for in System32 and next to the program,
    the first one that loads is used, and the log says where Kerfly looked."""
    import usb.backend.libusb0 as libusb0
    from kerfly.core import usblib
    errors = 0
    tmp = tempfile.mkdtemp()
    fake_dll = os.path.join(tmp, "libusb0.dll")
    open(fake_dll, "wb").close()
    saved = (os.name, usblib.sys.platform, libusb0.get_backend, usblib.candidates, usblib._result)
    calls = []

    def fake_get_backend(find_library=None):
        calls.append(find_library("libusb0") if find_library else None)
        return object() if find_library and find_library("libusb0") == fake_dll else None
    try:
        usblib.os.name = "nt"
        usblib.sys.platform = "win32"                 # also when the tests run on macOS
        libusb0.get_backend = fake_get_backend
        usblib.candidates = lambda: [os.path.join(tmp, "System32", "libusb0.dll"), fake_dll]
        usblib._result = None
        found, text = usblib.ensure_libusb()
        ok1 = found and fake_dll in text and calls[-1] == fake_dll
        usblib.candidates = lambda: [os.path.join(tmp, "nowhere", "libusb0.dll")]
        usblib._result = None
        found2, text2 = usblib.ensure_libusb()
        ok2 = not found2 and "nowhere" in text2 and "missing" in text2
    finally:
        usblib.os.name, usblib.sys.platform, libusb0.get_backend, usblib.candidates, usblib._result = saved
    # macOS: libusb-1.0 from inside Kerfly.app first, the log says where
    import usb.backend.libusb1 as libusb1
    fake_dylib = os.path.join(tmp, "libusb-1.0.0.dylib")
    open(fake_dylib, "wb").close()
    saved_mac = (usblib.sys.platform, libusb1.get_backend, usblib.mac_candidates, usblib._result)
    try:
        usblib.sys.platform = "darwin"
        libusb1.get_backend = lambda find_library=None: object() if find_library and \
            find_library("usb-1.0") == fake_dylib else None
        usblib.mac_candidates = lambda: [os.path.join(tmp, "nowhere.dylib"), fake_dylib]
        usblib._result = None
        found3, text3 = usblib.ensure_libusb()
        ok3 = found3 and fake_dylib in text3
    finally:
        usblib.sys.platform, libusb1.get_backend, usblib.mac_candidates, usblib._result = saved_mac
    for name, ok, detail in (("USB library loaded from the first place that works", ok1, ""),
                             ("USB library missing: the log lists where Kerfly looked", ok2, ""),
                             ("macOS: libusb-1.0 loaded from inside the app", ok3, "")):
        print("%-5s usb: %s %s" % ("OK" if ok else "FAIL", name, detail))
        errors += 0 if ok else 1
    return errors


def test_udev():
    """Linux: the USB rule is written through pkexec with the rule as an argument (no
    quoting problems), a closed password window is "cancelled", without pkexec the
    commands are given; a permission error is told from other USB errors."""
    from kerfly.core import udev
    errors = 0
    calls = []

    class Done:
        def __init__(self, rc):
            self.returncode, self.stdout, self.stderr = rc, "", "denied" if rc else ""

    def run(rc):
        def fake(cmd, **kw):
            calls.append((cmd, kw.get("env", {})))
            return Done(rc)
        return fake
    os.environ["LD_LIBRARY_PATH"] = "/tmp/_MEIxyz"                   # as a packaged Kerfly sets it
    try:
        ok, why = udev.install(run=run(0), which=lambda name: "/usr/bin/pkexec")
    finally:
        os.environ.pop("LD_LIBRARY_PATH", None)
    cmd, env = calls[-1]
    rule_line = [l for l in open(os.path.join(ROOT_DIR, "packaging", "linux", "99-kerfly-k40.rules"))
                 if l.startswith("SUBSYSTEM")][0].strip()
    good = ok and cmd[:3] == ["/usr/bin/pkexec", "sh", "-c"] and cmd[-1] == udev.RULE and \
        udev.RULE == rule_line and "LD_LIBRARY_PATH" not in env and udev.RULE_FILE in cmd[3]
    cancelled = udev.install(run=run(126), which=lambda n: "/usr/bin/pkexec") == (False, "cancelled")
    failed = udev.install(run=run(1), which=lambda n: "/usr/bin/pkexec") == (False, "denied")
    no_pkexec = udev.install(run=run(0), which=lambda n: None) == (False, "no pkexec") and \
        any("udevadm control" in c for c in udev.manual_commands())
    perm = udev.permission_problem("USB error: [Errno 13] Access denied (insufficient permissions)") and \
        not udev.permission_problem("USB error: No backend available")
    tmp = tempfile.mkdtemp()
    open(os.path.join(tmp, "50-other.rules"), "w").write('ATTRS{idVendor}=="0403"\n')
    found_none = not udev.installed(dirs=[tmp])
    open(os.path.join(tmp, "97-ctc-lasercutter.rules"), "w").write(
        'SUBSYSTEM=="usb", ATTRS{idVendor}=="1a86", ATTRS{idProduct}=="5512", GROUP="lasercutter"\n')
    found_ctc = udev.installed(dirs=[tmp])
    for name, ok_ in (("rule written by pkexec, packaged libraries left out", good),
                      ("password window closed: cancelled", cancelled), ("error text passed on", failed),
                      ("no pkexec: the commands to type", no_pkexec), ("permission error recognised", perm),
                      ("an existing K40 rule (also the K40 Whisperer one) is found", found_none and found_ctc)):
        print("%-5s udev: %s" % ("OK" if ok_ else "FAIL", name))
        errors += 0 if ok_ else 1
    return errors


def _inside(pt, polys):
    """Even-odd point in polygons (lists of points, closed or not)."""
    x, y = pt
    inside = False
    for poly in polys:
        n = len(poly)
        for i in range(n):
            (x1, y1), (x2, y2) = poly[i], poly[(i + 1) % n]
            if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
                inside = not inside
    return inside


def test_generators():
    """Generators: the material test grid and its layers; the box's fingers interlock
    with the next part (no gap, no overlap), each part one outline, the kerf grows
    them; kerf test slots = thickness + clearance; gear size; puzzle and ruler counts;
    the QR outline gives back the code's modules; the test card."""
    from kerfly.core import generators as g
    errors = 0
    results = []
    mt = g.material_test("engrave", 10, 50, 5, "power", 20, 60, 1, 3, 3, labels=True, legend="x")
    fields = [it for it in mt.items if it.name == "Field"]
    speeds = sorted({l.speed for l in mt.layers})
    powers = sorted({round(l.power, 3) for l in mt.layers})
    results.append(("material test: 5 x 3 fields, each on its own layer, speeds and powers spread evenly",
                    len(fields) == 15 and len(mt.layers) == 15 and speeds == [10, 20, 30, 40, 50]
                    and powers == [0.2, 0.4, 0.6] and len({it.layer for it in fields}) == 15))
    mp = g.material_test("cut", 5, 5, 1, "passes", passes_min=1, passes_max=4, rows=4, labels=False)
    results.append(("material test by passes: 1 to 4 passes, no labels",
                    [l.passes for l in mp.layers] == [1, 2, 3, 4] and all(it.name == "Field" for it in mp.items)))

    box = g.finger_box(100, 80, 50, 3, 10, kerf=0, lid=True)
    parts = {it.name: it for it in box.items}
    one_each = sorted(parts) == ["Back", "Bottom", "Front", "Left", "Lid", "Right"] and len(box.items) == 6

    def outline(name):
        it = parts[name]
        return [[(x + 0, y + 0) for x, y in it.spec.points]], it.spec.width, it.spec.height
    t = 3.0

    def strip(name, side, depth_at):
        """Material along one edge, sampled at the middle of every millimetre."""
        polys, w, h = outline(name)
        length = w if side in ("top", "bottom") else h
        out = []
        for k in range(int(length)):
            u = k + 0.5
            pt = {"top": (u, depth_at), "bottom": (u, h - depth_at), "left": (depth_at, u),
                  "right": (w - depth_at, u)}[side]
            out.append(_inside(pt, polys))
        return out
    # front's bottom edge against the bottom's top edge, front's left edge against the left side's
    # front edge (right edge of "Left"), left side's bottom edge against the bottom's left edge
    pairs = [(("Front", "bottom"), ("Bottom", "top")), (("Front", "left"), ("Left", "right")),
             (("Left", "bottom"), ("Bottom", "left")), (("Front", "top"), ("Lid", "top"))]
    interlock = True
    for (a, sa), (b, sb) in pairs:
        ma, mb = strip(a, sa, t / 2), strip(b, sb, t / 2)
        if sb == "left":
            mb = mb                                      # both run top to bottom / left to right
        inner = range(int(t) + 1, len(ma) - int(t) - 1)  # leave out the corners
        if any(ma[k] == mb[k] for k in inner):
            interlock = False
    kerfed = g.finger_box(100, 80, 50, 3, 10, kerf=0.2, lid=True)
    grow = abs(kerfed.items[0].spec.width - (box.items[0].spec.width + 0.2)) < 1e-6
    results.append(("finger box: six parts, one outline each, fingers interlock, the kerf grows the parts",
                    one_each and interlock and grow))
    try:
        g.finger_box(10, 10, 10, 5, 3)
        too_small = False
    except ValueError:
        too_small = True
    results.append(("finger box: too small for the material is refused", too_small))

    kt = g.kerf_test(50, 10, 10, 3.0, -0.2, 0.1, 7, 10, labels=False)
    cuts = [it for it in kt.items if it.name == "Comb cut"]
    plate = [it for it in kt.items if it.name == "Slot plate"][0]
    xs = sorted({round(x, 4) for x, y in plate.spec.points})
    widths = [round(b - a, 3) for a, b in zip(xs[1:-1:2], xs[2:-1:2])]
    results.append(("kerf test: 9 comb cuts, slots 2.8 to 3.1 mm", len(cuts) == 9 and
                    widths == [2.8, 2.85, 2.9, 2.95, 3.0, 3.05, 3.1]))

    gr = g.gear(20, 2.0, 20, 5)
    teeth = gr.items[0].spec
    results.append(("gear: tip diameter = module x (teeth + 2), axle hole",
                    abs(teeth.width - 44.0) < 0.05 and abs(teeth.height - 44.0) < 0.05 and len(gr.items) == 2))
    pz = g.puzzle(150, 100, 5, 4, seed=3)
    results.append(("puzzle: 4 + 3 inner lines in one shape, outline",
                    len(pz.items[0].spec.subpaths) == 7 and pz.items[1].spec.width == 150))
    rl = g.ruler(150, 25)
    results.append(("ruler: 151 marks, 16 numbers", len(rl.items[0].spec.subpaths) == 151 and
                    sum(1 for it in rl.items if it.name == "Number") == 16))

    try:
        import segno
        qr = g.qr_code("Kerfly", 30, "m", 2)
        matrix = segno.make("Kerfly", error="m", micro=False).matrix
        n = len(matrix)
        cell = 30.0 / (n + 4)
        sp = qr.items[0].spec.subpaths
        polys = [[(nd[0] + qr.items[0].left, nd[1] + qr.items[0].top) for nd in p["nodes"]] for p in sp]
        same = all(_inside(((2 + c + 0.5) * cell, (2 + r + 0.5) * cell), polys) == bool(matrix[r][c])
                   for r in range(n) for c in range(n))
        results.append(("QR code: the outline gives back every module of the code", same))
    except ImportError:
        print("SKIP  generators: QR code (segno not installed)")
    card = g.test_card()
    results.append(("test card: 16 shapes, a text on the circle",
                    len(card.items) == 16 and any(it.on_path_of >= 0 for it in card.items)))
    for name, ok in results:
        print("%-5s generators: %s" % ("OK" if ok else "FAIL", name))
        errors += 0 if ok else 1
    return errors


def test_simulate():
    """Job simulation: layer order, travel moves, durations from the layer speeds."""
    from kerfly.core.layers import default_layers, CUT
    from kerfly.core.layout import Element
    from kerfly.core.shapes import ShapeSpec, build_design
    from kerfly.core.simulate import timeline, total_seconds
    errors = 0

    def check(name, ok, detail=""):
        nonlocal errors
        print("%-5s simulate: %s %s" % ("OK" if ok else "FAIL", name, detail))
        errors += 0 if ok else 1

    spec = ShapeSpec(kind="rectangle", width=40, height=30, operation="cut")
    e = Element(build_design(spec), x=1.0, y=-1.0, shape=spec)
    layers = default_layers()
    cut = [l for l in layers if l.kind == CUT][0]
    cut.speed, cut.passes = 10.0, 2
    steps = timeline([e], layers, JobSettings(), "mm")
    burn = sum(s.seconds for s in steps if s.burn)
    first = steps[0]
    check("rectangle 140 mm at 10 mm/s, 2 passes = 28 s of cutting", abs(burn - 28.0) < 1e-6, "(%.3f s)" % burn)
    check("starts with a travel move from home to the shape", not first.burn and (first.x0, first.y0) == (0.0, 0.0)
          and abs(first.x1 - 25.4) < 1e-6 or abs(first.y1 - 25.4) < 1e-6)
    check("total includes travel", total_seconds(steps) > burn)
    return errors


def test_snap():
    """Object snapping targets and preferences."""
    from kerfly.core.snap import CENTRE, CORNER, EDGE, MIDDLE, SnapShape, find_snap, snap_offset
    errors = 0

    def check(name, ok, detail=""):
        nonlocal errors
        print("%-5s snap: %s %s" % ("OK" if ok else "FAIL", name, detail))
        errors += 0 if ok else 1

    square = SnapShape([[(0, 0), (10, 0), (10, 10), (0, 10), (0, 0)]])
    line = SnapShape([[(20, 0), (40, 20)]])
    shapes = [square, line]
    check("corner", find_snap(10.4, -0.3, shapes, 1.0) == (10, 0, CORNER))
    check("centre of the box", find_snap(5.2, 4.9, shapes, 1.0) == (5.0, 5.0, CENTRE))
    check("middle of a side", find_snap(10.3, 5.2, shapes, 1.0) == (10.0, 5.0, MIDDLE))
    hit = find_snap(25.6, 4.4, shapes, 1.0)
    check("point on a line", hit is not None and hit[2] == EDGE and abs(hit[0] - hit[1] - 20) < 1e-9, str(hit))
    check("corner wins over the edge next to it", find_snap(0.5, 3.0, shapes, 3.5)[2] == CORNER)
    check("nothing near", find_snap(15, 15, shapes, 1.0) is None)
    off = snap_offset([(9.2, 10.6), (50, 50)], shapes, 1.5)
    check("moving shape: offset to the nearest target", off is not None
          and abs(off[0] - 0.8) < 1e-9 and abs(off[1] + 0.6) < 1e-9, str(off))
    from kerfly.core.snap import find_axis_snap
    al = find_axis_snap(30.4, 12.0, [(30.0, 0.0), (0.0, 12.3)], 0.5)
    check("in line with other corners: x and y", al is not None and al[0] == 30.0 and al[1] == 12.3
          and len(al[2]) == 2)
    check("in line: nothing near", find_axis_snap(15, 15, [(0, 0)], 0.5) is None)
    many = SnapShape([[(i * 0.01, 0.0) for i in range(20000)]])
    check("detailed shapes are thinned out", len(many.points) < 7000 and find_snap(199.99, 0, [many], 0.5))
    return errors


def main():
    with open(MANIFEST) as f:
        baseline = json.load(f)["cases"]
    failures = 0
    for name, (source, operation, overrides) in CASES.items():
        if source == "svg" and not INKSCAPE:
            print("SKIP  %-26s (Inkscape not installed)" % name)
            continue
        failures += run_case(name, source, operation, JobSettings(**overrides), baseline)

    for name, (source, operation, lines) in SETTINGS_FILE_CASES.items():
        if source == "svg" and not INKSCAPE:
            print("SKIP  %-26s (Inkscape not installed)" % name)
            continue
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
            f.write("\n".join(lines) + "\n")
        try:
            settings = config.job_settings_from_values(config.read_settings_file(f.name))
        finally:
            os.remove(f.name)
        failures += run_case(name, source, operation, settings, baseline)

    failures += test_settings_file()
    failures += test_images(baseline)
    failures += test_layout(baseline)
    failures += test_shapes()
    failures += test_layers(baseline)
    failures += test_job_position()
    failures += test_materials()
    failures += test_arrange()
    failures += test_snap()
    failures += test_curves()
    failures += test_simulate()
    failures += test_usblib()
    failures += test_udev()
    failures += test_generators()
    failures += test_cut_order()
    failures += test_pattern_fill()

    gui_modules = sorted(m for m in sys.modules if m.split(".")[0] in ("tkinter", "_tkinter", "PySide6", "PyQt6"))
    if gui_modules:
        failures += 1
        print("ERROR core imported GUI modules: %s" % ", ".join(gui_modules))
    else:
        print("OK    core runs without any GUI toolkit loaded")

    print("\n%d case(s) failed." % failures if failures else "\nAll cases passed.")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
