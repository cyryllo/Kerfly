# Kerfly changelog

Version numbers:

- the **second number** goes up with every release (by 10 when a new module
  is added);
- the **third number** goes up for releases that only fix bugs;
- **1.0.0** will be the first release declared stable.

## Unreleased

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
- **Text on a path.** Select a text and a shape (line, curve, circle, ...)
  and choose **Edit → Put text on path** (toolbar Shapes). Every letter
  stands on the line, turned along it, with the font's kerning; centred on
  open lines, at the top of closed shapes. The options bar moves the text
  along the path, puts it on the other side, or makes it straight again.
  Editing the text keeps it on the path, also after moving it; saved in
  projects.
- **Order of elements**: Bring forward / Send backward (toolbar group
  **Order**, PgUp / PgDown in the bed view) and Bring to front / Send to back
  (Ctrl+PgUp / Ctrl+PgDown, Edit menu). Groups move together.

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
