# Installing Kerfly

A Polish version of this guide is in [INSTALL_pl.md](INSTALL_pl.md).

Kerfly comes in two ready-made packages. Download the one for your system
from the [releases page](https://github.com/cyryllo/Kerfly/releases/latest).
Nothing else is needed.

## Windows 10 / 11: the installer

1. Download **`Kerfly-<version>-windows-setup.exe`**.
2. Plug in the laser's USB cable and switch the laser on.
3. Run the installer. Windows may say **"Windows protected your PC"**: the
   installer is not signed (a signing certificate is paid), so Windows does
   not know its publisher. Choose **More info → Run anyway**.
4. The first time, tick **"Install the USB driver for the K40 laser"**. It
   installs the libusb-win32 driver the laser needs. If Kerfly or another
   program for this laser already worked with it on this PC, the driver is
   there and you can leave it unticked. After the driver change, LaserDRW and
   CorelLaser no longer work with the laser.
5. Start Kerfly from the Start menu (or the desktop icon, if you chose one).

## Linux: the AppImage

1. Download **`Kerfly-<version>-x86_64.AppImage`**.
2. Make it executable: in the file manager choose Properties → Allow
   executing as a program, or in a terminal:

   ```bash
   chmod +x Kerfly-*.AppImage
   ```

3. Let your user reach the laser's USB port. Do this once per computer, then
   log out and back in:

   ```bash
   sudo groupadd -f lasercutter
   sudo usermod -a -G lasercutter $USER
   echo 'SUBSYSTEM=="usb", ATTRS{idVendor}=="1a86", ATTRS{idProduct}=="5512", ENV{DEVTYPE}=="usb_device", MODE="0664", GROUP="lasercutter"' | sudo tee /etc/udev/rules.d/97-ctc-lasercutter.rules
   ```

   The `dialout` group is not enough: the laser's board is not a serial
   port.
4. Run the AppImage (double-click it, or `./Kerfly-*.AppImage`).

## Self-test

Before the first job, check the installation. Plug in and switch on the laser,
then run in a command window (Windows) or a terminal (Linux):

- Windows: `"C:\Program Files\Kerfly\kerfly-console.exe" --self-test`
- Linux: `./Kerfly-<version>-x86_64.AppImage --self-test`

Kerfly prints one line per check: libraries, USB driver, whether the laser is
found (it is not moved), Inkscape, the settings folder, and that the window
opens a design. `FAIL` lines must be fixed; `WARN` lines are optional parts or
mean that the laser is not connected.

## First run with a laser

Keep a hand on the laser's power switch.

1. **Settings → Machine**: set your board, bed size and units.
2. **Laser** tab → **Connect** (plug icon). The head homes to the upper-left
   corner.
3. Jog the head with the arrows and check the directions.
4. Draw a 20 × 20 mm rectangle and run **Trace boundary** with the laser off.
5. Cut a small test at low power on scrap material. Try **Pause** (the second
   click resumes) and **Stop**.

The [user guide](https://cyryllo.github.io/Kerfly/guide.html) explains the
rest.

## When something goes wrong

- **"USB error … libUSB driver not installed"**: on Windows run the installer
  again and tick the USB driver; on Linux add the rule from step 3 and log in
  again.
- **SVG text is missing or not cut**: install [Inkscape](https://inkscape.org/release/)
  (optional). Kerfly opens SVG files by itself, but it needs Inkscape to turn
  SVG text into lines. When Inkscape is installed, Kerfly finds it; otherwise
  set its path in Settings → Advanced.

To report a problem, choose **Help → Report a problem on GitHub…** (or the
**Bug report** button). Kerfly saves a diagnostic report and opens the report
form on GitHub with the version, system and board filled in. Drag the report
file into the form's "Diagnostic report" field. A free GitHub account is
needed to send it. You can write in English or Polish.

---

Running Kerfly from source, building the packages and running the tests:
[DEVELOPMENT.md](DEVELOPMENT.md).
