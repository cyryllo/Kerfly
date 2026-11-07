# Installing Kerfly

A Polish version of this guide is in [INSTALL_pl.md](INSTALL_pl.md).

Kerfly comes in ready-made packages for Windows, Linux and macOS. Download the one for your system
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

3. Run the AppImage (double-click it, or `./Kerfly-*.AppImage`).
4. Let your user reach the laser's USB port, once per computer. The easy
   way: in Kerfly choose **Laser → Allow USB access for the laser…**. The
   system asks for your password once; then unplug the laser's USB cable
   and plug it in again. (Kerfly also offers this by itself when it cannot
   connect for want of permission.)

   Or by hand in a terminal, then log out and back in:

   ```bash
   sudo groupadd -f lasercutter
   sudo usermod -a -G lasercutter $USER
   echo 'SUBSYSTEM=="usb", ATTRS{idVendor}=="1a86", ATTRS{idProduct}=="5512", ENV{DEVTYPE}=="usb_device", MODE="0664", GROUP="lasercutter"' | sudo tee /etc/udev/rules.d/97-ctc-lasercutter.rules
   ```

   The `dialout` group is not enough: the laser's board is not a serial
   port.

## macOS

*A preview: not yet tested with a laser. Please report how it works with
**Help → Report a problem**.*

1. Download **`Kerfly-<version>-macos-arm64.dmg`** for a Mac with Apple
   Silicon (M1 or later), or **`Kerfly-<version>-macos-x86_64.dmg`** for a
   Mac with an Intel processor (Apple menu → About This Mac says which). macOS 11
   or newer.
2. Open the `.dmg` and drag **Kerfly** onto **Applications**.
3. The first start: Kerfly is not signed by Apple (a paid certificate), so
   macOS says it cannot check the developer. Open **System Settings →
   Privacy & Security**, scroll down and choose **Open Anyway** next to the
   message about Kerfly (on older macOS: right-click Kerfly in Applications →
   **Open**). If macOS says the app "is damaged", run once in Terminal:

   ```bash
   xattr -dr com.apple.quarantine /Applications/Kerfly.app
   ```

4. USB needs no driver and no rule on macOS: plug the laser in and connect.

## Self-test

Before the first job, check the installation. Plug in and switch on the laser,
then run in a command window (Windows) or a terminal (Linux, macOS):

- Windows: `"C:\Program Files\Kerfly\kerfly-console.exe" --self-test`
- Linux: `./Kerfly-<version>-x86_64.AppImage --self-test`
- macOS: `/Applications/Kerfly.app/Contents/MacOS/Kerfly --self-test`

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
  again and tick the USB driver; on Linux choose **Laser → Allow USB access
  for the laser…** (step 4), then plug the laser in again.
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
