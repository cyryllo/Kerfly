# Kerfly changelog

Version numbers:

- the **second number** goes up with every release (by 10 when a new module
  is added);
- the **third number** goes up for releases that only fix bugs;
- **1.0.0** will be the first release declared stable.

## Unreleased

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
