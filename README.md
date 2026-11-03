# Kerfly

Kerfly is laser cutter control software for K40-class CO2 lasers with Lihuiyu
(M2 Nano family) controller boards. It runs on Linux (Debian first) and Windows.

Kerfly is a fork of **[K40 Whisperer](https://www.scorchworks.com/K40whisperer/k40whisperer.html)**
by Scorch (scorchworks.com), version 0.71, which is known for its stable laser
control. The original release is tagged `upstream-0.71` in this repository.

## Status

Early development. The code is currently K40 Whisperer 0.71 plus a regression
test suite. Planned work:

- separate the laser core from the user interface
- a new Qt (PySide6) interface
- built-in drawing and editing tools
- direct import of more file formats (PNG/JPG/BMP/TIFF/WebP, PDF, and others)

The laser output (EGV data sent over USB) is checked byte-for-byte against the
original 0.71 after every change. See [Regression tests](#regression-tests).

## Running from source (Debian / Ubuntu)

```bash
sudo apt install python3-venv python3-tk inkscape
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python k40_whisperer.py
```

Inkscape is required: SVG files are rasterized through it.

USB access without root needs a udev rule. See [README_Linux.txt](README_Linux.txt).

## Running from source (Windows)

Install Python 3 and Inkscape, then run `pip install -r requirements.txt` and
`python k40_whisperer.py`. The laser needs the libusb-win32 driver, which you
can install with [Zadig](https://zadig.akeo.ie/).

## Project layout

- `kerfly/core/`: the GUI-independent laser core. It contains the SVG, DXF
  and G-code loaders, settings file handling, design data, raster
  preparation, path ordering and EGV job generation. Nothing in it imports a
  GUI toolkit.
- `k40_whisperer.py`: the original Tkinter interface. It now calls
  `kerfly.core`. A new PySide6 interface is planned.
- `egv.py`, `nano_library.py`: EGV encoding and USB communication with the
  controller board. These are unchanged from K40 Whisperer.
- `tests/`: regression tests.

## Regression tests

```bash
.venv/bin/python tests/test_core.py          # core only, no display needed
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
