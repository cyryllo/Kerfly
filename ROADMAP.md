# Kerfly roadmap

Kerfly keeps the stable K40 Whisperer laser core (`egv.py`, `nano_library.py`
and the job generation in `kerfly/core`) unchanged, and checks it byte-for-byte
with the regression tests. New features are built around that core.

Many editing and drawing features are modelled on
[MeerK40t](https://github.com/meerk40t/meerk40t) (MIT licence). The references
below point to files in MeerK40t at commit `d511944e0` (September 2026).

- **Algorithm code** (no GUI) can be copied, keeping its MIT header and listing
  it in `THIRD-PARTY-NOTICES.md`.
- **MeerK40t's interface** is written for wxPython, so it cannot be copied. It
  is a model for behaviour, and Kerfly re-implements it in Qt on
  `QGraphicsScene`.
- **MeerK40t's laser drivers** (`lihuiyu/`, `ch341/`) are not used.

## Done

- [x] Regression tests against the unmodified K40 Whisperer 0.71
- [x] GUI-independent core (`kerfly/core`)
- [x] PySide6 main window with preview, jog, operations, settings, EGV export
- [x] Background job thread, with pause, resume and terminate
- [x] Editor, step 1: several elements on the bed; select, drag, scale and
  rotate with handles; X/Y/W/H/angle fields; the head moves to the design
  before a job
- [x] Editor, step 2: undo/redo, element list with visibility, snap grid,
  duplicate, centre on bed, arrow-key nudge; MeerK40t-style icon toolbar
- [x] Drawing tools, step 1: rectangle, ellipse, polygon, line, text (system
  fonts); cut / engrave outline / raster fill; tool strip on the right and
  options bar above the bed view
- [x] Layers with their own speed, passes, power and colour; element parts
  assigned to layers; material library (JSON in the user's settings folder)
- [x] Translations: English, Polish, German, Spanish, French (gettext;
  DE/ES/FR need a native speaker review)

## Next: complete the K40 Whisperer feature set in the new window

- [x] Move the head to the design corners and centre (temporary position)
- [x] Go to a given X/Y position
- [x] Test fire (M3)
- [x] Job time estimate
- [ ] Batch mode and post-job actions (`post_disp`, `post_exec`)
- [x] Open and send EGV files
- [ ] Rotary settings window parity

## Import more file types

| Feature | MeerK40t reference |
|---|---|
| ~~Bitmaps directly: PNG, JPG, BMP, TIFF, GIF, WebP~~ (done) | `image/imagetools.py` (loader) |
| PDF, EPS, AI, CDR, WMF via the Inkscape command line | `extra/inkscape.py` |
| LightBurn `.lbrn` / `.lbrn2` | `extra/lbrn.py` |
| xTool `.xcs` | `extra/xcs_reader.py` |
| EZCad `.ezd` | `extra/ezd.py` |
| ~~SVG without Inkscape~~ (done: raster with the built-in Qt renderer; Inkscape still needed to turn cut/engrave text into paths) | `svgelements.py` (also on PyPI) |

## Editor window (modelled on MeerK40t's interface)

| Feature | MeerK40t reference |
|---|---|
| Element tree / layers panel (select, hide ~~done~~; reorder, groups) | `gui/wxmtree.py` |
| ~~Operations list: assign elements to raster, engrave or cut instead of by colour only~~ (done: layers) | `gui/opassignment.py`, `gui/gui_optypes.py` |
| ~~Select, move, scale and rotate with handles~~ (done) | `gui/scenewidgets/`, `gui/toolwidgets/toolplacement.py` |
| ~~Undo / redo~~ (done) | `core/undos.py` |
| ~~Grid and snapping~~ (done; snapping to other objects still to do) | `gui/snapoptions.py`, `core/elements/grid.py` |
| Alignment and distribution | `gui/alignment.py`, `core/elements/align.py` |
| Ruler, measure tool | `gui/toolwidgets/toolmeasure.py` |
| Job simulation (play the path) | `gui/simulation.py` |
| ~~Material library (saved speed/power per material)~~ (done); export / import (done) | `gui/materialmanager.py`, `core/elements/materials.py` |
| ~~Toolbar~~ (done; every new command gets a button), themes | `gui/ribbon.py`, `gui/themes.py` |

## Drawing tools

| Tool | MeerK40t reference (`gui/toolwidgets/`) |
|---|---|
| ~~Rectangle (also rounded)~~ (done) | `toolrect.py` |
| ~~Ellipse, circle~~ (done) | `toolellipse.py`, `toolcircle.py` |
| ~~Line, regular polygon~~ (done); polyline, free polygon | `toolline.py`, `toolpolyline.py`, `toolpolygon.py` |
| Freehand drawing | `tooldraw.py` |
| Bezier / vector path | `toolvector.py` |
| ~~Text (system fonts)~~ (done); text on a path | `tooltext.py`, `toollinetext.py` |
| Node editing | `toolnodeedit.py`, `toolnodemove.py` |
| Cut a region out of an image | `toolimagecut.py` |
| Tabs (bridges) on cut paths | `tooltabedit.py` |

## Generators and processing

| Feature | MeerK40t reference |
|---|---|
| Text from Hershey / TrueType / SHX fonts (no Inkscape) | `extra/hershey.py`, `tools/ttfparser.py`, `tools/shxparser.py`, `tools/jhfparser.py` |
| Hatch and pattern fills | `fill/fills.py`, `fill/patternfill.py`, `fill/patterns.py` |
| Living hinges | `tools/livinghinges.py`, `tools/living_hinge_optimizer.py` |
| Image dithering (more methods than Floyd-Steinberg) | `image/dither.py` |
| Image adjustments (contrast, sharpen, crop, split) | `image/imagetools.py`, `extra/imageactions.py`, `gui/imagesplitter.py` |
| Bitmap to vector (trace) | `extra/potrace.py`, `extra/vtracer.py`, `extra/vectrace.py` |
| Path offset (kerf compensation) | `core/elements/offset_clpr.py`, `offset_mk.py` |
| Boolean operations on shapes | `tools/polybool.py`, `extra/cag.py` |
| Kerf test and material test generators | `tools/kerftest.py`, `gui/materialtest.py` |

## Packaging (later)

- Linux: AppImage. PyInstaller collects the program and libraries, and
  appimagetool packs the result. Builds run on an older glibc in GitHub
  Actions. USB access needs a udev rule: Kerfly will offer to install it once
  through `pkexec`. Inkscape stays external (only needed for SVG) until SVG
  is read without it.
- Windows: PyInstaller `.exe` and an installer that also sets up the libusb
  driver. Reference: Scorch's
  [K40 Whisperer Driver Installer](https://github.com/scorchworks/K40-Whisperer-Driver-Installer).
- Possibly a Debian `.deb` that installs the udev rule.
