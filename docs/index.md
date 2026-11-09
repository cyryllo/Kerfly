---
layout: default
lang: en
other_lang: pl/
wide: true
description: Kerfly is free laser control software for K40 CO2 lasers with Lihuiyu M2 Nano boards. Draw, place and cut on Windows, Linux and macOS.
---
{% assign img = '/img/en/' | relative_url %}

<div class="hero">
  <img src="{{ '/assets/logo.svg' | relative_url }}" alt="Kerfly logo">
  <div>
    <h1>Kerfly</h1>
    <p>Free laser control software for K40 lasers. Draw, lay out and cut in one window.</p>
    <p class="badges"><span>Windows</span><span>Linux</span><span>macOS</span><span>Free &amp; open source</span><span>5 languages</span></p>
  </div>
</div>

<div class="buttons">
  <a class="button primary" href="#download">Download</a>
  <a class="button" href="{{ '/guide.html' | relative_url }}">User guide</a>
  <a class="button" href="{{ site.repo }}/blob/main/INSTALL.md">Installation</a>
</div>

<div class="shot"><a href="{{ '/screenshot.png' | relative_url }}"><img src="{{ '/screenshot.png' | relative_url }}" alt="Kerfly main window with a drawing on the laser bed"></a></div>

<p class="lead">Kerfly runs K40-class CO2 lasers with <strong>Lihuiyu boards</strong> (M2 Nano family: M1, M2, M3, B1, …), the blue-and-white desktop lasers sold under many names. Everything from the first sketch to the cut part happens in one modern window: draw, open your files, arrange them on the bed, set the layers, check the job and send it.</p>

<div class="stats">
  <div><strong>10</strong><span>generators: boxes, tests, stamps, QR, …</span></div>
  <div><strong>8</strong><span>engraved fill patterns</span></div>
  <div><strong>3</strong><span>living hinge patterns</span></div>
  <div><strong>3</strong><span>layer kinds: raster, outline, cut</span></div>
  <div><strong>1:1</strong><span>laser data checked byte by byte</span></div>
</div>

## What Kerfly can do

<div class="showcase">
  <div class="shot-col"><a href="{{ img }}site-nodes.png"><img loading="lazy" src="{{ img }}site-nodes.png" alt="Editing the nodes of a heart shape, with curve handles"></a></div>
  <div class="text-col">
    <h3>Draw and edit like in a vector program</h3>
    <ul>
      <li>Rectangle (also rounded), ellipse, polygon, line, polyline, pen curves, freehand and text in any installed font.</li>
      <li>Edit the nodes of every shape and of opened SVG and DXF files: drag nodes and curve handles, add, remove, smooth, cut open.</li>
      <li>Snapping to corners, centres and edges of other shapes, and to a grid; hold Alt to place freely.</li>
      <li>Union, difference, intersection and exclusion of shapes.</li>
    </ul>
  </div>
</div>

<div class="showcase reverse">
  <div class="shot-col small"><a href="{{ img }}design.png"><img loading="lazy" src="{{ img }}design.png" alt="The element list with order buttons"></a></div>
  <div class="text-col">
    <h3>Lay out the whole bed</h3>
    <ul>
      <li>Put several files and drawings on a picture of the laser bed; drag, scale and rotate them with handles or type exact numbers.</li>
      <li>Align, distribute, mirror, group, duplicate; undo and redo everything.</li>
      <li>The element list is the order of the job: move parts up or down with the arrows beside it. Holes are always cut before their outline.</li>
      <li>Projects keep the layout, the layers and copies of your files in one <code>.kerfly</code> file.</li>
    </ul>
  </div>
</div>

<div class="showcase">
  <div class="shot-col small"><a href="{{ img }}layers.png"><img loading="lazy" src="{{ img }}layers.png" alt="Layers panel with speed, passes and time of each layer"></a></div>
  <div class="text-col">
    <h3>Layers, like LightBurn</h3>
    <ul>
      <li>Raster engraving, outline engraving and cutting, each layer with its own speed, passes, colour and, on M3 boards, power.</li>
      <li>Add more layers of a kind (for example a slow and a fast cut) and choose the layer of every shape.</li>
      <li>A material library ("Plywood 3 mm") sets all layers at once; export and import it.</li>
      <li>The time of every layer and of the whole job, before you start.</li>
    </ul>
  </div>
</div>

<div class="showcase reverse">
  <div class="shot-col"><a href="{{ img }}site-fill.png"><img loading="lazy" src="{{ img }}site-fill.png" alt="Shapes filled with honeycomb, waves, bricks, circles and diamonds"></a></div>
  <div class="text-col">
    <h3>Pattern fills</h3>
    <p>Fill any closed shape with engraved lines in a pattern while its outline is still cut: lines, cross-hatch, waves, zigzag, circles, honeycomb, diamonds and bricks. Choose the size, angle and the free margin; pick the bucket tool and click the shapes.</p>
    <p>A coaster with a cut edge and an engraved honeycomb inside is two clicks.</p>
  </div>
