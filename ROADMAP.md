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
- [x] First test on a real laser (Windows 10, M3 board) and its fixes: raster
  position in layouts, trace start, position after Stop; safety check that
  the head stays on the bed before a job is sent

## Next: complete the K40 Whisperer feature set in the new window

- [x] Move the head to the design corners and centre (temporary position)
- [x] Go to a given X/Y position
- [x] Test fire (M3)
- [x] Job time estimate
- [ ] Batch mode and post-job actions (`post_disp`, `post_exec`)
- [x] Open and send EGV files
- [ ] Rotary settings window parity
- [x] Design follows the head (toggle under the unlock button)
- [ ] Remember the view settings without "Save settings as default": the snap
  grid (on / off and its size), snap to objects, design follows the head.
  Now the grid is off again after every start unless the settings were saved
  as default. Keep them in Kerfly's own settings file, saved at once when
  they change; also a "Grid" option in Settings to have it on from the start.
- [ ] Idea: a toggle so that the plain arrow keys move the laser head (now
  Ctrl+arrows do; plain arrows move the selected element). Ignore key
  auto-repeat, so holding a key does not queue up moves; never in text fields

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
| Element tree / layers panel (select, hide, groups, ~~reorder~~ done; nested groups) | `gui/wxmtree.py` |
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
| ~~Text (system fonts)~~ (done); ~~text on a path~~ (done) | `tooltext.py`, `toollinetext.py` |
| ~~Node editing with Bezier handles, for drawn shapes and broken-apart SVG / DXF~~ (done) | `toolnodeedit.py`, `toolnodemove.py` |
| Cut a region out of an image | `toolimagecut.py` |
| ~~Tabs (bridges) on cut paths~~ (done: count and width per outline) | `tooltabedit.py` |

## Generators and processing

| Feature | MeerK40t reference |
|---|---|
| Text from Hershey / TrueType / SHX fonts (no Inkscape) | `extra/hershey.py`, `tools/ttfparser.py`, `tools/shxparser.py`, `tools/jhfparser.py` |
| ~~Hatch fill~~ (done; since 0.17 part of the pattern fills: Lines / Cross-hatch without the outline); pattern fills (step 1 done, see below) | `fill/fills.py`, `fill/patterns.py` (`fill/patternfill.py` is obsolete in MeerK40t) |
| ~~Living hinges~~ (step 1 done: Living hinge tool, straight / wavy / zigzag cuts, cut length, bridge, row spacing, direction, solid border); more hinge patterns later | `tools/livinghinges.py`, `tools/living_hinge_optimizer.py` |
| Image dithering (more methods than Floyd-Steinberg) | `image/dither.py` |
| Image adjustments (contrast, sharpen, crop, split) | `image/imagetools.py`, `extra/imageactions.py`, `gui/imagesplitter.py` |
| Bitmap to vector (trace) | `extra/potrace.py`, `extra/vtracer.py`, `extra/vectrace.py` |
| Path offset (kerf compensation) | `core/elements/offset_clpr.py`, `offset_mk.py` |
| ~~Boolean operations on shapes~~ (done: union, difference, intersection, exclusion) | `tools/polybool.py`, `extra/cag.py` |
| Kerf test and material test generators (material test: planned after the first laser test) | `tools/kerftest.py`, `gui/materialtest.py` |

### Pattern fills

Any closed shape (drawn, or from an ungrouped SVG / DXF) can be filled with a
pattern, clipped to its outline; holes stay empty.

- [x] Step 1 (0.17): Fill tool (bucket, Shift+F), Fill section in the options
  bar, outline kept on its own layer (or left out), spacing / angle / margin,
  eight patterns: lines, cross-hatch, waves, zigzag, circles, honeycomb,
  diamonds, bricks. Own clipping code (`kerfly/core/patterns.py`), no
  optional library needed.
- [ ] Step 2: more patterns (below), concentric rings following the outline
  (needs path offset, shared with kerf compensation), custom tile, line width
  of the motif.

- **The outline stays.** It keeps its own layer (cut or outline), and the fill
  is a separate part on a vector engrave layer, with its own speed and power.
  Example: a coaster whose edge is cut and whose inside gets engraved waves.
  Option to leave the outline out (fill only, like the current hatch).
- **Fill tool in the drawing tool strip on the right** (bucket icon), used like
  a drawing tool: pick it, choose the pattern in the options bar above the bed
  view (a row of small pattern previews plus the settings), then click a closed
  shape to fill it. Clicking a filled shape again changes its fill; with shapes
  already selected, choosing a pattern fills all of them. The fill of a
  selected shape can be changed or removed later in the options bar.
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

## Release tests (before every stable release)

Goal: every function of the window is clicked through automatically before a
stable release, the way a user does it, and the window is checked to show
the truth after every step. The unit tests (`tests/test_gui.py`) call the
window's methods directly, so they miss what a user sees: a list showing
"Lines" while the shapes have no pattern, a bar that does not refresh after a
click, a field that changes the wrong element. The user's own daily use stays
the main test; these tests catch what is easy to miss.

