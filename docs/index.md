---
layout: default
lang: en
other_lang: pl/
description: Kerfly is free laser control software for K40 CO2 lasers with Lihuiyu M2 Nano boards. Draw, place and cut on Linux and Windows.
---

<div class="hero">
  <img src="{{ '/assets/logo.svg' | relative_url }}" alt="Kerfly logo">
  <div>
    <h1>Kerfly</h1>
    <p>Free laser control software for K40 lasers, for Linux and Windows.</p>
  </div>
</div>

<div class="buttons">
  <a class="button primary" href="{{ site.repo }}/releases/latest">Download</a>
  <a class="button" href="{{ '/guide.html' | relative_url }}">User guide</a>
  <a class="button" href="{{ site.repo }}/blob/main/INSTALL.md">Installation</a>
  <a class="button" href="{{ site.repo }}">Source code</a>
</div>

<div class="shot"><img src="{{ '/screenshot.png' | relative_url }}" alt="Kerfly main window with a drawing on the laser bed"></div>

Kerfly runs K40-class CO2 lasers with **Lihuiyu boards** (M2 Nano family:
M1, M2, M3, B1, ...): the blue-and-white desktop lasers sold under many
names. It is a fork of **[K40 Whisperer](https://www.scorchworks.com/K40whisperer/k40whisperer.html)**
by Scorch and keeps its laser control unchanged: the data sent to the laser is
checked byte for byte against K40 Whisperer after every change. Around that
core, Kerfly adds a modern window with drawing and editing tools.

## What it can do

<div class="features">
  <div class="feature"><h3>Lay out the bed</h3><p>Put several files on the laser bed, move, scale and rotate them with the mouse or by typing, align, group and stack them in order. Undo and redo everything.</p></div>
  <div class="feature"><h3>Draw and edit</h3><p>Rectangles, ellipses, polygons, lines, curves, freehand and text in any installed font, also along a curve or a circle. Edit the nodes of drawn shapes and of opened SVG and DXF files.</p></div>
  <div class="feature"><h3>Layers like LightBurn</h3><p>Raster engraving, outline engraving and cutting, each with its own speed, passes and power. A material library sets them all at once.</p></div>
  <div class="feature"><h3>Many file types</h3><p>SVG (with or without Inkscape), DXF, G-code, and pictures: PNG, JPG, BMP, TIFF, GIF, WebP. Projects keep everything in one file.</p></div>
  <div class="feature"><h3>Patterns, hinges, bridges</h3><p>Fill shapes with engraved patterns (waves, honeycomb, bricks, ...) while their outline is still cut, cut living hinges that let plywood bend, leave bridges that hold cut parts in the sheet, combine shapes.</p></div>
  <div class="feature"><h3>Safe to run</h3><p>Trace the outline first, simulate the job, see the time. Kerfly refuses jobs that would run the head off the bed.</p></div>
  <div class="feature"><h3>Like K40 Whisperer, if you want</h3><p>Uses the same settings file. Let the design follow the head, or keep it in place on the bed: your choice.</p></div>
  <div class="feature"><h3>Your language</h3><p>English, Polish, German, Spanish and French. Runs on Linux (Debian, Ubuntu) and Windows 10 / 11.</p></div>
</div>

## Getting started

<ol class="steps">
  <li><a href="{{ site.repo }}/releases/latest">Download</a> the latest version (Source code, zip) and unpack it.</li>
  <li>Windows: install Python and the USB driver; Linux: add the USB rule. The <a href="{{ site.repo }}/blob/main/INSTALL.md">installation guide</a> explains each step.</li>
  <li>Start <code>start_kerfly.bat</code> (Windows) or <code>./start_kerfly.sh</code> (Linux). The first start sets everything up.</li>
  <li>Read the <a href="{{ '/guide.html' | relative_url }}">user guide</a>: connect the laser, place a design, trace, start.</li>
</ol>

## Status

Kerfly is in **early development**. The first test on a real laser was in
November 2026 (Windows 10, M3 board): cutting kept its size, the jog, pause
and stop worked, and the problems found were fixed in version 0.15. Planned
next: image tracing, kerf compensation, more patterns, more file formats,
and installers for Windows and Linux. See the
[roadmap]({{ site.repo }}/blob/main/ROADMAP.md) and the
[changes]({{ site.repo }}/blob/main/CHANGELOG.md).

## Help and feedback

Found a problem? In Kerfly choose **Help → Report a problem on GitHub…**: it
saves a diagnostic report and opens the [report form]({{ site.repo }}/issues/new/choose).
Ideas and translation fixes are welcome too, in English or Polish.