</div>

<div class="showcase">
  <div class="shot-col"><a href="{{ img }}site-hinge.png"><img loading="lazy" src="{{ img }}site-hinge.png" alt="Living hinges with straight, wavy and zigzag cuts"></a></div>
  <div class="text-col">
    <h3>Living hinges</h3>
    <p>Rows of cuts that let plywood bend: straight, wavy or zigzag. Set the cut length, the bridges between them, the row spacing and the direction, or put the hinge in a band only where the part should bend.</p>
  </div>
</div>

<div class="showcase reverse">
  <div class="shot-col"><a href="{{ img }}site-textpath.png"><img loading="lazy" src="{{ img }}site-textpath.png" alt="Text running around a circle and along a curve"></a></div>
  <div class="text-col">
    <h3>Text on a path</h3>
    <p>Put a text along a line, a curve or around a circle, slide it along with the mouse, change the letter spacing, the distance from the line and the side. Great for coasters, signs and seals.</p>
  </div>
</div>

<div class="showcase">
  <div class="shot-col"><a href="{{ img }}site-generators.png"><img loading="lazy" src="{{ img }}site-generators.png" alt="A material test, a finger-joint box, a gear and a stamp made by the generators"></a></div>
  <div class="text-col">
    <h3>Generators: ready designs from a few numbers</h3>
    <ul>
      <li><strong>Material test</strong>: a grid of fields, each with its own speed and power or passes, on its own layer, with the values engraved.</li>
      <li><strong>Finger-joint box</strong> with or without a lid, inside or outside sizes, kerf compensation.</li>
      <li><strong>Kerf test</strong>: measure how wide your laser cuts and find the tightest fit.</li>
      <li><strong>Gear</strong> with involute teeth, <strong>puzzle</strong>, <strong>ruler</strong>, <strong>QR code</strong> and a <strong>test card</strong> for the laser.</li>
      <li><strong>Exact sizes</strong>: type your laser's kerf into a cut layer and the parts come out at their drawn size; <strong>Offset</strong> draws an outline around a shape or inside it.</li>
    </ul>
  </div>
</div>

<div class="showcase reverse">
  <div class="shot-col"><a href="{{ img }}stamp.png"><img loading="lazy" src="{{ img }}stamp.png" alt="The stamp generator: text, logo and frame, inverted and mirrored"></a></div>
  <div class="text-col">
    <h3>Rubber stamps in one click</h3>
    <p>Pick a usual stamp size (or your own), type the lines, choose a font, a logo and a frame, and press <strong>Generate stamp</strong>. Kerfly burns the background away so the text stays raised, mirrors the stamp so it prints the right way round, and adds the cut line around it. <strong>Round stamps</strong> too: text around the top and the bottom, rings, and text or a logo in the middle.</p>
  </div>
</div>

<div class="showcase">
  <div class="shot-col"><a href="{{ img }}site-simulation.png"><img loading="lazy" src="{{ img }}site-simulation.png" alt="Job simulation playing on the bed, half way through"></a></div>
  <div class="text-col">
    <h3>See the job before the laser does</h3>
    <ul>
      <li><strong>Simulation</strong> plays the whole job on the bed: the order of the cuts, the moves with the laser off, the raster, the time.</li>
      <li><strong>Trace boundary</strong> drives the head around the design (as a rectangle from the nearest corner) so you can check where it will cut.</li>
      <li>Save the job as an EGV file, or send one you have.</li>
    </ul>
  </div>
</div>

<div class="showcase reverse">
  <div class="shot-col"><a href="{{ img }}site-safety.png"><img loading="lazy" src="{{ img }}site-safety.png" alt="A shape outside the bed drawn red, with Start locked"></a></div>
  <div class="text-col">
    <h3>Made to keep your laser safe</h3>
    <ul>
      <li>A shape sticking out of the work area turns red and Start is locked, so the head never runs into the frame.</li>
      <li>Kerfly checks that the head stays on the bed for the whole job before anything is sent.</li>
      <li>Pause and resume with the same button; Stop ends the job at once and asks for Home before the next one.</li>
    </ul>
  </div>
</div>

<div class="showcase">
  <div class="shot-col small"><a href="{{ img }}laser.png"><img loading="lazy" src="{{ img }}laser.png" alt="Laser tab with connect, home, jog arrows and corner buttons"></a></div>
  <div class="text-col">
    <h3>Full control of the machine</h3>
    <ul>
      <li>Connect, home, unlock the rail, jog the head with buttons or Ctrl+arrows, move it to the corners or the centre of the design, or to any X/Y.</li>
      <li>Keep the design where it is on the bed, or let it <strong>follow the head</strong>: your way of working.</li>
      <li>Test fire and power per operation on M3 boards.</li>
    </ul>
  </div>