- [x] **Step 1: "the window tells the truth" checks.** One function, run
  after every step of the tests below, compares what is shown with the data:
  - every field and list of the options bar shows the value of the selected
    shape (or of the tool when nothing is selected): each field says which
    setting it shows, so the check is generic and covers new fields at once;
  - position and size fields = the element's real bounds; the element list =
    the elements (names, order, ticks, selection); the layers panel = the
    layers the elements use;
  - the bed view: one item per element, drawn where the element is;
  - the job compiles, stays on the bed, and its outline is where the
    elements are;
  - undo brings back exactly the state before the step, redo the state
    after it; a saved and reopened project is the same.
- [x] **Step 2: scripted session with real clicks** (`tests/test_release.py`).
  Real mouse and keyboard events (QTest), not method calls: draw every shape
  with its tool, choose every option from every drop-down list, type into
  every field, move / scale / rotate with handles, arrows and fields,
  select several, group, combine shapes, order buttons, fill, hinge (band
  width and position), text on a path, bridges, layers and the material
  library, trace, simulation, start / pause / stop on the fake laser, new
  project, save and open. After each step: the checks of step 1.
- [x] **Step 3: coverage list.** The test fails when a toolbar button, menu
  command, tool or options field was never used by the session: a new
  function cannot be released without its release test.
- [x] **Step 4: random sessions.** Thousands of random steps (draw, select,
  change an option, move, undo, ...) with a fixed seed, the step 1 checks
  after each one; a failure prints the seed and the steps to repeat it.
- [x] **Step 5: reference results.** For a set of sample projects (every
  shape, fill pattern, hinge, text on a path, bridges, raster): pictures of
  the bed view and of the simulation, and the exact laser data (as in
  `tests/regression.py`), compared with saved references, so a changed
  outline, cut order or cut preview shows up.
- [x] **Step 6: run them where it counts.** The release workflow runs the
  release tests on Linux and Windows before building the packages (a failed
  test stops the release), and the built programs run a short
  `--release-test` (fonts, Inkscape, USB library in the installed program).
- [x] **Step 7: test card for the laser.** A ready project
  (`tests/fixtures/release_card.kerfly`) with every operation on a small
  piece of plywood: raster, outline, cut, fill patterns, hinge, text on a
  path, bridges, holes before outlines, a size ruler. Before a feature
  release (1.x.0) it is cut on the machine with a short list of what to
  measure and compare; fix-only releases (1.x.y) need only the automatic
  tests.

## Milestone: GRBL lasers (after the K40 milestone)

Start only when everything on the K40 works and is confirmed on the machine
(the K40 milestone: the remaining K40 Whisperer features above and the
packages below). GRBL is a second, separate driver next to the K40 one: the
design still becomes cut lines, engrave lines and a raster, and only the
driver turns them into commands. The K40 path stays unchanged and is still
checked byte for byte.

- [ ] **Step 1: export G-code for GRBL** (File → Save G-code, toolbar button).
  Vectors as `G0` / `G1` with feed rate, power as `S`, laser mode `M4`
  (power follows the speed, clean corners); raster line by line with the
  power from the pixel brightness, white parts skipped, overscan at the line
  ends. Usable at once with other senders (LaserGRBL, UGS). Tests: the
  generated G-code checked against expected files.
- [ ] **Step 2: direct control over the serial port** (`pyserial`).
  Connect and read the board settings (`$$`: bed size, `$30` maximum power,
  `$32` laser mode); home `$H`, unlock `$X`, jog with `$J=`, trace boundary,
  start; pause, resume and stop with the real-time commands `!`, `~`,
  Ctrl-X; streaming that keeps the board's buffer full; alarms and errors
  shown as messages. GRBL reports the real head position, so the "position
  unknown after Stop" problem of the K40 goes away. Tests: a fake GRBL board,
  like the fake USB device for the K40.
- [ ] **Step 3: machine profiles.** Settings → Machine: K40 (Lihuiyu) or GRBL,
  each with its own bed size, power range, speeds and options (air assist
  `M8`); the window shows only what the chosen machine can do.
- [ ] **Step 4: test on a real GRBL machine** (diode laser or a K40 with a
  GRBL board). Windows: the boards usually use a CH340 USB chip; its driver
  goes into the installation guide.

## Packaging

- [x] Windows: PyInstaller program folder and an Inno Setup installer that can
  also run Scorch's K40 USB driver installer (`packaging/windows/kerfly.iss`).
- [x] Linux: AppImage from the PyInstaller folder, built on Ubuntu 22.04
  (`packaging/linux/build-appimage.sh`).
- [x] Release workflow (`.github/workflows/release.yml`): on a version tag
  builds both, runs their self-test and publishes the release with the notes
  from CHANGELOG.md.
- [ ] Debian `.deb` that uses the system's Python libraries (a few MB) with the
  udev rule, menu entry and icon, in an own signed APT repository on GitHub
  Pages (`https://cyryllo.github.io/Kerfly/apt`), modelled on LamaDeck's.
- [ ] AppImage: offer to install the udev rule once (through `pkexec`).

