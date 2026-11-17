# Kerfly for developers

This page is for people who want to run Kerfly from source, change it,
translate it or build the packages. To install and use Kerfly, see
[INSTALL.md](INSTALL.md) and the [user guide](https://cyryllo.github.io/Kerfly/guide.html).

## Running from source

### Linux (Debian / Ubuntu)

```bash
sudo apt install python3-venv inkscape
git clone https://github.com/cyryllo/Kerfly && cd Kerfly
./start_kerfly.sh
```

`start_kerfly.sh` makes a virtual environment (`.venv`) and installs the
libraries the first time. By hand:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt -r requirements-optional.txt
.venv/bin/python kerfly.py
```

For the laser's USB port add the udev rule from [INSTALL.md](INSTALL.md)
(step 3 of the Linux part).

### Windows 10 / 11

1. Install **Python 3.13** (64-bit) from <https://www.python.org/downloads/windows/>
   and tick **"Add python.exe to PATH"**. 3.13 is recommended because every
   library has ready-made wheels for it.
2. Get the source (`git clone` or the source archive of a release) and
   double-click **`start_kerfly.bat`**. The first start installs the
   libraries; it needs internet and takes a few minutes.
3. The laser needs the **libusb-win32** driver. Install Kerfly once with the
   installer and tick the driver, or use [Zadig](https://zadig.akeo.ie/):
   Options → List All Devices, choose **USB-EPP/I2C… CH341A** (ID `1A86 5512`),
   choose **libusb-win32**, **Replace Driver**.

Inkscape is optional. It is used for SVG rasters when it is installed, and it
is needed for SVG text that is cut or engraved as an outline.

Self-test from source: `start_kerfly.bat --self-test` (Windows) or
`./start_kerfly.sh --self-test` (Linux).

## Tests

```bash
.venv/bin/python tests/test_core.py          # core only, no display needed
QT_QPA_PLATFORM=offscreen .venv/bin/python tests/test_gui.py   # the window, offscreen
.venv/bin/python tests/test_stamp.py         # the stamp picture clean (CI: also on the Windows platform)
.venv/bin/python tests/test_i18n.py          # translations complete and up to date
sudo apt install xvfb
xvfb-run -a .venv/bin/python tests/regression.py   # full application
.venv/bin/python kerfly.py --self-test
```

`tests/regression.py` has 25 cases: vector cut, vector engrave, raster, trace
and G-code jobs, M1/M2/M3/B1 boards, rotate, mirror, home in upper right and
multiple passes. Each case compares the exact bytes the laser would receive
with a baseline made by the original laser core (tag `upstream-0.71`). M3
power mode is captured through a fake USB device. SVG-based baselines depend
on the Inkscape version (currently 1.4); without Inkscape those cases are
skipped. Kerfly-only behaviour goes through settings whose defaults keep the
original output, so these baselines stay byte-identical.

GitHub Actions runs every push on clean Windows and Ubuntu machines: it
installs Kerfly with `start_kerfly.bat` / `start_kerfly.sh`, runs the
self-test and all the test suites above.

## Release tests

Before a stable release, run the release test on a Full HD screen:

```bash
QT_QPA_PLATFORM=xcb xvfb-run -a -s "-screen 0 1920x1080x24" .venv/bin/python tests/test_release.py
```

It works through a whole session in the real window with real mouse clicks
and key presses (tools, every options bar field for every shape, every menu
and toolbar command, the panels, a stand-in laser). After every step
`kerfly/gui/truth.py` checks that the window shows what its data holds
(options bar, position fields, element list, Layer lists, layers panel, bed
view, job), and every change is undone and redone. Dialogs are answered by
clicking their buttons; file and colour pickers and the browser are
replaced. The test fails when a command, an options bar field or a panel
control was never used: **a new function needs its steps in
`tests/test_release.py`**. In the options bar, every field must say which
setting it shows (`widget.setProperty("spec_attr", name)`), so the checks
cover it.

More release tests:

```bash
# random sessions: many random steps with real input, after each the same checks;
# a failure prints the seed and the steps, to repeat it exactly
QT_QPA_PLATFORM=xcb xvfb-run -a -s "-screen 0 1920x1080x24" .venv/bin/python tests/test_random.py --seed 1 --runs 3 --steps 300
# reference results of the sample projects (tests/fixtures/release, made by
# tools/make_release_samples.py): exact laser data, cut order and lengths, bed pictures
.venv/bin/python tests/test_references.py              # --update after a deliberate change
.venv/bin/python tests/test_references.py --screenshots /tmp/shots   # Full HD pictures to look at
# the built program checks itself (fonts, Qt plugins, libraries) with a short session
Kerfly --release-test                                  # Windows: kerfly-console.exe --release-test
```

Without X11 (Windows) the release test runs on a Full HD screen of Qt's
offscreen platform: `QT_QPA_PLATFORM=offscreen:configfile=tests/fullhd.json`.

The release session and the random sessions run on the developer's
computer **before every version tag** (they need a few minutes and a
screen). GitHub Actions runs the quick ones on every push (core, GUI,
translations, laser data, references, `--release-test`), and the built
installer and AppImage run `--release-test` before they are released.

All of them in one go, before a tag: `tools/run_release_checks.sh` (about
20 minutes; prints one short block per suite).

## Laser test card

Before a feature release (1.x.0) the test card is cut on the machine; a
fix-only release (1.x.y) needs only the automatic tests. Insert it with
**Generators → Test card** in the built program (the same design is saved in
`tests/fixtures/release_card.kerfly` by `tools/make_release_samples.py`), put a piece of 3 mm plywood of about 160 x 100 mm on
the bed, Trace boundary, then Start. Write down the board, material, speed
and power. Then check:

1. **Size:** the square is 50.0 mm on each side (± 0.2 mm), its hole is
   20.0 mm and in the middle.
2. **Order:** the hole was cut before the square (the square did not move
   while its hole was cut); outlines and the raster ran before the cuts.
3. **Ruler:** 100 mm long, a mark every 10 mm (check it with a ruler).
4. **Raster:** the black block and the word "Kerfly" are where the preview
   shows them, not shifted against the cut and engraved lines.
5. **Patterns:** lines, honeycomb, waves and circles stay inside their
   squares, with the small free border.
6. **Hinge:** the cut strip bends without breaking; no cut reaches the
   outline.
7. **Text on a path:** "KERFLY TEST" follows the top of the circle.
8. **Bridges:** the small rectangle stays held in the sheet by two bridges
   and breaks out by hand.
9. **Turned pentagon** and the **open line**: engraved / cut where the
   preview shows them; the line starts at its end nearer the head.
10. **Time:** the job took about as long as the estimate.

Report anything else with **Help → Report a problem** and a photo.

## Screenshots

After a change to the window, refresh the screenshots of the README and the
user guide:

```bash
xvfb-run -a -s "-screen 0 1920x1200x24" .venv/bin/python tools/make_screenshots.py
```

## The window's look

The look follows the mockups in `docs/ui-mockups/` (Design canvas files: the
main window, the options bar, the Laser tab, every dialog).

- `kerfly/gui/theme.py` holds every size (icons 16/20/24, spacing 4/8/12,
  heights 28/32/36/44, rounding), the colours of the light and the dark theme
  and the colours drawn on the bed (`CANVAS`). No other file names a colour
  or a size of its own.
- `kerfly/gui/widgets.py` has the building blocks: a caption or a field with
  its icon, an icon button, hints, a beta badge, and the dialog pattern:
  `DialogBody`, `Section` (a title, rows of an icon caption and a field),
  `PreviewBar`, `Segmented`, `DialogFooter` (Cancel first, then the action
  named for what it does, never OK) and `ask()` for questions with named
  buttons.
- Every field has an icon and a tooltip; a new or moved control gets its steps
  in `tests/test_release.py`.

## Translations

Kerfly is in English, Polish, German, Spanish and French. The German, Spanish
and French translations have not yet been reviewed by native speakers.
Corrections are welcome.

1. Install the developer tools: `pip install -r requirements-dev.txt`
2. To add a language, add its code to `LANGUAGES` in `kerfly/i18n.py` and run
   `python tools/i18n.py`. This creates
   `kerfly/locale/<code>/LC_MESSAGES/kerfly.po`.
3. Translate the `.po` file, for example with [Poedit](https://poedit.net/).
4. Run `python tools/i18n.py` to compile it, then `python tests/test_i18n.py`
   to check it.

In the code, wrap every user-visible string in `_()`, or use `N_()` for
strings in tables that are translated later, then run `python tools/i18n.py`.

## Packages and releases

`.github/workflows/release.yml` builds the Windows installer (PyInstaller +
Inno Setup, `packaging/kerfly.spec`, `packaging/windows/kerfly.iss`) and the
Linux AppImage (`packaging/linux/`), runs `--self-test` on both, and on a
version tag (`vX.Y.Z`) publishes them as a GitHub release with notes from
[CHANGELOG.md](CHANGELOG.md) (`tools/release_notes.py`). To try the packages
without a release: Actions → packages → Run workflow.

**When GitHub cannot build the AppImage** (its Ubuntu runners could not reach
Ubuntu's package servers on 2026-11-11), build it on your computer:
`packaging/linux/build-appimage-docker.sh v1.3.2` builds that version from a
clean copy in an Ubuntu 22.04 container (so it runs on older systems too), runs
its `--self-test` and `--release-test`, and writes it to `dist/`. It needs
Docker. The release is created only when every package was built, so then
create it by hand on GitHub (Releases → Draft a new release, the tag, the notes
from `python tools/release_notes.py X.Y.Z`) and attach the AppImage and the
other packages from the run's artifacts (Actions → the run → Artifacts).

Every code release raises the version in `kerfly/__init__.py` and gets a
section in CHANGELOG.md and in CHANGELOG_pl.md (Polish): the release text
shows the Polish one first, then the English one (`tools/release_notes.py`). Changes to the documentation alone get no new version.

## Branches

- **`main`**: the 1.x line, always releasable. Fixes only (1.8.1, 1.8.2, …);
  every fix release is tagged here, as before.
- **`2.0`**: the next big version, with the new features of the
  [roadmap](ROADMAP.md) (GRBL lasers, nesting, join into a polyline, …).
  Its version is 2.0.0 from the start, so test builds tell themselves apart
  from the 1.x releases (the update check of a 2.0 build offers no 1.x
  release).
- A fix goes to `main` first (and is released from there), then
  `git checkout 2.0 && git merge main` brings it into 2.0 (a conflict in
  `kerfly/__init__.py` or the changelogs keeps 2.0's version and adds the
  fix's lines). When 2.0 is released, `2.0` is merged into `main` (then take
  the development-version warning off the top of README.md and README_pl.md).
- The website is built from `main` only, so it shows the new features once
  2.0 is out; tests run on both branches.
- For now 2.0 test versions are published **as GitHub pre-releases with only an
  AppImage**; on Windows (and Linux) they can also be run from the source
  archive with `start_kerfly.bat` / `start_kerfly.sh`. No Windows installer or
  macOS package yet. `tools/release_notes.py` puts a development-version
  warning at the top of their release text (a version with letters after the
  number, e.g. `2.0.0a1`). Kerfly's update check skips pre-releases, so 1.x
  users are not offered them.

## Project layout

- `kerfly/core/`: the laser core, independent of the window: SVG, DXF and
  G-code loaders, settings file, design data, raster preparation, path
  order, layers and EGV job generation. Nothing in it imports a GUI toolkit.
- `kerfly/gui/`: the PySide6 window. Start it with `kerfly.py`.
- `egv.py`, `nano_library.py`: EGV encoding and USB communication with the
  controller board, unchanged from the original core.
- `k40_whisperer.py`: the original Tkinter window, kept working on
  `kerfly.core` (needs `python3-tk`).
- `tests/`: the test suites. `tools/`: translations, screenshots, icons,
  release notes. `packaging/`: the installer and the AppImage. `docs/`: the
  website and the user guide (GitHub Pages).

Plans are in [ROADMAP.md](ROADMAP.md), changes in [CHANGELOG.md](CHANGELOG.md).

## Origin

Kerfly is a fork of K40 Whisperer 0.71 by Scorch; the original release is
tagged `upstream-0.71` in this repository. See the license section of the
[README](README.md#license).

## Code signing (SignPath, Windows)

Kerfly applied to the SignPath Foundation's free code signing for open source
(2026-11-15). The website and the READMEs carry the code signing policy and
the privacy policy (docs/privacy.md, docs/pl/privacy.md) that SignPath asks
for. `Kerfly.exe` and the installer carry the product name and version
(packaging/kerfly.spec `version_file()`, packaging/windows/kerfly.iss
`VersionInfo*`). `packaging/windows/signpath-artifact-configuration.xml` is the
artifact configuration to paste into the SignPath project. Once accepted, the
release workflow uploads the installer, submits a signing request
(`signpath/github-action-submit-signing-request`, secret `SIGNPATH_API_TOKEN`,
parameter `version`) and waits for the maintainer's manual approval.
