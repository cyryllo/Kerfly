# Kerfly

Kerfly is laser cutter control software for K40-class CO2 lasers with Lihuiyu
(M2 Nano family) controller boards. It runs on Linux (Debian first) and Windows.

Kerfly is a fork of **[K40 Whisperer](https://www.scorchworks.com/K40whisperer/k40whisperer.html)**
by Scorch (scorchworks.com), version 0.71, which is known for its stable laser
control. The original release is tagged `upstream-0.71` in this repository.

![Kerfly main window](docs/screenshot.png)

## Status

Early development (0.1). Kerfly has a new Qt (PySide6) window. It can open
SVG, DXF and G-code files, and bitmap images (PNG, JPG, BMP, TIFF, GIF, WebP)
for raster engraving without Inkscape.

Kerfly has drawing tools in a strip on the right of the bed view, like
LightBurn's: rectangle (with rounded corners), ellipse, regular polygon, line
and text in any installed font. Each shape is cut, engraved as an outline, or
filled as a raster engraving. Position, size and rotation of the selected element,
and the options of the selected shape or tool (operation, corner radius,
text, font), are shown in a ribbon-style bar above the bed view.

Designs are placed on a picture of the laser bed. You can put several files
on the bed, drag them with the mouse, scale and rotate them with handles, or
type their position, size and angle. The editor has undo and redo, a snap
grid, duplicate, centre on the bed and an element list where elements can be
left out of the job. A toolbar with labelled groups (File, Edit, Arrange,
View), in the style of MeerK40t, gives one-click access to the editing
commands. Machine control (connect, home, trace, start, stop) is in the panel
on the left. When a job starts, the laser head first
moves to the design. "Place design at the head" keeps the K40 Whisperer way of
working, where the design starts where the head is.

It can jog the head, move it to the design corners or to a given position,
and run raster engrave, vector engrave, vector cut, G-code and boundary trace
jobs. It estimates the job time, saves jobs as EGV files and sends existing
EGV files. On M3 boards it also offers test fire and power per operation.
Long jobs run in the background. Pause stops the laser for a moment and the
same button resumes it; Stop ends the job immediately.

The original K40 Whisperer window (`k40_whisperer.py`) is still included and
uses the same core. Batch mode is not in the new window yet.

Planned: the remaining K40 Whisperer features, more file formats, an editor
window and drawing tools. See [ROADMAP.md](ROADMAP.md).

The laser output (EGV data sent over USB) is checked byte-for-byte against the
original 0.71 after every change. See [Regression tests](#regression-tests).

## Running from source (Debian / Ubuntu)

```bash
sudo apt install python3-venv python3-tk inkscape
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python kerfly.py               # new window
.venv/bin/python k40_whisperer.py        # original K40 Whisperer window
```

Inkscape is required: SVG files are rasterized through it.

USB access without root needs a udev rule. See [README_Linux.txt](README_Linux.txt).

## Running from source (Windows)

Install Python 3 and Inkscape, then run `pip install -r requirements.txt` and
`python kerfly.py`. The laser needs the libusb-win32 driver, which you
can install with [Zadig](https://zadig.akeo.ie/).

## Languages

Kerfly is available in English, Polish, German, Spanish and French. It uses
the system language by default. You can change it in Settings → Advanced →
Language.

The German, Spanish and French translations have not yet been reviewed by
native speakers. Corrections are welcome.

To translate Kerfly into another language or correct a translation:

1. Install the developer tools: `pip install -r requirements-dev.txt`
2. To add a language, add its code to `LANGUAGES` in `kerfly/i18n.py` and run
   `python tools/i18n.py`. This creates
   `kerfly/locale/<code>/LC_MESSAGES/kerfly.po`.
3. Translate the `.po` file, for example with [Poedit](https://poedit.net/).
4. Run `python tools/i18n.py` to compile it, then `python tests/test_i18n.py`
   to check it.

Developers: wrap every user-visible string in `_()`, or use `N_()` for strings
in tables that are translated later. Then run `python tools/i18n.py`.

## Project layout

- `kerfly/core/`: the GUI-independent laser core. It contains the SVG, DXF
  and G-code loaders, settings file handling, design data, raster
  preparation, path ordering and EGV job generation. Nothing in it imports a
  GUI toolkit.
- `kerfly/gui/`: the new PySide6 interface. Start it with `kerfly.py`.
- `k40_whisperer.py`: the original Tkinter interface. It now calls
  `kerfly.core`.
- `egv.py`, `nano_library.py`: EGV encoding and USB communication with the
  controller board. These are unchanged from K40 Whisperer.
- `tests/`: regression tests.

## Regression tests

```bash
.venv/bin/python tests/test_core.py          # core only, no display needed
.venv/bin/python tests/test_gui.py           # new window, offscreen
.venv/bin/python tests/test_i18n.py          # translations complete and up to date
sudo apt install xvfb
xvfb-run -a .venv/bin/python tests/regression.py   # full application
```

There are 25 test cases. They cover vector cut, vector engrave, raster, trace
and G-code jobs, M1/M2/M3/B1 boards, rotate, mirror, home in upper right and
multiple passes. Each case compares the exact bytes the laser would receive
with the baseline produced by the unmodified 0.71. M3 power mode is captured
through a fake USB device. SVG-based baselines depend on the Inkscape version
(currently 1.4).

## License

Kerfly is free software, distributed under the **GNU General Public License,
version 3 or later** (GPL-3.0-or-later). See [LICENSE](LICENSE).

- Copyright (C) 2017–2026 Scorch: the original K40 Whisperer.
- Copyright (C) 2026 Kerfly contributors: changes made in this fork.

Some files come from other projects (Inkscape extensions, a MIT-licensed speed
code library, small snippets from public websites) and keep their own notices.
[THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md) lists each file, its author
and its license.

## Credits and disclaimer

All credit for the laser control core goes to **Scorch**, the author of
K40 Whisperer. Kerfly is an independent fork. It is not affiliated with or
endorsed by Scorch or scorchworks.com. Please report Kerfly bugs here, not to
the K40 Whisperer author.

This program controls a laser. It is provided WITHOUT ANY WARRANTY (see
sections 15–16 of the GPL). Never leave a running laser unattended.
