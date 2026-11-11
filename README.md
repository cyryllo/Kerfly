# <img src="kerfly/gui/icons/kerfly.svg" width="48" alt="" align="center"> Kerfly

[![tests](https://github.com/cyryllo/Kerfly/actions/workflows/tests.yml/badge.svg)](https://github.com/cyryllo/Kerfly/actions/workflows/tests.yml)

**Website and user guide:** [cyryllo.github.io/Kerfly](https://cyryllo.github.io/Kerfly/) · **Download:** [latest release](https://github.com/cyryllo/Kerfly/releases/latest) · **Po polsku:** [README_pl.md](README_pl.md)

Kerfly is free laser control software for K40-class CO2 lasers with Lihuiyu
(M2 Nano family) controller boards. It runs on Windows 10 / 11, Linux and macOS.

![Kerfly main window](docs/screenshot.png)

## Installing

Download the package for your system from the
[latest release](https://github.com/cyryllo/Kerfly/releases/latest):

- **Windows 10 / 11:** run `Kerfly-<version>-windows-setup.exe`. The
  installer is not signed, so Windows may say "Windows protected your PC":
  choose **More info → Run anyway**. The first time, tick the USB driver for
  the K40 laser.
- **Linux:** make `Kerfly-<version>-x86_64.AppImage` executable and run it.
  Allow the laser's USB port once: **Laser → Allow USB access for the
  laser…** (asks for your password; see [INSTALL.md](INSTALL.md#linux-the-appimage)).
- **macOS 11 or newer** (preview, not yet tested with a laser): open
  `Kerfly-<version>-macos-arm64.dmg` (Apple Silicon) or `-macos-x86_64.dmg`
  (Intel) and drag Kerfly to Applications. It is not signed by Apple; how to
  open it the first time: [INSTALL.md](INSTALL.md#macos).

Step by step, with the self-test and the first run on the laser:
[INSTALL.md](INSTALL.md) ([po polsku](INSTALL_pl.md)). How to use Kerfly:
the [user guide](https://cyryllo.github.io/Kerfly/guide.html).

## What it does

- **Lay out the bed.** Put several files on a picture of the laser bed,
  drag, scale and rotate them with the mouse or type their position, size
  and angle. Align, group, combine and offset shapes, choose the order of
  the job, undo and redo everything.
- **Draw and edit.** Rectangle (with rounded corners), ellipse, polygon,
  line, polyline, pen curves, freehand and text in any installed font, also
  along a line, curve or circle. Edit the nodes of drawn shapes and of opened
  SVG and DXF files.
- **Patterns and hinges.** The **Fill** tool fills closed shapes with
  engraved patterns (lines, waves, honeycomb, concentric, ...) while their
  outline is still cut. The **Living hinge** tool cuts hinges that let
  plywood bend.
- **Generators.** Ready designs from a few numbers: material test, finger-joint
  box, kerf test, gear, puzzle, ruler, QR code, rubber stamps, rectangular
  and round (inverted and mirrored), and a test card for the laser.
- **Layers, like LightBurn.** Raster engrave, outline engrave and cut, each
  with its own speed, passes and power (M3 boards) and colour; cut layers
  compensate the kerf, so parts come out at their drawn size. A material
  library (for example "Plywood 3 mm") sets all layers at once.
- **Files.** SVG, DXF, G-code, and pictures (PNG, JPG, BMP, TIFF, GIF, WebP)
  for raster engraving. A project (`.kerfly`) keeps the layout, layers,
  shapes and copies of the source files in one file.
- **Run the laser.** Connect, home, jog, trace the outline, simulate and
  time the job, pause and resume, stop. The design stays where it is on the
  bed and the head drives to it, or the design follows the head: your
  choice. Kerfly refuses jobs that would run the head off the bed.
- **Your language.** English, Polish, German, Spanish and French (Settings →
  Advanced → Language).

**Kerfly 1.2 is stable and ready for everyday work.** Changes are in [CHANGELOG.md](CHANGELOG.md), plans in
[ROADMAP.md](ROADMAP.md).

## Drawing and editing: mouse and keys

| Action | How |
|---|---|
| Select several elements | Drag a frame around them, or Ctrl+click |
| Move | Drag, or the arrow keys (1 mm or one grid step; Shift: 10×) |
| Snapping | Snaps to corners, centres, middles and lines of other elements, to the bed and to the grid (View → Snap to objects, Ctrl+;) |
| Snap nothing for a moment | **Hold Alt** while drawing, dragging or moving a node |
| Square / circle, 45° lines | Hold Shift while drawing |
| Polyline | Click the corners. Click the first point to close; double-click or Enter for an open line; Backspace removes the last corner; Esc cancels |
| Pen (B) | Click for a corner, press and drag for a smooth curve. Click the first point to close; double-click or Enter to finish; Backspace removes the last node |
| Freehand (F) | Draw with the button held; end near the start to close |
| Measure (M) | Drag between two points: distance, width, height, angle |
| Edit nodes (N) | Drag nodes and round curve handles (Ctrl: one handle alone). Shift+click selects more. Double-click a side to add a node, a node to remove it. Keys: I insert, D delete, L line, C curve, O smooth, S symmetric, Z close / open, B break |
| Edit an opened SVG / DXF | Ungroup it: every line becomes its own shape and the picture splits into its separate parts; click to move, double-click to edit nodes |
| Edit nodes of any element | Double-click it |
| Group / Ungroup | Ctrl+Shift+G / Ctrl+Alt+G. Clicking one member selects the whole group |
| Element list | Shows what is selected on the bed; click a row (Ctrl / Shift: several) to select on the bed |
| Zoom | The wheel zooms in; it does not zoom out further than the whole bed |
| Pan and zoom | Middle or right mouse button drags the view; the wheel zooms |

On KDE Plasma 5, Alt+drag moves windows by default. Change it in System
Settings → Window Management → Window Behavior → Window Actions, or use Plasma
6, where Meta moves windows.

## Reporting problems

In Kerfly choose **Help → Report a problem on GitHub…** (or the **Bug report**
button). Kerfly saves a diagnostic report (settings, self-test and the log of
what was sent to the laser) and opens the
[report form](https://github.com/cyryllo/Kerfly/issues/new/choose) with the
version, system and board filled in; drag the report file into the form.
There are forms for laser problems (wrong place, power or speed), other bugs,
feature ideas and translation fixes. You can write in English or Polish.

## Supporting the project

Kerfly is free and stays free. You can help it grow:

- **Use it and report what does not work**, or what you miss (see above).
  Every report becomes a test, so the same problem does not come back.
- **Tell others about it**: on groups and forums, and to whoever sold you
  your laser.
- **Test it with your machine and board**, especially boards that are not
  confirmed yet (M3 Plus and others) and macOS.
- **Improve a translation**, or add a new language.
- **Laser makers, sellers and shops: I am open to cooperation**: testing
  Kerfly with your machines and new boards, ready material settings for them,
  mentioning Kerfly to your customers, or your own idea. Contact me through my
  GitHub profile, [@cyryllo](https://github.com/cyryllo).

## License

Kerfly is free software, distributed under the **GNU General Public License,
version 3 or later** (GPL-3.0-or-later). See [LICENSE](LICENSE).

- Copyright (C) 2017–2026 Scorch: the original K40 Whisperer.
- Copyright (C) 2026 Kerfly contributors: changes made in this fork.

Some files come from other projects and keep their own notices.
[THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md) lists each file, its author
and its license.

This program controls a laser. It is provided WITHOUT ANY WARRANTY (see
sections 15–16 of the GPL). Never leave a running laser unattended.

---

Kerfly is an independent fork of [K40 Whisperer](https://www.scorchworks.com/K40whisperer/k40whisperer.html)
by Scorch, who wrote its laser control core. It is not affiliated with or
endorsed by Scorch; please report Kerfly problems here.
For developers (running from source, tests, translations, packages):
[DEVELOPMENT.md](DEVELOPMENT.md).
