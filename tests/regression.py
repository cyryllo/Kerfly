#!/usr/bin/env python3
"""
EGV regression harness for K40 Whisperer.

Loads the unmodified application headlessly (Tk mainloop disabled, message
boxes recorded instead of shown), opens fixture designs, runs each job type
with output redirected to an EGV file, and compares the bytes against the
stored baseline. The EGV stream is exactly what is sent to the laser over USB,
so identical bytes mean identical machine behaviour.

Usage (needs an X display; Xvfb is recommended):
    xvfb-run -a .venv/bin/python tests/regression.py            # check
    xvfb-run -a .venv/bin/python tests/regression.py --update   # rewrite baseline
    xvfb-run -a .venv/bin/python tests/regression.py -k png     # only matching cases
"""
import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(TESTS_DIR)
FIXTURES = os.path.join(TESTS_DIR, "fixtures")
BASELINE_DIR = os.path.join(TESTS_DIR, "baseline")
OUTPUT_DIR = os.path.join(TESTS_DIR, "output")
MANIFEST = os.path.join(BASELINE_DIR, "manifest.json")

SVG = os.path.join(FIXTURES, "shapes.svg")
DXF = os.path.join(FIXTURES, "shapes.dxf")
NGC = os.path.join(FIXTURES, "sample.ngc")

# (name, source, job method, settings overrides)
# source: "svg" | "dxf" | "ngc" | "png" (synthetic image injected directly,
# bypassing Inkscape, so the raster pipeline is tested deterministically).
CASES = [
    ("svg_vcut",                 "svg", "Vector_Cut",         {}),
    ("svg_veng",                 "svg", "Vector_Eng",         {}),
    ("svg_reng",                 "svg", "Raster_Eng",         {}),
    ("svg_raster_vector_cut",    "svg", "Raster_Vector_Cut",  {}),
    ("svg_trace",                "svg", "Trace_Eng",          {}),
    ("svg_vcut_no_inside_first", "svg", "Vector_Cut",         {"inside_first": 0}),
    ("svg_vcut_rotate_mirror",   "svg", "Vector_Cut",         {"rotate": 1, "mirror": 1}),
    ("svg_vcut_home_ur",         "svg", "Vector_Cut",         {"HomeUR": 1}),
    ("svg_vcut_passes2",         "svg", "Vector_Cut",         {"Vcut_passes": "2"}),
    ("svg_vcut_feeds",           "svg", "Vector_Eng_Cut",     {"Vcut_feed": "25", "Veng_feed": "50"}),
    ("svg_veng_cut_m1",          "svg", "Vector_Eng_Cut",     {"board_name": "LASER-M1"}),
    ("svg_all_b1",               "svg", "Raster_Vector_Cut",  {"board_name": "LASER-B1"}),
    ("dxf_vcut",                 "dxf", "Vector_Cut",         {}),
    ("dxf_veng",                 "dxf", "Vector_Eng",         {}),
    ("ngc_gcode",                "ngc", "Gcode_Cut",          {}),
    ("png_reng_halftone",        "png", "Raster_Eng",         {}),
    ("png_reng_grayscale",       "png", "Raster_Eng",         {"halftone": 0}),
    ("png_reng_negate",          "png", "Raster_Eng",         {"negate": 1}),
    ("png_reng_rotate_mirror",   "png", "Raster_Eng",         {"rotate": 1, "mirror": 1}),
    ("png_reng_up_step",         "png", "Raster_Eng",         {"engraveUP": 1, "rast_step": "0.004"}),
    ("png_reng_feed",            "png", "Raster_Eng",         {"Reng_feed": "200"}),
]

NEEDS_INKSCAPE = {"svg"}

# Cases captured through a fake USB device instead of "save EGV to file".
# The M3 board with power control enabled refuses EGV file output (power is set
# with separate USB commands between job stages), so those go through FakeK40.
USB_CASES = [
    ("usb_m3_power_all",   "svg", "Raster_Vector_Cut", {"board_name": "LASER-M3"}),
    ("usb_m3_power_levels","svg", "Raster_Vector_Cut", {"board_name": "LASER-M3", "Reng_power": "0.3",
                                                        "Veng_power": "0.6", "Vcut_power": "0.9"}),
    ("usb_m3_gcode",       "ngc", "Gcode_Cut",         {"board_name": "LASER-M3", "Gcode_power": "0.4"}),
    ("usb_m2_vcut",        "svg", "Vector_Cut",        {}),
]


