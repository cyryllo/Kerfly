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
- [x] Remember the view settings without "Save settings as default": snap
  grid on / off and its size, snap to objects, design follows the head
  (saved at once in Kerfly's window.ini); Settings → View has them too

## Import more file types

| Feature | MeerK40t reference |
|---|---|
| ~~Bitmaps directly: PNG, JPG, BMP, TIFF, GIF, WebP~~ (done) | `image/imagetools.py` (loader) |
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

## New versions

- [x] Step 1 (2026-11-12): once a day at start, a question to GitHub's list of
  releases; a bar above the bed with a link to the new release (Later, Skip
  this version); Help → Check for updates and a toolbar button; on by
  default, off in Settings → Advanced. Nothing downloaded by Kerfly.
- [ ] Step 2, only if users ask for it: **Update now**, always after asking,
  never during a job. Windows: download the new installer and run it silently
  (Inno Setup), then start the new version (the system asks for admin rights).
  AppImage: download the new file and swap it in place. macOS: only the link
  (without Apple's paid signing, replacing the app runs into the system's
  protection). Every download checked against SHA-256 sums published with
  the release; the previous version stays linked on the releases page. No
  silent updates: Kerfly runs a machine, a new version must never arrive in
  the middle of the work.

## Optional: engrave each design separately (raster layers)

Asked for by a user (2026-11-12; see also issue #2). Planned as an optional
function, for later.

**The problem.** On one raster layer all the pictures on the bed are joined
into one image. The head engraves it row by row, and every row runs from the
first dark point to the last one, across the empty gaps between the designs.
With designs side by side (names on several products in a row) most of the
time goes on driving over the gaps: two 50 × 50 mm pictures 90 mm apart take
31.8 min on one layer, 17.0 min when each is engraved on its own.

**What works today.** Put each design on its own raster layer (Layers panel:
**+** → Raster engrave, then the Layer list above the bed): layers run one
after another in the same job, so it is fast, but with many designs it means
many layers to make and keep track of.

**The planned option (B).** A tick box at a raster layer: **"Each design
separately"**. With it on, the designs on that layer are engraved one after
another, each in its own area (all with this layer's speed, power and
passes), as if each had its own layer, but without making layers. Still one
job, one Start.

- Which designs are "one": each element on the bed (a group counts as one).
- Order: as in the element list (the same order as the other layers).
- The time in the Layers panel, the simulation and the job all follow it.
- Off by default: with the designs touching or overlapping it gives nothing.
- Release-test step: two pictures with a gap on a layer with the option, the
  laser data and the time compared with two separate layers (must be equal).

**Considered and left out for now (A):** putting every newly added design on a
new raster layer by itself (reusing an empty one). Gives the same time, and
also separate speeds per design, but the Layers panel fills up with layers;
only if users need different settings per design.

## Run one kind of work: Engrave, Outline, Cut buttons

Asked for by a user (2026-11-10), as K40 Whisperer's three buttons (Raster
Engrave, Vector Engrave, Vector Cut) were used: engrave first, check, then cut.

- [x] Switched on in **Settings** ("Engrave, Outline and Cut buttons next to
  Start"), off by default: those who work with layers keep a plain window.
- [x] Three buttons next to **Start** (machine control on the left):
  **Engrave**, **Outline**, **Cut**. Each runs all ticked layers of that kind,
  in their order and each with its own speed, power and passes (two cut layers
  with different speeds are both cut). Start still runs everything.
- [x] The same in the Laser menu; time estimate and the "head stays on the
  bed" check for just that part; greyed out when there is nothing of that kind.
- [x] Release test steps: each button on the stand-in laser, only that kind
  of data sent.

## Basic editing commands and the right-click menu

Asked for by users (2026-11-10): Kerfly has Duplicate but no clipboard, and
the right mouse button only pans the view. K40 Whisperer had no menu there
(a right-drag moved the head without the design).

- [x] Inkscape's keys (2026-11-11): Ctrl+G / Ctrl+Shift+G group / ungroup,
  Ctrl+[ / Ctrl+] rotate 90°, H / V mirror, Ctrl++ / Ctrl+- / Ctrl+* / Ctrl+^
  union / difference / intersection / exclusion (Go to X/Y moved to Ctrl+Alt+G).
- [x] **Copy, Cut, Paste** (Ctrl+C, Ctrl+X, Ctrl+V; Edit menu and the Edit
  group of the toolbar) and **Paste in place** (Ctrl+Alt+V), as in Inkscape:
  elements with their layers, also from one project to another; Paste puts
  them at the mouse, Paste in place where they were.
- [x] **Select all** (Ctrl+A), **Deselect** (Esc on the bed; Ctrl+Shift+A, as Esc stops a running job), as in Inkscape.
- [x] **Right-click menu on an element or the selection** (a right-drag still
  pans the view; a right-click without moving opens the menu):
  - Copy, Cut, Paste, Duplicate, Delete;
  - Group / Ungroup;
  - **Layer ▸** the layers of its kind, to move it with one click (for
    example each design on its own raster layer, so they are engraved one
    after another, issue #2);
  - Combine shapes ▸ (union, difference, intersection, exclusion), Offset;
  - Order ▸ (up, down, first, last), Align ▸;
  - Rotate 90°, Mirror;
  - Fill with a pattern / Remove the pattern, Text on a path, Edit nodes;
  - Centre on the bed;
  - Leave out of the job (the tick of the element list).
- [x] **Right-click menu on the empty bed:** **Move the head here** (laser
  connected; what K40 Whisperer's right-drag did), Paste, Select all, Fit
  view, Grid on / off.
- [x] Release test steps: Layer ▸, Leave out of the job and Move the head here with real right clicks (the other entries are the Edit menu's commands, used there).

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
| Bitmap to vector (trace), like LightBurn's Trace Image (button "Trace" in the options bar of a selected picture) | `extra/potrace.py`, `extra/vtracer.py`, `extra/vectrace.py` |
| ~~Path offset (kerf compensation)~~ (done: Offset tool in the drawing tools on the right, kerf column of cut layers and in the material library, concentric fill pattern; pyclipper) | `core/elements/offset_clpr.py`, `offset_mk.py` |
| ~~Boolean operations on shapes~~ (done: union, difference, intersection, exclusion) | `tools/polybool.py`, `extra/cag.py` |
| ~~Kerf test and material test generators~~ (done, Generators group; also finger-joint box, gear, puzzle, ruler, QR code, rubber stamp, laser test card) | `tools/kerftest.py`, `gui/materialtest.py` |
| More generators: ~~round stamps with text around the circle~~ (done), living-hinge boxes, more box types (sliding lid, dividers) | `boxes.py` (not in MeerK40t) |

### Pattern fills

Any closed shape (drawn, or from an ungrouped SVG / DXF) can be filled with a
pattern, clipped to its outline; holes stay empty.

- [x] Step 1 (0.17): Fill tool (bucket, Shift+F), Fill section in the options
  bar, outline kept on its own layer (or left out), spacing / angle / margin,
  eight patterns: lines, cross-hatch, waves, zigzag, circles, honeycomb,
  diamonds, bricks. Own clipping code (`kerfly/core/patterns.py`), no
  optional library needed.
- [ ] Step 2: more patterns (below), ~~concentric rings following the
  outline~~ (done, with the path offset of kerf compensation), custom tile,
  line width of the motif.

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
- [x] **Step 6: run them where it counts.** The release session and the
  random sessions run on the developer's computer before every version tag;
  GitHub runs the references and `--release-test` on every push, and the
  built programs run `--release-test` (fonts, Qt plugins, libraries in the
  installed program) before they are released.
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

## Maybe some day

Set aside for now (not planned; back on the list only when users need it).

- PDF, EPS, AI, CDR, WMF import through the Inkscape command line (set aside
  2026-11-13; MeerK40t reference: `extra/inkscape.py`).

## Packaging

- [x] Windows: PyInstaller program folder and an Inno Setup installer that can
  also run Scorch's K40 USB driver installer (`packaging/windows/kerfly.iss`).
- [x] Linux: AppImage from the PyInstaller folder, built on Ubuntu 22.04
  (`packaging/linux/build-appimage.sh`).
- [x] Release workflow (`.github/workflows/release.yml`): on a version tag
  builds both, runs their self-test and publishes the release with the notes
  from CHANGELOG.md.
- [x] macOS: `Kerfly.app` in a `.dmg` for Apple Silicon and Intel, with libusb inside, built and
  checked on GitHub (a preview; added to the 1.1.0 release with a `macos-v1.1.0` tag).
- [ ] macOS: confirm the USB connection with a K40 on a Mac (users with Macs report).
- [ ] macOS: signing and notarization (needs a paid Apple Developer account), so it opens without
  "Open Anyway".
- [ ] Debian `.deb` that uses the system's Python libraries (a few MB) with the
  udev rule, menu entry and icon, in an own signed APT repository on GitHub
  Pages (`https://cyryllo.github.io/Kerfly/apt`), modelled on LamaDeck's.
- [x] Linux (AppImage too): Laser → Allow USB access for the laser… installs the udev rule
  through `pkexec`; offered by itself when connecting fails for want of permission.

