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
  <a class="button primary" href="{{ site.repo }}/releases/latest">Download (Windows, Linux)</a>
  <a class="button" href="{{ '/guide.html' | relative_url }}">User guide</a>
  <a class="button" href="{{ site.repo }}/blob/main/INSTALL.md">Installation</a>
</div>

<div class="shot"><img src="{{ '/screenshot.png' | relative_url }}" alt="Kerfly main window with a drawing on the laser bed"></div>

Kerfly runs K40-class CO2 lasers with **Lihuiyu boards** (M2 Nano family:
M1, M2, M3, B1, ...): the blue-and-white desktop lasers sold under many
names. Draw, lay out and run your jobs in one window, from the first sketch
to the cut part.

## What it can do

<div class="features">
  <div class="feature"><h3>Lay out the bed</h3><p>Put several files on the laser bed, move, scale and rotate them with the mouse or by typing, align, group and stack them in order. Undo and redo everything.</p></div>
  <div class="feature"><h3>Draw and edit</h3><p>Rectangles, ellipses, polygons, lines, curves, freehand and text in any installed font, also along a curve or a circle. Edit the nodes of drawn shapes and of opened SVG and DXF files.</p></div>
  <div class="feature"><h3>Layers like LightBurn</h3><p>Raster engraving, outline engraving and cutting, each with its own speed, passes and power. A material library sets them all at once.</p></div>
  <div class="feature"><h3>Many file types</h3><p>SVG (with or without Inkscape), DXF, G-code, and pictures: PNG, JPG, BMP, TIFF, GIF, WebP. Projects keep everything in one file.</p></div>
  <div class="feature"><h3>Patterns, hinges, bridges</h3><p>Fill shapes with engraved patterns (waves, honeycomb, bricks, ...) while their outline is still cut, cut living hinges that let plywood bend, leave bridges that hold cut parts in the sheet, combine shapes.</p></div>
  <div class="feature"><h3>Generators</h3><p>Ready designs from a few numbers: material test, finger-joint box, kerf test, gear, puzzle, ruler, QR code, rubber stamp and a test card for the laser.</p></div>
  <div class="feature"><h3>Safe to run</h3><p>Trace the outline first, simulate the job, see the time. Kerfly refuses jobs that would run the head off the bed.</p></div>
  <div class="feature"><h3>Your way of working</h3><p>Keep the design in place on the bed and let the head drive to it, or let the design follow the head: your choice.</p></div>
  <div class="feature"><h3>Your language</h3><p>English, Polish, German, Spanish and French. Runs on Windows 10 / 11 (installer) and Linux (AppImage, most distributions).</p></div>
</div>

## Getting started

Open the <a href="{{ site.repo }}/releases/latest">latest release</a> and download the package for your system. No Python needed.

<ol class="steps">
  <li><strong>Windows 10 / 11:</strong> run <code>Kerfly-&lt;version&gt;-windows-setup.exe</code>. The installer is not signed, so Windows may say <em>Windows protected your PC</em>: choose <em>More info → Run anyway</em>. The first time, tick <em>Install the USB driver for the K40 laser</em>. Kerfly is then in the Start menu.</li>
  <li><strong>Linux:</strong> make <code>Kerfly-&lt;version&gt;-x86_64.AppImage</code> executable and run it. Allow the <a href="{{ site.repo }}/blob/main/INSTALL.md#linux-the-appimage">laser's USB port</a> once: <em>Laser → Allow USB access for the laser…</em> (asks for your password).</li>
  <li>Read the <a href="{{ '/guide.html' | relative_url }}">user guide</a>: connect the laser, place a design, trace, start.</li>
</ol>

The <a href="{{ site.repo }}/blob/main/INSTALL.md">installation guide</a> explains each step.

## Status

**Kerfly 1.0 is stable and ready for everyday work** with your laser.
Planned next: image tracing, kerf compensation, more patterns, more file
formats, and a Debian package with its own APT repository. See the
[roadmap]({{ site.repo }}/blob/main/ROADMAP.md) and the
[changes]({{ site.repo }}/blob/main/CHANGELOG.md).

## Help and feedback

Found a problem? In Kerfly choose **Help → Report a problem on GitHub…**: it
saves a diagnostic report and opens the [report form]({{ site.repo }}/issues/new/choose).
Ideas and translation fixes are welcome too, in English or Polish.
