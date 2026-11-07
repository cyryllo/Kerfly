# Licensing and third-party notices

Kerfly as a whole is distributed under the **GNU General Public License,
version 3 or (at your option) any later version** (GPL-3.0-or-later). The full
text is in [LICENSE](LICENSE).

Kerfly is a fork of K40 Whisperer 0.71 by Scorch. Some source files carry their
own copyright notices and licenses. All of them are compatible with
distributing the combined work under GPL-3.0-or-later. The original notices
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

## Kerfly core (`kerfly/`)

The `kerfly/core/` modules contain code moved out of `k40_whisperer.py` and
restructured for Kerfly. They carry both copyrights: 2017–2026 Scorch for the
original code, and 2026 Kerfly contributors for the changes. They are licensed
GPL-3.0-or-later.

## Files written for Kerfly

| File | Copyright | License |
|---|---|---|
| `convex_hull.py` | 2026 Kerfly contributors | GPL-3.0-or-later |
| `interpolate.py` | 2026 Kerfly contributors | GPL-3.0-or-later |
| `kerfly/gui/`, `kerfly.py` | 2026 Kerfly contributors | GPL-3.0-or-later |
| `tests/` | 2026 Kerfly contributors | GPL-3.0-or-later |

`convex_hull.py` and `interpolate.py` used to be short snippets copied from
Wikibooks and Stack Overflow (CC BY-SA content). CC BY-SA 3.0 is not formally
compatible with the GPL, so both were rewritten from scratch for Kerfly with
the same interface. They were checked to give identical results to the
originals, and the regression tests pass unchanged.

## Icons

| Files | Origin | License |
|---|---|---|
| `kerfly/gui/icons/tabler/*.svg` | [Tabler Icons](https://tabler.io/icons), Copyright (c) 2020-2026 Paweł Kuna | MIT (`kerfly/gui/icons/tabler/LICENSE`) |
| `kerfly/gui/icons/__init__.py` jog pad icons | drawn for Kerfly in the style of the K40 Whisperer icons | GPL-3.0-or-later |

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
| segno | BSD-3-Clause |
| Inkscape (external program, called as a subprocess) | GPL-2.0-or-later |
| PySide6 / Qt | LGPL-3.0, GPL-2.0 or GPL-3.0 (Kerfly uses them under the GPL-3.0) |

## Windows installer and AppImage

The ready-made packages (built by `.github/workflows/release.yml` from
`packaging/`) contain, besides Kerfly:

- **Python** and the libraries above, collected by **PyInstaller**
  (bootloader: GPL-2.0 with an exception that allows any program to use it).
  The licence texts of the libraries are in the package metadata folders
  (`_internal/*.dist-info`), `LICENSE` (GPL-3.0) and `licenses/LGPL-3.0.txt`.
  Qt and PySide6 are separate shared libraries, as the LGPL asks; their source
  code is at <https://code.qt.io/>.
- **Windows only: K40 USB driver installer** (`K40_Driver_Install.exe`), by
  Scorch, a modified version of Zadig / libwdi by Pete Batard, GPL-3.0 (libwdi:
  LGPL-2.1). It installs the libusb-win32 driver (LGPL-2.1 / GPL-2.0). Source:
  <https://github.com/scorchworks/K40-Whisperer-Driver-Installer>. The installer
  runs it only when the user ticks "Install the USB driver for the K40 laser".
  The build checks its SHA-256 sum before bundling it.
- **Windows only: `libusb0.dll`** of **libusb-win32 1.2.6.0** (Travis Lee
  Robinson, Stephan Meyer and others; LGPL-3.0, text in
  `licenses/libusb-win32-LGPL.txt`), next to `Kerfly.exe`, as K40 Whisperer
  ships it. Kerfly uses it only when Windows has no `libusb0.dll` of its own.
  Source: <https://sourceforge.net/projects/libusb-win32/>.
- **Windows only: the installer itself** is made with **Inno Setup**
  (Jordan Russell and Martijn Laan, Inno Setup License, a free licence that
  allows this use).
- **AppImage only: the AppImage runtime** of appimagetool (MIT).
- **macOS only: `libusb-1.0.0.dylib`** of **libusb 1.0** (LGPL-2.1-or-later,
  text in `licenses/LGPL-3.0.txt` covers the later versions; source:
  <https://github.com/libusb/libusb>), built by Homebrew, inside `Kerfly.app`
  so the laser's USB port works without installing anything.

## Libraries installed with Kerfly

These are installed by pip from `requirements.txt`. They are not copied into
this repository.

| Library | Licence | Used for |
|---|---|---|
| PySide6 (Qt for Python) | LGPL-3.0 | window and drawing |
| lxml | BSD-3-Clause | SVG reading (K40 Whisperer) |
| Pillow | MIT-CMU (HPND) | images |
| pyusb | BSD-3-Clause | USB connection to the laser |
| svgelements | MIT | reading SVG curves for node editing |
| pyclipper (optional) | MIT | offset of the boundary trace |
| segno | BSD-3-Clause | QR codes (Generators → QR code) |
