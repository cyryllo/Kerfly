#!/usr/bin/env python3
"""
Reference results of the release tests (ROADMAP: release tests, step 5).

Every sample project in tests/fixtures/release (made by
tools/make_release_samples.py) is opened in the window, and what Kerfly makes
of it is compared with saved references (tests/references/):

- the laser data: the exact bytes of the EGV job;
- the job as the simulation plays it: order of the cuts, length cut and
  travelled, time, the area covered, and every move (as a fingerprint);
- the bed view: a picture of the bed, compared pixel by pixel (a small
  tolerance for smoothed edges). A difference writes the new picture and a
  difference picture next to the references, in out/.

The texts sample depends on the fonts of the computer: it is not compared,
only drawn into the screenshots.

    .venv/bin/python tests/test_references.py                 # compare
    .venv/bin/python tests/test_references.py --update        # after a deliberate change: new references
    .venv/bin/python tests/test_references.py --screenshots DIR   # Full HD window pictures to look at

Copyright (C) 2026 Kerfly contributors
Licensed under the GNU General Public License v3 or later. See LICENSE.
"""
import argparse
import glob
import hashlib
import json
import math
import os
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp(prefix="kerfly_refs_cfg_")
os.environ["APPDATA"] = os.environ["XDG_CONFIG_HOME"]
TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(TESTS_DIR)
sys.path.insert(0, ROOT)
sys.path.insert(0, TESTS_DIR)

from PySide6.QtCore import QRectF, Qt  # noqa: E402
from PySide6.QtGui import QColor, QImage, QPainter  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from kerfly.core import config  # noqa: E402
from kerfly.gui.main_window import MainWindow  # noqa: E402
from kerfly.gui.simulation import simulation_steps  # noqa: E402
from fakes import run_until_idle  # noqa: E402

SAMPLES = os.path.join(TESTS_DIR, "fixtures", "release")
REFS = os.path.join(TESTS_DIR, "references")
REF_FILE = os.path.join(REFS, "release.json")
OUT = os.path.join(REFS, "out")
FONT_DEPENDENT = {"texts"}
PX_PER_MM = 3                       # bed pictures: 3 pixels per millimetre
PIXEL_TOLERANCE = 48                # a pixel differs when a colour channel differs more than this
MAX_DIFFERENT = 0.002               # ... and the picture differs when more than 0.2 % of the pixels do


def open_sample(path, app):
    values = dict(config.DEFAULT_VALUES)
    values.update(grid_mm="0", language="en")
    w = MainWindow(values)
    w.resize(1920, 1080)
    w.open_project(path)
    w.preview.select_element([])
    for _ in range(5):
        app.processEvents()
    return w


def egv_of(w, app):
    out = tempfile.mktemp(suffix=".egv")
    w.start_job(output_file=out)
    run_until_idle(app, w)
    if not os.path.exists(out):
        return {"egv_sha256": None, "egv_bytes": 0, "status": w.statusBar().currentMessage()}
    data = open(out, "rb").read()
    os.remove(out)
    return {"egv_sha256": hashlib.sha256(data).hexdigest(), "egv_bytes": len(data)}


def simulation_of(w):
    """What the simulation plays: a readable summary and a fingerprint of every move."""
    steps = simulation_steps(w)
    burn = [s for s in steps if s.burn]
    length = lambda s: math.hypot(s.x1 - s.x0, s.y1 - s.y0)
    order = []
    for s in steps:                                  # the layers in the order they run
        if s.burn and (not order or order[-1] != s.layer):
            order.append(s.layer)
    fingerprint = hashlib.sha256(";".join("%.2f,%.2f,%.2f,%.2f,%d,%s" % (s.x0, s.y0, s.x1, s.y1, s.burn, s.kind)
                                          for s in steps).encode()).hexdigest()
    xs = [v for s in burn for v in (s.x0, s.x1)]
    ys = [v for s in burn for v in (s.y0, s.y1)]
    return {"moves": len(steps), "burn_moves": len(burn),
            "burn_mm": round(sum(length(s) for s in burn), 1),
            "travel_mm": round(sum(length(s) for s in steps if not s.burn), 1),
            "seconds": round(sum(s.seconds for s in steps), 1),
            "area_mm": [round(min(xs), 2), round(min(ys), 2), round(max(xs), 2), round(max(ys), 2)] if xs else None,
            "layer_order": order,
            "first_cuts": [[round(s.x0, 2), round(s.y0, 2), round(s.x1, 2), round(s.y1, 2)] for s in burn[:6]],
            "fingerprint": fingerprint}


