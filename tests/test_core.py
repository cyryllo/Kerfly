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
