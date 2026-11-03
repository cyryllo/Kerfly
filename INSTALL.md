# Installing and running Kerfly

Kerfly runs from source with Python. Installers (`.exe`, AppImage) will come
later. A Polish version of this guide is in [INSTALL_pl.md](INSTALL_pl.md).

## Windows 10 / 11

1. **Python 3.13** from <https://www.python.org/downloads/windows/> (the
   "Windows installer (64-bit)" of the latest 3.13 release). It is recommended
   because every library has ready-made packages for it. In the installer,
   tick **"Add python.exe to PATH"**.
2. **Inkscape** (optional) from <https://inkscape.org/release/>. Kerfly
   reads SVG files by itself. Inkscape is needed only for SVG text that is cut
   or engraved as an outline, which Inkscape turns into paths. When it is
   installed, Kerfly also uses it for rasters, as K40 Whisperer does.
3. **USB driver** for the K40 board (M2 Nano, CH341 chip), once:
   - If K40 Whisperer already worked on this PC, the driver is installed.
   - Otherwise, use **Zadig** (<https://zadig.akeo.ie/>):
     1. Choose **Options → List All Devices**.
     2. Select **USB-EPP/I2C… CH341A** (ID `1A86 5512`).
     3. Choose **libusb-win32** and click **Replace Driver**.

     LaserDRW and CorelLaser will no longer work with the laser after this.
     To switch back, use Device Manager. Another option is Scorch's
     [driver installer](https://github.com/scorchworks/K40-Whisperer-Driver-Installer).
4. Unzip Kerfly (for example to `C:\Kerfly`) and double-click
   **`start_kerfly.bat`**. The first start installs the libraries. This needs
   internet and takes a few minutes.

## Linux (Debian / Ubuntu)

```bash
sudo apt install python3-venv inkscape
git clone https://github.com/cyryllo/Kerfly && cd Kerfly
./start_kerfly.sh
```

To use the laser without root, run this once, then log out and back in:

```bash
sudo groupadd -f lasercutter
sudo usermod -a -G lasercutter $USER
echo 'SUBSYSTEM=="usb", ATTRS{idVendor}=="1a86", ATTRS{idProduct}=="5512", ENV{DEVTYPE}=="usb_device", MODE="0664", GROUP="lasercutter"' | sudo tee /etc/udev/rules.d/97-ctc-lasercutter.rules
```

## Self-test

Before the first job, check the installation. Plug in and switch on the laser,
then run in the Kerfly folder:

- Windows (Command Prompt): `start_kerfly.bat --self-test`
- Linux: `./start_kerfly.sh --self-test`

Kerfly prints one line per check: libraries, USB driver, whether the K40 is
found (it is not moved), Inkscape, the settings folder, and that the window
opens a design. `FAIL` lines must be fixed; `WARN` lines are optional or mean
that the laser is not connected. Send this output along with any bug report.

## First run with a laser

Keep a hand on the laser's power switch.

1. **Settings → Machine**: set your board, bed size and units.
2. **Laser** tab → **Connect** (plug icon). The head homes to the upper-left
   corner.
3. Jog the head with the arrows and check the directions.
4. Draw a 20 × 20 mm rectangle and run **Trace boundary** with the laser off.
5. Cut a small test at low power on scrap material. Try **Pause** (the second
   click resumes) and **Stop**.

## Troubleshooting

- **"USB error … libUSB driver not installed"**: install the driver
  (Windows, step 3) or the udev rule (Linux).
- **SVG files do not open**: install Inkscape, or set its path in Settings →
  Advanced.