class FakeK40:
    """Stands in for nano_library.K40_CLASS and records everything sent to the 'laser'."""

    def __init__(self):
        self.timeout = 200
        self.n_timeouts = 10
        self.log = bytearray()

    def _note(self, text):
        self.log += ("#%s\n" % text).encode()

    def send_data(self, data, update_gui=None, stop_calc=None, passes=1,
                  preprocess_crc=True, wait_for_laser=False):
        self._note("send_data passes=%s crc=%s wait=%s len=%d" % (passes, preprocess_crc, wait_for_laser, len(data)))
        self.log += bytes(data) + b"\n"

    def set_PWM_register(self, pct_power):
        self._note("set_PWM_register %r" % (pct_power,))

    def __getattr__(self, name):  # unlock_rail, home_position, ...
        def call(*a, **kw):
            self._note("%s %r %r" % (name, a, kw))
        return call


def synthetic_image():
    """600x400 px @1000 dpi: horizontal gradient with a dark disc and a light ring.
    Built per-pixel (no ImageDraw) so it does not depend on Pillow's rasterizer."""
    from PIL import Image
    w, h = 600, 400
    cx, cy = 300, 200
    data = []
    for y in range(h):
        for x in range(w):
            r2 = (x - cx) ** 2 + (y - cy) ** 2
            if r2 < 80 ** 2:
                v = 0
            elif r2 < 120 ** 2:
                v = 230
            else:
                v = int(x * 255 / (w - 1))
            data.append(v)
    im = Image.new("L", (w, h))
    im.putdata(data)
    return im


def inkscape_version():
    exe = shutil.which("inkscape")
    if not exe:
        return None
    try:
        out = subprocess.run([exe, "--version"], capture_output=True, text=True, timeout=60)
        return (out.stdout or out.stderr).strip().splitlines()[0]
    except Exception as e:
        return "unknown (%s)" % e


