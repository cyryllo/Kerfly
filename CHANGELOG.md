# Kerfly changelog

Version numbers:

- **1.0.0** is the first stable release;
- the **second number** goes up with every release that adds features (by
  10 when a new module is added);
- the **third number** goes up for releases that only fix bugs.

## Unreleased

### Fixed

- The colour square and text of the Engrave only, Outline only and Cut only
  buttons are centred (they sat against the left edge).

## 1.4.0 (2026-11-13)

Copy and paste, a right-click menu, a text editor for stamps, boxes that fit
the bed, where each design comes from, and checking for new versions.

### Fixed

- **Stamp: streaks across the letters and a dashed frame on Windows**, in the
  preview, the simulation and the engraving. The stamp is now painted in Qt's
  usual colour format and only then made black and white, and a missing font
  (DejaVu Sans on Windows) is replaced by Arial instead of an artificial
  bold.
- **The job simulation opened twice** after a second click; a second click
  now brings the open one to the front.
- **Linux AppImage: SVG files did not open when Inkscape is installed** (the
  program hung). The programs Kerfly starts (Inkscape, the browser) got the
  AppImage's own libraries, and Inkscape failed on its older C++ library; they
  now get the system's.

### Added

- **New versions:** once a day at start Kerfly asks GitHub whether a new
  version is out (nothing about the user or the work is sent). A bar above
  the bed then shows it, with **See the release** (its page: what is new and
  the files), **Later** and **Skip this version**. **Help → Check for
  updates** (toolbar **Updates**) asks at once. On by default; switched off
  in Settings → Advanced. Nothing is downloaded or installed by Kerfly.
- **Copy, cut and paste** as in Inkscape: Ctrl+C, Ctrl+X, Ctrl+V (pasted at
  the mouse pointer when it is over the bed, otherwise 5 mm further), Ctrl+Alt+V
  pastes in place; also into another project in the same window (groups stay
  groups, layers go along by name). **Select all** (Ctrl+A) and **Deselect**
  (Esc on the bed, Ctrl+Shift+A). In the Edit menu and a new **Clipboard**
  group of the toolbar, together with Duplicate and Delete.
- **Engrave only, Outline only, Cut only**: to run one kind of work at a
  time (for example engrave, check, then cut), each runs all the ticked
  layers of its kind with their own settings. Small buttons above Start,
  always visible also on small screens, switched on in Settings → View (off
  by default); also in the Laser menu. Their tooltips show the time of their
  part.
- **Where each design comes from:** the element list shows an opened file
  with its folder (Customer A › design.svg), and the bottom bar the folders and
  file of the design under the mouse pointer (or of the selected one), the
  whole path in its tooltip; designs of the same name from different folders
  (one folder per customer) can be told apart. Saved projects, copies and the
  parts of a split file keep where they came from.
- **Stamp text editor**: the text of the rectangular stamp is written in a
  small editor that shows it as it will look, with **B** bold, **I** italic,
  **U** underline, **A+ / A−** bigger and smaller letters and the alignment of
  the lines, for each part of the text (for example the name big and bold,
  the address smaller).
- **Finger-joint box fits the bed**: the parts are laid out on the work area;
  those that do not fit go on a next sheet at the same place, on its own
  unticked cut layer (Sheet 2, …). **Each part on its own layer** as an option.
- **Puzzle with round tabs**: a narrow neck and a round head, each tab a
  little different.
- **Home the head after a job** (Settings → Machine): after a finished job
  the head goes back to 0, 0, ready for the next piece, without pressing
  Home (not after Stop, and not after a boundary trace). The design stays
  where it is; the next Start drives the head to it.
