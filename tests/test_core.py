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
import sys

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(TESTS_DIR)
sys.path.insert(0, ROOT_DIR)
sys.path.insert(0, TESTS_DIR)

from kerfly.core.design import Design          # noqa: E402
from kerfly.core.settings import JobSettings   # noqa: E402
from kerfly.core import job, raster            # noqa: E402
from regression import synthetic_image, NGC, MANIFEST  # noqa: E402

# baseline case name -> (source, operation, JobSettings overrides)
CASES = {
    "png_reng_halftone":      ("png", "Raster_Eng", {}),
    "png_reng_grayscale":     ("png", "Raster_Eng", {"halftone": False}),
    "png_reng_negate":        ("png", "Raster_Eng", {"negate": True}),
    "png_reng_rotate_mirror": ("png", "Raster_Eng", {"rotate": True, "mirror": True}),
    "png_reng_up_step":       ("png", "Raster_Eng", {"engrave_up": True, "raster_step": 0.004}),
    "png_reng_feed":          ("png", "Raster_Eng", {"raster_feed": 200.0}),
    "ngc_gcode":              ("ngc", "Gcode_Cut",  {}),
}


def load_png(design):
    im = synthetic_image()
    design.reset()
    design.input_dpi = 1000.0
    w, h = im.size
    design.bounds = (0.0, w / design.input_dpi, 0.0, h / design.input_dpi)
    design.raster.set_image(im)


def load_ngc(design):
    from g_code_library import G_Code_Rip
    design.reset()
    g_rip = G_Code_Rip()
    g_rip.Read_G_Code(NGC, XYarc2line=True, arc_angle=2, units="in", Accuracy="")
    design.gcode.set_ecoords(g_rip.generate_laser_paths(g_rip.g_code_data), data_sorted=True)
    design.bounds = design.gcode.bounds


def main():
    with open(MANIFEST) as f:
        baseline = json.load(f)["cases"]
    failures = 0
    for name, (source, operation, overrides) in CASES.items():
        design = Design()
        settings = JobSettings(**overrides)
        if source == "png":
            load_png(design)
            raster.make_raster_coords(design, settings)
        else:
            load_ngc(design)
        chunks = job.build_job(design, settings, operation)
        data = job.egv_file_bytes(chunks[0].data)
        digest = hashlib.sha256(data).hexdigest()
        if digest == baseline[name]["sha256"]:
            print("OK    %-26s %8d B" % (name, len(data)))
        else:
            failures += 1
            print("DIFF  %-26s %8d B (baseline %d B)" % (name, len(data), baseline[name]["size"]))

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