def bed_picture(w):
    view = w.preview
    bed = view.bed_rect
    image = QImage(int(bed.width() * PX_PER_MM), int(bed.height() * PX_PER_MM), QImage.Format_RGB32)
    image.fill(QColor("white"))
    p = QPainter(image)
    p.setRenderHint(QPainter.Antialiasing, True)
    view.scene().render(p, QRectF(image.rect()), bed, Qt.IgnoreAspectRatio)
    p.end()
    return image


def compare_pictures(new, ref):
    """(fraction of differing pixels, difference picture)."""
    if new.size() != ref.size():
        return 1.0, None
    diff = QImage(new.size(), QImage.Format_RGB32)
    diff.fill(QColor("white"))
    n = 0
    ref = ref.convertToFormat(QImage.Format_RGB32)
    for y in range(new.height()):
        for x in range(new.width()):
            a, b = new.pixelColor(x, y), ref.pixelColor(x, y)
            if max(abs(a.red() - b.red()), abs(a.green() - b.green()), abs(a.blue() - b.blue())) > PIXEL_TOLERANCE:
                n += 1
                diff.setPixelColor(x, y, QColor("red"))
            elif a != QColor("white"):
                diff.setPixelColor(x, y, QColor(200, 200, 200))
    return n / float(new.width() * new.height()), diff


def first_difference(new, ref):
    for key in ("egv_bytes", "layer_order", "moves", "burn_moves", "burn_mm", "travel_mm", "seconds", "area_mm",
                "first_cuts", "fingerprint", "egv_sha256"):
        if new.get(key) != ref.get(key):
            return "%s: %r, the reference has %r" % (key, new.get(key), ref.get(key))
    return ""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--update", action="store_true", help="write new references (after a deliberate change)")
    parser.add_argument("--screenshots", metavar="DIR", help="also save Full HD window pictures here")
    args = parser.parse_args()
    app = QApplication(sys.argv)
    refs = json.load(open(REF_FILE)) if os.path.exists(REF_FILE) and not args.update else {}
    new_refs = {}
    failures = 0
    if args.update:
        os.makedirs(REFS, exist_ok=True)
    for path in sorted(glob.glob(os.path.join(SAMPLES, "*.kerfly"))):
        name = os.path.splitext(os.path.basename(path))[0]
        w = open_sample(path, app)
        if args.screenshots:
            os.makedirs(args.screenshots, exist_ok=True)
            w.show()
            for _ in range(10):
                app.processEvents()
            w.grab().save(os.path.join(args.screenshots, "%s.png" % name))
        picture = bed_picture(w)
        if name in FONT_DEPENDENT:
            if args.screenshots:
                picture.save(os.path.join(args.screenshots, "%s_bed.png" % name))
            print("--    %s: depends on the fonts here, not compared" % name)
            w._dirty = False
            w.close()
            continue
        result = egv_of(w, app)
        result.update(simulation_of(w))
        new_refs[name] = result
        ref_png = os.path.join(REFS, "%s.png" % name)
        if args.update:
            picture.save(ref_png)
            print("REF   %s: %d EGV bytes, %d moves, %.1f mm cut" % (name, result["egv_bytes"], result["moves"],
                                                                     result["burn_mm"]))
        else:
            problems = []
            if name not in refs:
                problems.append("no reference (run with --update once)")
            else:
                diff = first_difference(result, refs[name])
                if diff:
                    problems.append("job differs: " + diff)
            if os.path.exists(ref_png):
                fraction, diff_img = compare_pictures(picture, QImage(ref_png))
                if fraction > MAX_DIFFERENT:
                    os.makedirs(OUT, exist_ok=True)
                    picture.save(os.path.join(OUT, "%s_new.png" % name))
                    if diff_img is not None:
                        diff_img.save(os.path.join(OUT, "%s_diff.png" % name))
                    problems.append("bed view differs in %.2f %% of the pixels (see %s)" % (
                        100 * fraction, os.path.relpath(OUT, ROOT)))
            else:
                problems.append("no reference picture")
            print("%-5s %s %s" % ("FAIL" if problems else "OK", name, "; ".join(problems)))
            failures += bool(problems)
        w._dirty = False
        w.close()
    if args.update:
        os.makedirs(REFS, exist_ok=True)
        with open(REF_FILE, "w") as f:
            json.dump(new_refs, f, indent=1, sort_keys=True)
        print("references written to", os.path.relpath(REFS, ROOT))
        return 0
    print("All references match." if not failures else "%d samples differ from their references." % failures)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