- **Right-click menu** on the bed (a right click without dragging; a right
  drag still pans the view). On an element: its commands, with **Layer ▸**
  to move all the selected elements to another layer in one click (for
  example each design on its own raster layer, issue #2), combine shapes,
  order, align, turn, mirror, fill, edit nodes, **Leave out of the job**. On
  the empty bed: **Move the head here** (the design stays where it is),
  paste, select all, fit, grid.

## 1.3.3 (2026-11-12)

Easier work on small screens (laptops with 1366 × 768).

### Changed

- **The mouse wheel changes a number field or a list only after it was
  clicked.** Scrolling the left panel on a small screen (1366 × 768) to
  reach Start changed the speeds of the layers the wheel passed over; now the
  panel scrolls and the values stay. Click into a field to change it with the
  wheel.
- **Start, Pause and Stop stay at the bottom of the left panel**, always
  visible, also when the panel scrolls on a small screen.

## 1.3.2 (2026-11-11)

(1.3.0 and 1.3.1 were tagged but not released: their Linux package could not be
built while Ubuntu's package servers did not answer. Everything below is new
since 1.2.1.)

Important fixes: the laser always gets the job that is on the screen, and with the
home in the upper right several designs come out where they are on the screen.
Keyboard shortcuts as in Inkscape.

### Fixed

- **The laser could get an older job than the one on the screen.** To start
  faster, Kerfly keeps each layer's laser data, but it was reused after the
  design had changed: after opening another file (without moving the head),
  the laser engraved the previous design; after moving an element to another
  layer, a layer engraved elements that were no longer on it; an element
  left out of the job (unticked in the element list) was still engraved. The
  kept data is now used only while the elements, their places and their
  layers are exactly the same.
- **Home in the upper right: a layout of several designs came out mirrored**
  (each text right, but the designs in each other's places). The job mirrors
  the design for the machine's reversed x axis; the designs are now placed in
  it as they lie on the bed. A single design gives the same laser data as
  before.

### Changed

- **Keyboard shortcuts as in Inkscape:** **Ctrl+G** groups and
  **Ctrl+Shift+G** ungroups (before: Ctrl+Shift+G and Ctrl+Alt+G); Go to
  X/Y position moved from Ctrl+G to **Ctrl+Alt+G**.

### Added

- More keys as in Inkscape: **Ctrl+[** / **Ctrl+]** rotate by 90°, **H** /
  **V** mirror the selection (with the bed view in focus), **Ctrl++** union,
  **Ctrl+-** difference, **Ctrl+\*** intersection, **Ctrl+^** exclusion. The
  old keys (Ctrl+L, Ctrl+R, Ctrl+Shift+H, Ctrl+Shift+V) still work.

## 1.2.1 (2026-11-10)

### Fixed

- **SVG files with Polish letters such as Ł, Ę or Ń (for example in layer
  names) did not open on Windows** ("latin-1" error, issue #1): the file was
  read in the system's text encoding instead of the encoding written in the
  file. DXF and G-code files with texts in another encoding open too.
- When a file cannot be opened, the reason is written to the log, so the
  diagnostic report shows it.

## 1.2.0 (2026-11-09)

Parts at their exact size, a new Offset tool and round stamps.

### Added

- **Kerf compensation.** The laser burns away a thin line, so a part cut
  along its outline came out a little smaller and its holes a little larger.
  Cut layers now have a **Kerf** column (and the material library a kerf for
  each material): type the width of your laser's cut (measure it with
  Generators → Kerf test) and the outlines are cut half of it further out,
  the holes half of it further in, so the parts come out at their drawn
  size. Bridges are cut into the moved outline, open lines are cut as drawn.
  0 (the default) leaves the job exactly as before.
- **Offset** tool in the drawing tools on the right (Shift+O, also Edit →
  Offset): set the distance, round or sharp corners and *Keep the original*
  in the options bar, then click closed shapes to draw a new outline around
  them (a negative distance: inside them). **Offset selected** does it for
  shapes selected before. For a border around a text, a frame around a part
  or a smaller copy inside.
- **Concentric** fill pattern: rings following the outline inwards.
- **Round stamp** generator: text around the top and the bottom (the same
  letter height for both, a dot on each side), an outer and an inner ring,
  text lines or a picture in the middle, usual diameters (30 to 50 mm) or
  your own. Inverted and mirrored for rubber, with a round cut outline.
- **macOS** (preview, not yet tested with a laser): Kerfly for Macs with
  Apple Silicon and with Intel processors, in a disk image, with everything
  the laser's USB port needs inside.

### Changed

- **Job simulation**: what the laser has burnt so far turns red, on every
  layer. An engraved picture turns red only where it is dark, row by row;
  before, the simulation covered the whole picture with grey lines. Moves
  with the laser off stay grey dashed lines.

### Fixed

- **The language chosen in Settings did not come after a restart** unless
  the settings were also saved as default (File → Save settings as
  default); reported on Windows 11. The language is now kept at once, like
  the grid and snapping.
- Curves made by the generators: the node editor drew their nodes shifted
  from the shape.

## 1.1.0 (2026-11-06)

### Changed

- The snap grid (on or off, and its size), snapping to objects and "Design
  follows the head" are remembered for the next start at once, without
  "Save settings as default". Settings has a new View tab with them.

### Added

- **Generators** (new toolbar group and menu): ready designs from a few
  numbers, each with a preview and the last numbers remembered, inserted at
  the laser head as one group and one undo step:
  - **Material test**: fields with their own speed and power (or passes),
    each on a layer of its own, the values engraved;
  - **Finger-joint box**: bottom, walls and lid with fingers, inside or
    outside sizes, kerf compensation;
  - **Kerf test**: a comb to measure the kerf and slots to find the fit;
  - **Gear** with involute teeth; **Puzzle**; **Ruler**; **QR code**;
  - **Stamp**: text, a picture and a frame in the usual stamp sizes,
    inverted and mirrored for rubber, with the cut outline;
  - **Test card**: every operation on a piece of plywood, to check the laser.

  QR codes use the new library segno (BSD licence), installed with Kerfly
  and included in the packages.
- Linux: **Laser → Allow USB access for the laser…** adds the rule for the
  laser's USB port with one click (the system asks for the password once),
  so the AppImage needs no terminal commands. Kerfly offers it by itself
  when it cannot connect for want of permission.

## 1.0.1 (2026-11-06)

### Fixed (found by the new release tests)

- After deleting the selected element (or undoing it away, or a new
  project), the options bar and the Layer list above the bed kept showing
  the deleted element.
- Undo of deleting a layer did not bring the layer back (its shapes stayed
  on the default layer). Adding and deleting layers are now steps of
  Undo / Redo.
- Combine shapes → Difference cut sometimes the first shape out of the
  second: the order of the selected shapes changed from run to run. Now it
  is always the order of the element list (the other shapes are cut out of
  the one highest in the list), and a union starts its outline at the same
  place every time.
- A level or upright line could not be made longer or shorter by typing
  its width (height) in the position fields; its height (width) field showed
  0.01 instead of 0.

### Tests

- Release tests (`tests/test_release.py`): a whole working session in the
  real window on a Full HD screen, with real mouse clicks and key presses:
  every drawing tool, every field of the options bar for every kind of
  shape, every command of the menus and toolbars, the panels, the stand-in
  laser. After each step the window must show what its data holds
  (`kerfly/gui/truth.py`), and each change is undone and redone. The test
  fails when a command, a field or a control was never used.
- The GUI tests check after each step that the window tells the truth, and
  change settings through the fields, as a user does.

## 1.0.0 (2026-11-06)

The first stable release: Kerfly is ready for everyday work with K40 lasers.

Kerfly 1.0 runs K40 lasers with Lihuiyu (M2 Nano family) boards on
Windows 10 / 11 (installer) and Linux (AppImage): drawing and node editing,
layers and a material library, pattern fills, living hinges, text on a path,
bridges, SVG, DXF, G-code and pictures, projects in one file, boundary trace,
simulation and job time, and a check that the head stays on the bed before
anything is sent.

### Documentation

- README, installation guide, user guide and website describe only the two
  ready-made packages: the Windows installer (with the "Windows protected
  your PC" warning of an unsigned installer) and the Linux AppImage with the
  rule for the laser's USB port. Running from source, tests, translations
  and packaging moved to the new DEVELOPMENT.md, linked at the bottom.

### Fixed

- Fill and Living hinge tools: clicking a shape that was already selected
  cut the hinge (or filled it), but the options bar kept showing "No hinge" /
  "No pattern"; it now shows what the shape got.

## 0.19.1 (2026-11-06)

### Changed

- The order buttons (up, down, to the start, to the end) are beside the
  element list on the Design tab instead of in the toolbar.
- The element list also shows a single element (it appeared only with two).

### Fixed

- Fill and Living hinge tools with shapes selected: the options bar showed
  the pattern a click gives (Lines), not what the selected shapes have; it
  now shows "No pattern" / "No hinge" for shapes without one, and changing a
  number under "No pattern" no longer fills anything.

## 0.19.0 (2026-11-06)

Fixes from the second laser test (Windows 10, the 0.18.0 installer).

### Fixed

- **The installed program could not connect to the laser** ("USB error: No
  backend available") while the same PC worked from source: the packed
  program did not find `libusb0.dll`. Kerfly now looks for it itself (where
  pyusb looks, then `C:\Windows\System32`, then next to the program) and the
  Windows installer also brings its own `libusb0.dll` (libusb-win32 1.2.6.0,
  the version of the K40 driver), used only when Windows has none. The log
  and the self-test say where it was found, or where Kerfly looked.
- **Fill / Living hinge tools with several shapes selected:** only the first
  choice reached all of them (the selection was lost); the pattern shown
  first could not be applied. Every choice now reaches all selected shapes.

### Changed

- **The element list is the order of the job.** Within a layer the laser
  does the element at the top of the list first; K40 Whisperer's path sorting
  had mixed the elements by distance (a triangle, ellipse and rectangle were
  cut as triangle, rectangle, ellipse). Inside one element inner shapes are
  still cut first. The order buttons are now **Move up (earlier)**, **Move
  down (later)**, **To the start** and **To the end** (PgUp, PgDown, Ctrl+PgUp,
  Ctrl+PgDown); the simulation shows the same order. A single opened file is
  cut as before (byte-identical to K40 Whisperer).
- **Trace boundary as a rectangle**: it ran along the convex outline, so
  under a curve it followed the curve. Now it drives round the rectangle
  around the design (Settings → Vector: "Boundary trace as a rectangle", on by
  default; off: the outline, as in K40 Whisperer).
- **Open lines are cut from the end nearer to the head**, so the head no
  longer runs to the far end of a curve first.

### New

- **Living hinge in a band**: the width of the band with cuts (0: the whole
  shape, as before) and where its middle is, from the middle of the shape.
- **File → New project** (Ctrl+N, toolbar **New**): an empty bed with the
  default layers; asks to save unsaved changes first.

## 0.18.0 (2026-11-05)

### New

- **Ready-made packages.** Each release now has a **Windows installer**
  (`Kerfly-<version>-windows-setup.exe`: Start menu entry, desktop icon,
  uninstaller, and the option to install the K40 USB driver with Scorch's
  driver installer) and a **Linux AppImage** (`Kerfly-<version>-x86_64.AppImage`,
  runs without installing). No Python needed. GitHub Actions builds both from
  `packaging/` when a version is tagged, runs the self-test of each, and
  publishes the release with the notes from this changelog.

## 0.17.0 (2026-11-05)

### New

- **Pattern fills.** The new **Fill with a pattern** tool (bucket, Shift+F, on
  the tool strip) fills closed shapes with engraved lines in a pattern: lines,
  cross-hatch, waves, zigzag, circles, honeycomb, diamonds or bricks, with
  size, angle and a margin from the outline. Click a shape to fill it;
  selected shapes get the chosen pattern at once. The outline keeps its own
  layer, so a cut shape is still cut and the pattern is engraved on an
  outline layer (a second Layer list chooses which); the outline can also be
  left out. Holes stay empty. A selected shape shows the Fill section to
  change or remove its pattern. Saved in projects, one undo step.
- **Text on a path.** The **Text on a path** tool (Shift+T, on the tool
  strip): click a line, curve or shape to put the selected text on it, or,
  with no text selected, a new one typed in the options bar.
  Every letter stands on the line, turned along it, with the font's kerning;
  centred on open lines, at the top of closed shapes. Dragging the text
  slides it along the line (round and round on a circle). The options bar
  sets the start along the path, the distance from the line, the other side,
  or makes it straight again. An existing text is put on a shape with
  **Edit → Put text on path**. Saved in projects.
- **Letter spacing** for every text (the field with the AV icon in the Font
  section). The fields of a text on a path have icons too.
- **Living hinges.** The **Living hinge** tool (Shift+H) cuts a field of cuts
  into a closed shape so the sheet can bend: straight, wavy or zigzag cuts,
  with cut length, bridge between cuts, row spacing, direction and a solid
  border along the outline. The cuts are cut before the outline. Selected
  shapes get the chosen hinge at once; saved in projects, one undo step.
- **Tool strip in groups**: selecting, drawing, and operations on shapes
  (text on a path, fill, living hinge, measure).
- **Icons beside every field** of the options bar (rotation, bridges, corner
  radius, sides, font size, letter spacing, fill, hinge, text on a path), with
  a tooltip saying what the field does.
- **Order of elements**: Bring forward / Send backward (toolbar group
  **Order**, PgUp / PgDown in the bed view) and Bring to front / Send to back
  (Ctrl+PgUp / Ctrl+PgDown, Edit menu). Groups move together.

### Changed

- **Hatch is part of the pattern fills.** The separate Hatch section of the
  options bar is gone: choose the **Lines** or **Cross-hatch** pattern and
  switch the outline off. The laser data are the same as before, and hatched
  shapes of older projects open this way. The pattern size now goes down to
  0.05 mm, as the hatch spacing did.

### Fixed

- The window could not be made narrower than about 1550 px while a text was
  selected (its options did not fit), so on smaller screens it was wider than
  the screen. The options bar now scrolls sideways when its sections do not
  fit.

## 0.16.0 (2026-11-05)

### New

- **Report a problem on GitHub** (Help menu, **Bug report** button). Kerfly
  saves the diagnostic report and opens the report form on GitHub with the
  version, system and board filled in; the report file is dragged into it.
- **Report forms on GitHub** for laser problems (wrong place, power or speed,
  head running into the frame), other bugs, feature ideas and translation
  fixes. They ask for the diagnostic report, the design and photos. Reports
  can be written in English or Polish.
- **README in Polish** (`README_pl.md`), with a screenshot of the Polish
  window.
- **User guide** in English and Polish (`docs/guide.md`, `docs/pl/guide.md`):
  first start, the window, moving the head, files, drawing, layers, running
  a job, settings, all keyboard shortcuts, troubleshooting. **Help → User
  guide** (F1) opens it in the program's language.
- **Project website** <https://cyryllo.github.io/Kerfly/> (English and
  Polish), built from `docs/` by GitHub Actions on every push.
- `tools/make_screenshots.py` takes all screenshots of the README and the
  guide in English and Polish from the real window.
- **Logo and program icon**: a K whose upper arm is a laser beam. It is the
  window and taskbar icon (on Windows Kerfly gets its own taskbar entry
  instead of Python's). `tools/make_icons.py` renders `kerfly.png` and
  `kerfly.ico` from `kerfly/gui/icons/kerfly.svg`.
- **Design follows the head** (square button under the unlock button, beside
  the jog arrows; Ctrl+Alt+H; green when on).
  When on, the arrows, Go to X/Y and Home move the design together with the
  laser head, as in K40 Whisperer, and the arrows keep the design on the bed.
  The corner and centre buttons still only move the head. The setting is
  kept.

### Changed

- The jog pad buttons are larger (76 px squares), as tall as the machine
  buttons beside them.
- A test checks that no keyboard shortcut is used twice.

## 0.15.0 (2026-11-05)

Fixes from the first test on a real laser (Windows 10, LASER-M3 board).

### Fixed (laser output)

- **Raster engraving too high on the bed.** A picture was engraved too high
  when the layout had other elements too (for example a picture and a cut
  outline), or when the picture was scaled or rotated. The engraving moved up
  by the distance between the bottom of the layout and the home position, and
  the head could run into the frame. Cut and outline engraving were in the
  right place. The trace boundary of such a layout reached too high for the
  same reason. Cause: K40 Whisperer measures raster scan lines from the bottom
  of the picture, but a layout of several elements was built in bed
  coordinates. A layout is now built from (0, 0) like a loaded file. A single
  unchanged element was not affected and is still byte-identical to K40
  Whisperer.
- **Trace boundary starts where the head is.** The trace first ran along the
  top edge to the upper right corner and back, then went round. It now starts
  at the corner nearest the head (upper left). The old start point came from
  the pyclipper library (used for the trace gap); K40 Whisperer does the
  same. The K40 Whisperer window (`k40_whisperer.py`) keeps the old start, so
  its laser data stay byte-identical.

### New

- **Safety check before sending.** Kerfly checks every head position of the
  generated laser data (job and trace boundary). If the head would leave the
  laser bed by more than 1 mm, nothing is sent and a message says which
  edge and by how much. Not checked: the X direction with home in the upper
  right, and the Y direction on the rotary.
- **Head position after Stop.** The K40 does not report where the head is.
  After a job is stopped while sending, the status bar says that the head
  position is unknown and to press Home before the next job.
- **Progress bar fills with the percentage** of the current step (preparing
  the data, sending to the laser). The small moving bar on its right still
  shows that Kerfly is working.

### Fixed

- The diagnostic log got the same status message thousands of times
  ("Waiting for the laser to finish." while the laser runs), so the report
  only held the last minutes. Each message is now logged once in a row.

## 0.14.0 (2026-11-04)

### Fixed (laser output)

- **Wrong position of a layer with a single untransformed element.** When the
  layout had several elements and one layer (for example Cut) held just one
  element that was not rotated, scaled or mirrored, that element was cut
  relative to the layout's corner instead of at its own place on the bed.
  Present since 0.1.0. A single element alone on the bed was not affected,
  and is still byte-identical to K40 Whisperer.

### New

- **The layer decides what the laser does.** The separate operation list in
  the shape options is gone: select an element and choose its layer. On an
  outline layer a closed shape can be **filled with lines** (hatch).
- Pictures (raster engraving) are shown in the colour of their layer, as the
  lines are (dark = the layer colour, greys lighter).
- **Element list as in LightBurn**: each element shows the colour squares and
  names of its layers ("Rectangle · Cut").
- **Any layer for a drawn shape.** The Layer list above the bed view shows
  every layer of the left panel (cut, outline engrave, raster engrave and the
  ones you added). A layer of another kind changes the shape's operation:
  outline engrave, or fill for raster layers (closed shapes). A hatch stays a
  hatch on an outline layer.

- **Curves module.**
  - **Pen** tool (B, on the tool strip):
    - click for a corner, or press and drag for a smooth node with curve
      handles;
    - click the first point to close the shape; double-click or Enter
      finishes an open path;
    - Backspace removes the last node, Shift keeps 45° angles, Esc cancels.
  - **Edit nodes** now works on curves, as in MeerK40t:
    - drag nodes and their round handles; a smooth node keeps both handles
      in line, and Ctrl moves one handle alone;
    - Shift+click selects several nodes;
    - buttons with icons in the bar above the bed view, in four sections:
      Node (Add, Remove), Side (Straight, Curve), Curve through the node
      (Smooth, Symmetric), Shape (Close / open, Cut open);
    - buttons that need a selected node stay grey until you click one, and
      the status bar says what to do;
    - keys: I add, D / Delete remove, L straight, C curve, O smooth,
      S symmetric, Z close / open, B cut open;
    - double-click a side to add a node, or a node to remove it.
  - Ellipses become real curves when you edit their nodes.
  - Paths are saved in projects.
- **Editing opened SVG / DXF files.** An opened file is one element that
  behaves like a group.
  - **Ungroup** splits it into separate shapes, one per line, each with its
    real curves (SVG via svgelements; DXF arcs, circles and polyline bulges
    stay arcs).
  - The pieces stay exactly in place and keep their cut or outline layer.
  - Each piece can then be clicked and dragged on its own; double-click it
    to edit its nodes.
  - Double-clicking a file that is not ungrouped explains this.
  - When a file cannot be read with its curves (for example SVG text), its
    lines become polylines, as before.
  - The picture part (raster engraving) splits into its separate areas too,
    each a picture of its own with exactly the same pixels and greys, in the
    same place. This also works on opened pictures (PNG, JPG, ...).
  - With nothing selected, Ungroup acts on the only opened file or group.
  - Ungroup also splits a cut or outlined text into its letters.
- **Element list ↔ bed selection.** Selecting on the bed highlights the rows
  in the element list (also several elements or a whole group). Clicking a
  row selects the element on the bed; Ctrl / Shift picks several.
- **Freehand** drawing tool (F). Draw with the mouse button held; end near
  the start to close the shape. The line is simplified and smoothed into
  curves that can be edited with Edit nodes.
- **Hatch** for closed shapes on an outline layer ("Fill with lines"): the area is filled with parallel
  engraved lines instead of a raster image. You set the spacing, the angle,
  and optionally a cross-hatch. Holes (for example in letters) stay empty, and
  the lines go to the outline engrave layer.
- **Bridges** for shapes on a cut layer (options bar): a number of short uncut gaps per
  closed outline, with their width, so the part stays in the sheet.
- **Measure** tool (M). A plain click does not erase the last measurement. Drag between two points to see the distance, width,
  height and angle, on the bed and in the status bar. Points snap to corners,
  centres and lines.
- **Job simulation** (View → Simulate job, Ctrl+Shift+J, Simulate button).
  It plays the laser head's moves on the bed view in the order the job runs
  them: layers in job order, paths inside first, travel moves dashed.
  - Play / pause, a time slider, a "next layer" button, and speeds from 1×
    (real time) to 1000×. The speed is chosen automatically so the whole job
    plays in about half a minute. Raster engraving is drawn one line every
    0.2 mm, and it is the slowest part of a real job too.
  - The time comes from the layer speeds and passes.
- Toolbar reorganised so labels are not cut short:
  - rotate and mirror are small icons in a new Transform group;
  - group and ungroup joined the Shapes group.
- The bar above the bed view has a fixed height, so it no longer stretches.
- The mouse wheel zooms in and out about the point under the cursor, which
  stays in place (also during the simulation); one more step out at the limit
  centres the whole bed. It zooms in as far as you like, but not further out than the
  whole bed, so the bed cannot get lost.
- The bed view follows the window size until you zoom or pan. Fitting counts
  only the bed and the elements, and waits until the view has a size, so the
  bed no longer shrinks away or disappears.
- **Combine shapes** (new Shapes toolbar group, Edit → Combine shapes):
  union, difference (the first selected shape minus the others), intersection
  and exclusion of the closed outlines of two or more selected shapes. The
  result is one path that keeps the first shape's operation and layer.
- `start_kerfly.bat` / `start_kerfly.sh` install libraries added in an
  update. New: `svgelements`.

## 0.4.0 (2026-11-04)

- **Mirror** horizontally and vertically (toolbar group Arrange, Edit menu,
  Ctrl+Shift+H / Ctrl+Shift+V). Works for vectors and images, also when they
  are rotated.
- **Align** (new toolbar group): left, centre, right, top, middle and bottom.
  Several selected elements are aligned to each other, and a single element to
  the bed. **Distribute** spreads three or more elements evenly, horizontally
  or vertically. The outermost elements stay in place and the ones between get
  equal gaps. Elements too wide for gaps get evenly spaced centres instead.
  The status bar shows the result. Select several elements by dragging a frame
  around them or with Ctrl+click.
- **Polyline** drawing tool (Shift+L, on the tool strip on the right):
  - click the corners;
  - click the first point to close the shape, or double-click / press Enter
    to finish an open line;
  - Backspace removes the last corner, Shift keeps 45° angles, Esc cancels.

  Closed polylines can be cut, outlined or filled. Polylines are saved in
  `.kerfly` projects.
- **Snap to objects** (View → Snap to objects, Ctrl+;). It is on by default
  and works together with the grid. **Hold Alt** while drawing, dragging or
  editing nodes to snap to nothing (objects and grid) for a moment.
  - Drawing tools snap to corners, centres and side middles of other elements
    and of the bed, to the ends and middles of lines, and to any point on a
    line or curve. A purple marker with a label shows the target before you
    click.
  - A dragged element snaps with its corners, side middles or centre onto
    those points.
  - Several selected elements move together without snapping.
- **Edit nodes** tool (N, second button on the tool strip). Click a drawn
  shape to show its corners:
  - drag a corner to move it (it snaps to other elements and the grid);
  - double-click a side to add a corner;
  - double-click a corner, or select it and press Delete, to remove it.

  A dragged corner also snaps to the other corners and side middles of the
  same shape. It lines up (same height or same column) with another corner,
  and a dashed guide line shows it. Rectangles, ellipses, polygons and lines
  become polylines on the first edit. Rotation, scale and mirror are kept, and every edit can be undone.
  Text and opened files have no editable nodes.
- **Group / Ungroup** (Shapes group, Ctrl+Shift+G / Ctrl+Alt+G):
  - Clicking any member of a group selects the whole group.
  - Moving, arrow keys, rotating, mirroring, duplicating and deleting act on
    the group as one. Align and distribute treat it as a single block.
  - The element list shows "Group 1: …", and groups are saved in projects.
- A click with a slightly shaking mouse is a click, not a tiny drag (system
  drag distance), so elements no longer move by accident.
- Several selected elements (a frame drag or Ctrl+click) now move, rotate
  and mirror together, around the centre of the selection.
- Toolbar: **Settings** has its own group, together with a new **Materials**
  button (material library).

## 0.3.0 (2026-11-04)

- Elements outside the work area are drawn red. Start and Trace stay locked,
  with a warning above them, until the elements are moved back onto the bed.
- Diagnostic log (`kerfly.log` in the settings folder). It records every laser
  command, job, status message and error, and what the laser library prints.
- **Help → Save diagnostic report…** (also the **Report** button on the
  toolbar) saves the checks, settings and log in one text file to attach to
  a bug report. **Help → Open the log folder** opens the folder with the log.

## 0.2.0 (2026-11-04)

- Polish layer names shortened: Cięcie / Obrys / Grawer.
- The "+" button in Layers appends a new layer to the list. It no longer moves
  the selected element to the new layer: use the Layer choice above the bed
  view for that.
- The element list fills the Design tab, so it no longer scrolls after three
  elements.
- The window opens at 85% of the screen and remembers its size, position and
  maximized state.
- The drawing tool strip no longer touches the window edge.
- The options bar stays empty when nothing is selected. The hint text made it
  taller in narrow windows.

## 0.1.0 (2026-11-04)

First version for testing on a laser:

- PySide6 window with a ribbon toolbar, an editor with several elements on the
  bed, undo/redo, a snap grid and drawing tools (rectangle, ellipse, polygon,
  line, text).
- Layers with speed, passes and power, and a material library with import and
  export.
- Project files (`.kerfly`), SVG without Inkscape, DXF, G-code, images and
  EGV.
- English, Polish, German, Spanish and French.
- `--self-test`, plus tests on clean Windows and Ubuntu machines (GitHub
  Actions).
- Laser output is byte-for-byte identical to K40 Whisperer 0.71.