</div>

## Opens your files

SVG (with or without Inkscape), DXF, G-code, and pictures for raster engraving: PNG, JPG, BMP, TIFF, GIF, WebP. Opened SVG and DXF files can be split into separate shapes and edited node by node.

## Tested like a release should be

Kerfly drives a real machine with a laser, so "it seems to work" is not enough:

<div class="features">
  <div class="feature"><h3>Byte-exact laser data</h3><p>After every change the data sent to the laser is compared byte by byte with the proven original.</p></div>
  <div class="feature"><h3>Clicked through like a user</h3><p>Before every release a test clicks through the whole program in over 270 steps on a Full HD screen and checks after each step that the window shows what Kerfly will really do.</p></div>
  <div class="feature"><h3>Thousands of random sessions</h3><p>Random clicking hunts for the mistakes no person would think of; each one can be repeated exactly.</p></div>
  <div class="feature"><h3>Three systems</h3><p>Every change is tested on clean Windows, Linux and macOS machines, and the packages check themselves before they are published.</p></div>
</div>

<h2 id="download">Download</h2>

<p>Free, no account, no Python needed. The <a href="{{ site.repo }}/releases/latest">latest release</a> has a package for each system:</p>

<div class="platforms">
  <div class="platform">
    <h3>Windows 10 / 11</h3>
    <p><code>Kerfly-…-windows-setup.exe</code></p>
    <p>Run the installer; the first time tick <em>Install the USB driver for the K40 laser</em>. It is not signed, so Windows may say it protected your PC: choose <em>More info → Run anyway</em>.</p>
  </div>
  <div class="platform">
    <h3>Linux</h3>
    <p><code>Kerfly-…-x86_64.AppImage</code></p>
    <p>Make it executable and run it. Allow the laser's USB port once with <em>Laser → Allow USB access for the laser…</em> (asks for your password).</p>
  </div>
  <div class="platform">
    <h3>macOS 11+ <span class="tag">preview</span></h3>
    <p><code>…-macos-arm64.dmg</code> / <code>…-macos-x86_64.dmg</code></p>
    <p>Apple Silicon or Intel. Drag Kerfly to Applications; the first start needs <em>Open Anyway</em> (<a href="{{ site.repo }}/blob/main/INSTALL.md#macos">how</a>). Not yet tested with a laser: tell us how it works.</p>
  </div>
</div>

<div class="buttons">
  <a class="button primary" href="{{ site.repo }}/releases/latest">Go to the latest release</a>
  <a class="button" href="{{ site.repo }}/blob/main/INSTALL.md">Step-by-step installation</a>
</div>

## Questions

<div class="faq">
<details><summary>Which lasers does Kerfly work with?</summary><p>K40-class CO2 lasers with Lihuiyu controller boards of the M2 Nano family (M1, M2, M3, B1 and others): the board name is printed on it, for example LASER-M2. Other controllers (Ruida, GRBL) are not supported; GRBL lasers are planned.</p></details>
<details><summary>Is it really free?</summary><p>Yes: free software under the GPL-3.0 licence, no account, no ads, no limits. The source code is on <a href="{{ site.repo }}">GitHub</a>.</p></details>
<details><summary>Do I need Inkscape or other programs?</summary><p>No. Kerfly opens SVG files by itself. Inkscape is optional and only needed for SVG text that should be cut or engraved as lines.</p></details>
<details><summary>Do I need a USB driver?</summary><p>On Windows the installer installs it when you tick the box. On Linux one click in Kerfly (Laser → Allow USB access) adds the rule. macOS needs nothing.</p></details>
<details><summary>Is Kerfly in my language?</summary><p>English, Polish, German, Spanish and French; it follows the language of your system, and you can change it in Settings → Advanced.</p></details>
<details><summary>Something does not work. What do I do?</summary><p>Choose Help → Report a problem in Kerfly: it saves a diagnostic report and opens the <a href="{{ site.repo }}/issues/new/choose">report form</a>. You can write in English or Polish.</p></details>
</div>

## Status

**Kerfly 1.1 is stable and ready for everyday work** with your laser.
Planned next: image tracing, more patterns, more file
formats, and a Debian package with its own APT repository. See the
[roadmap]({{ site.repo }}/blob/main/ROADMAP.md) and the
[changes]({{ site.repo }}/blob/main/CHANGELOG.md).

## Help and feedback

Found a problem? In Kerfly choose **Help → Report a problem on GitHub…**: it
saves a diagnostic report and opens the [report form]({{ site.repo }}/issues/new/choose).
Ideas and translation fixes are welcome too, in English or Polish.
