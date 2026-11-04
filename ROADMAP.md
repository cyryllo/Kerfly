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
- [x] Project files (`.kerfly`): layout, layers and copies of the source files
- [x] SVG without Inkscape (built-in Qt renderer; Inkscape is still used when
  installed, and for SVG text that is cut or engraved as an outline)
- [x] Material library export and import
- [x] Layout sized from the desktop font (KDE/GNOME), so it fits any font and
  language
- [x] `--self-test` and GitHub Actions on clean Windows and Ubuntu machines
- [x] Elements outside the work area drawn red; Start and Trace locked
- [x] Diagnostic log and report (Help menu, Report button)

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
| ~~SVG without Inkscape~~ (done: raster with the built-in Qt renderer; Inkscape still needed to turn cut/engrave text into paths). SVG curves for editing are read with svgelements (PyPI, MIT) | `svgelements.py` (also on PyPI) |

## Editor window (modelled on MeerK40t's interface)

| Feature | MeerK40t reference |
|---|---|
| Element tree / layers panel (select, hide, groups ~~done~~; reorder, nested groups) | `gui/wxmtree.py` |
| ~~Operations list: assign elements to raster, engrave or cut instead of by colour only~~ (done: layers) | `gui/opassignment.py`, `gui/gui_optypes.py` |
| ~~Select, move, scale and rotate with handles~~ (done) | `gui/scenewidgets/`, `gui/toolwidgets/toolplacement.py` |
| ~~Undo / redo~~ (done) | `core/undos.py` |
| ~~Grid and snapping~~ (done) | `gui/snapoptions.py`, `core/elements/grid.py` |
| ~~Snapping to other objects: corners, ends and middles of lines, points on curves, centres and edges of elements; for moving and for the drawing tools~~ (done) | `gui/snapoptions.py`, `gui/scenewidgets/` (MeerK40t "magnets"/snap points) |
| ~~Alignment and distribution, mirror~~ (done) | `gui/alignment.py`, `core/elements/align.py` |
| ~~Ruler, measure tool~~ (done) | `gui/toolwidgets/toolmeasure.py` |
| ~~Job simulation (play the path)~~ (done) | `gui/simulation.py` |
| ~~Material library (saved speed/power per material)~~ (done); export / import (done) | `gui/materialmanager.py`, `core/elements/materials.py` |
| ~~Toolbar~~ (done; every new command gets a button), themes | `gui/ribbon.py`, `gui/themes.py` |

## Drawing tools

| Tool | MeerK40t reference (`gui/toolwidgets/`) |
|---|---|
| ~~Rectangle (also rounded)~~ (done) | `toolrect.py` |
| ~~Ellipse, circle~~ (done) | `toolellipse.py`, `toolcircle.py` |
| ~~Line, regular polygon, polyline / free polygon~~ (done) | `toolline.py`, `toolpolyline.py`, `toolpolygon.py` |
| ~~Freehand drawing~~ (done, smoothed into curves) | `tooldraw.py` |
| ~~Bezier / vector path (pen tool)~~ (done) | `toolvector.py` |
| ~~Text (system fonts)~~ (done); text on a path | `tooltext.py`, `toollinetext.py` |
| ~~Node editing with Bezier handles, for drawn shapes and broken-apart SVG / DXF~~ (done) | `toolnodeedit.py`, `toolnodemove.py` |
| Cut a region out of an image | `toolimagecut.py` |
| ~~Tabs (bridges) on cut paths~~ (done: count and width per outline) | `tooltabedit.py` |

## Generators and processing

| Feature | MeerK40t reference |
|---|---|
| Text from Hershey / TrueType / SHX fonts (no Inkscape) | `extra/hershey.py`, `tools/ttfparser.py`, `tools/shxparser.py`, `tools/jhfparser.py` |
| ~~Hatch fill~~ (done: spacing, angle, cross-hatch); pattern fills (planned below) | `fill/fills.py`, `fill/patterns.py` (`fill/patternfill.py` is obsolete in MeerK40t) |
| Living hinges | `tools/livinghinges.py`, `tools/living_hinge_optimizer.py` |
| Image dithering (more methods than Floyd-Steinberg) | `image/dither.py` |
| Image adjustments (contrast, sharpen, crop, split) | `image/imagetools.py`, `extra/imageactions.py`, `gui/imagesplitter.py` |
| Bitmap to vector (trace) | `extra/potrace.py`, `extra/vtracer.py`, `extra/vectrace.py` |
| Path offset (kerf compensation) | `core/elements/offset_clpr.py`, `offset_mk.py` |
| ~~Boolean operations on shapes~~ (done: union, difference, intersection, exclusion) | `tools/polybool.py`, `extra/cag.py` |
| Kerf test and material test generators (material test: planned after the first laser test) | `tools/kerftest.py`, `gui/materialtest.py` |

### Pattern fills (planned)

Any closed shape (drawn, or from an ungrouped SVG / DXF) can be filled with a
pattern, clipped to its outline; holes stay empty.

- **The outline stays.** It keeps its own layer (cut or outline), and the fill
  is a separate part on a vector engrave layer, with its own speed and power.
  Example: a coaster whose edge is cut and whose inside gets engraved waves.
  Option to leave the outline out (fill only, like the current hatch).
- **Options:** pattern, spacing / tile size, angle, margin from the outline,
  line width of the motif.
- **Patterns** (more can be added later, so they are kept in a simple list):
  - lines: parallel (current hatch), cross-hatch, dashed, dotted, concentric
    (offset rings following the outline), spiral, radial lines
  - wavy lines ("wobble"): sine wave, zigzag / sawtooth, circles, gear, jigsaw,
    meander (Greek key)
  - tiles: grid, bricks, diamonds, herringbone / fishbone, chevron, honeycomb,
    triangles, fish scales, fabric weave, crosses, stars, dots
  - curves: Hilbert / Peano curves, Truchet tiles, Voronoi cells
  - custom: any drawn shape or SVG repeated in a grid (with optional
    alternate-row offset)
- The tile patterns are the same ones used for living hinges (cut instead of
  engraved), so both features share one pattern library.
- MeerK40t references: `fill/patterns.py` (tile patterns, shape pattern,
  concentric), `fill/fills.py` (scanline, Eulerian and spiral fills; wobbles:
  circle, sine wave, sawtooth, jigsaw, gear, meander, dashed).

## Packaging (later)

- Linux: AppImage. PyInstaller collects the program and libraries, and
  appimagetool packs the result. Builds run on an older glibc in GitHub
  Actions. USB access needs a udev rule: Kerfly will offer to install it once
  through `pkexec`. Inkscape stays external and optional (SVG text to paths).
- Windows: PyInstaller `.exe` and an installer that also sets up the libusb
  driver. Reference: Scorch's
  [K40 Whisperer Driver Installer](https://github.com/scorchworks/K40-Whisperer-Driver-Installer).
- Possibly a Debian `.deb` that installs the udev rule.