def sha256(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def first_diff(a_path, b_path):
    with open(a_path, "rb") as f:
        a = f.read()
    with open(b_path, "rb") as f:
        b = f.read()
    n = min(len(a), len(b))
    for i in range(n):
        if a[i] != b[i]:
            return i, len(a), len(b)
    return n, len(a), len(b)


def load_app():
    """Import k40_whisperer with GUI side effects neutralised. Returns (module, app, messages)."""
    # Isolate from the user's ~/k40_whisperer.txt so defaults are always used.
    os.environ["HOME"] = tempfile.mkdtemp(prefix="k40w_home_")
    if os.path.exists(os.path.join(ROOT_DIR, "k40_whisperer.txt")):
        sys.exit("ERROR: %s/k40_whisperer.txt exists and would override default settings." % ROOT_DIR)

    import tkinter
    import tkinter.messagebox

    messages = []

    def record(kind):
        def f(title=None, message=None, **kw):
            messages.append("%s: %s | %s" % (kind, title, message))
            return True
        return f

    for name in ("showinfo", "showwarning", "showerror"):
        setattr(tkinter.messagebox, name, record(name))
    tkinter.messagebox.askokcancel = record("askokcancel")
    tkinter.messagebox.askyesno = record("askyesno")
    tkinter.Tk.mainloop = lambda self, n=0: None
    tkinter.Misc.bell = lambda self, displayof=0: None

    sys.argv = ["k40_whisperer.py"]
    sys.path.insert(0, ROOT_DIR)
    cwd = os.getcwd()
    import k40_whisperer as k40w  # runs the startup code, chdir()s to ROOT_DIR
    os.chdir(cwd)
    return k40w, k40w.app, messages


def run(args):
    k40w, app, messages = load_app()

    ink = inkscape_version()
    if ink:
        app.inkscape_path.set(shutil.which("inkscape"))

    # Snapshot defaults of every setting any case touches.
    defaults = {}
    all_cases = [c + ("file",) for c in CASES] + [c + ("usb",) for c in USB_CASES]
    for _, _, _, overrides, _ in all_cases:
        for key in overrides:
            defaults.setdefault(key, getattr(app, key).get())

    png = synthetic_image()
    out_dir = BASELINE_DIR if args.update else OUTPUT_DIR
    os.makedirs(out_dir, exist_ok=True)

    manifest_old = {}
    if os.path.exists(MANIFEST):
        with open(MANIFEST) as f:
            manifest_old = json.load(f)

    results = {}
    failures = 0
    class ConfigureEvent:
        widget = app.master

    for name, source, job, overrides, mode in all_cases:
        if args.k and args.k not in name:
            continue
        if source in NEEDS_INKSCAPE and not ink:
            print("SKIP  %-28s (Inkscape not installed)" % name)
            results[name] = {"status": "skipped"}
            continue

        for key, val in defaults.items():
            getattr(app, key).set(val)
        for key, val in overrides.items():
            getattr(app, key).set(val)
        # Re-derive display_power (M3 power mode) exactly as the GUI does on resize.
        app.Master_Configure(ConfigureEvent(), update=1)
        del messages[:]

        if source == "svg":
            app.Open_SVG(SVG)
        elif source == "dxf":
            app.Open_DXF(DXF)
        elif source == "ngc":
            app.Open_G_Code(NGC)
        elif source == "png":
            app.resetPath()
            app.input_dpi = 1000.0
            w, h = png.size
            app.Design_bounds = (0.0, w / app.input_dpi, 0.0, h / app.input_dpi)
            app.RengData.set_image(png.copy())
            app.wim, app.him = w, h
            app.aspect_ratio = float(w - 1) / float(h - 1)
        app.menu_View_Refresh()

        out = os.path.join(out_dir, name + (".egv" if mode == "file" else ".usb"))
        if os.path.exists(out):
            os.remove(out)
        if mode == "file":
            app.k40 = None
            getattr(app, job)(output_filename=out)
        else:
            fake = FakeK40()
            app.k40 = fake
            getattr(app, job)()
            app.k40 = None
            if fake.log:
                with open(out, "wb") as f:
                    f.write(bytes(fake.log))

        if not os.path.exists(out) or os.path.getsize(out) == 0:
            failures += 1
            print("ERROR %-28s no output produced. status=%r" % (name, app.statusMessage.get()))
            for m in messages:
                print("      " + m.replace("\n", " "))
            results[name] = {"status": "error", "messages": list(messages)}
            continue

        digest = sha256(out)
        entry = {"sha256": digest, "size": os.path.getsize(out), "source": source,
                 "job": job, "settings": overrides, "capture": mode}
        if messages:
            entry["messages"] = list(messages)
        results[name] = entry

        if args.update:
            print("WROTE %-28s %8d B  %s" % (name, entry["size"], digest[:12]))
            continue

        ref = manifest_old.get("cases", {}).get(name)
        if not ref or "sha256" not in ref:
            print("NEW   %-28s (no baseline)" % name)
        elif ref["sha256"] == digest:
            print("OK    %-28s %8d B" % (name, entry["size"]))
        else:
            failures += 1
            base = os.path.join(BASELINE_DIR, os.path.basename(out))
            off, la, lb = first_diff(base, out)
            print("DIFF  %-28s first difference at byte %d (baseline %d B, now %d B)" % (name, off, la, lb))

    if args.update:
        manifest = {
            "environment": {
                "python": platform.python_version(),
                "platform": platform.platform(),
                "pillow": __import__("PIL").__version__,
                "lxml": __import__("lxml.etree").etree.__version__,
                "inkscape": ink,
                "k40_whisperer": k40w.version,
            },
            "cases": results,
        }
        with open(MANIFEST, "w") as f:
            json.dump(manifest, f, indent=2, sort_keys=True)
        print("Baseline written to %s" % BASELINE_DIR)

    print("\n%d case(s) failed." % failures if failures else "\nAll cases passed.")
    return 1 if failures else 0


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--update", action="store_true", help="regenerate baseline EGV files")
    p.add_argument("-k", help="run only cases whose name contains this string")
    rc = run(p.parse_args())
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(rc)  # skip Tk teardown noise
