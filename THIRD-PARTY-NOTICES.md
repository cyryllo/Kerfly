# Licensing and third-party notices

Kerfly as a whole is distributed under the **GNU General Public License,
version 3 or (at your option) any later version** (GPL-3.0-or-later). The full
text is in [LICENSE](LICENSE).

Kerfly is a fork of K40 Whisperer 0.71 by Scorch. Some source files carry their
own copyright notices and licenses. All of them are compatible with
distributing the combined work under GPL-3.0-or-later (except the two marked
under [Open item](#open-item), which are under review). The original notices
in each file are kept as they are. When you modify a file, add your own notice
next to the existing one rather than replacing it.

## Files from K40 Whisperer (Scorch, scorchworks.com)

| File | Copyright | License |
|---|---|---|
| `k40_whisperer.py` | 2017–2026 Scorch | GPL-3.0-or-later |
| `dxf.py` | 2018 Scorch | GPL-3.0-or-later |
| `ecoords.py` | 2018 Scorch | GPL-3.0-or-later |
| `g_code_library.py` | 2017 Scorch | GPL-3.0-or-later |
| `egv.py` | 2017–2025 Scorch | GPL-2.0-or-later |
| `nano_library.py` | 2017–2025 Scorch | GPL-2.0-or-later |
| `svg_reader.py` | 2017–2021 Scorch | GPL-2.0-or-later |
| `embedded_images.py` | Scorch (no header) | distributed with K40 Whisperer under GPL |
| `emblem`, `scorchworks.ico` | Scorch | distributed with K40 Whisperer under GPL |

## Files from Inkscape 0.92 extensions

| File | Copyright | License |
|---|---|---|
| `inkex.py` | 2005, 2010 Aaron Spike and contributors | GPL-2.0-or-later |
| `simplepath.py`, `simplestyle.py`, `cubicsuperpath.py` | 2005 Aaron Spike | GPL-2.0-or-later |
| `bezmisc.py` | 2005 Aaron Spike, 2010 Nick Drobchenko | GPL-2.0-or-later |
| `ffgeom.py` | 2005 Aaron Cyril Spike | GPL-2.0-or-later |
| `simpletransform.py` | 2006 Jean-Francois Barraud, 2010 Alvin Penner | GPL-2.0-or-later |
| `cspsubdiv.py` | Inkscape extensions (no header in this copy) | GPL-2.0-or-later |

## Other sources

| File | Origin | License |
|---|---|---|
| `LaserSpeed.py` | LHYMICRO-GL speed code library, also used in MeerK40t | MIT (stated in the file) |
| `windowsinhibitor.py` | [Deluge-PreventSuspendPlus](https://github.com/h3llrais3r/Deluge-PreventSuspendPlus) | GPL-3.0-or-later (per that project's `setup.py`) |
| `convex_hull.py` | [Wikibooks: Monotone chain convex hull](https://en.wikibooks.org/wiki/Algorithm_Implementation/Geometry/Convex_hull/Monotone_chain) | CC BY-SA (Wikibooks content license). See [Open item](#open-item) |
| `interpolate.py` | [Stack Overflow answer](https://stackoverflow.com/questions/7343697/linear-interpolation-python) | CC BY-SA 3.0 (Stack Overflow content license at the time). See [Open item](#open-item) |

### Open item

`convex_hull.py` and `interpolate.py` are short snippets copied from websites
licensed under Creative Commons BY-SA. CC BY-SA 4.0 is one-way compatible with
GPLv3. CC BY-SA 3.0 is not formally compatible. Both snippets are a few lines
of standard algorithms (monotone chain convex hull, linear interpolation). They
are planned to be replaced with independent implementations, which the
regression tests will verify for identical output.

## Code borrowed from MeerK40t

Code taken from [MeerK40t](https://github.com/meerk40t/meerk40t) in the future
is MIT-licensed (Copyright (c) 2021 meerk40t). MIT code can be included in a
GPL project, but its copyright and permission notice must be preserved. Each
borrowed file keeps its MIT header, and the file is listed here.

| File | Origin in MeerK40t | License |
|---|---|---|
| (none yet) | | |

## Runtime dependencies (not bundled in this repository)

| Package | License |
|---|---|
| Python | PSF License |
| Tk / tkinter | Tcl/Tk License (BSD-style) |
| lxml | BSD-3-Clause |
| Pillow | MIT-CMU (HPND) |
| pyusb | BSD-3-Clause |
| pyclipper / Clipper | MIT / Boost Software License |
| Inkscape (external program, called as a subprocess) | GPL-2.0-or-later |
| PySide6 (planned) | LGPL-3.0 |

If a binary build (Windows `.exe`, AppImage) bundles any of these, it must
include their license texts.
