#!/bin/sh
# Build Kerfly-<version>-x86_64.AppImage: one file that runs on most Linux
# systems without installing anything (the program, Python and Qt inside).
#
#   APPIMAGETOOL=/path/to/appimagetool packaging/linux/build-appimage.sh
#
# Needs the Python environment with requirements.txt and PyInstaller
# (PYTHON, default .venv/bin/python) and appimagetool
# (https://github.com/AppImage/appimagetool). The release workflow
# (.github/workflows/release.yml) builds it on Ubuntu 22.04, so the AppImage
# also runs on older systems.
#
# Copyright (C) 2026 Kerfly contributors
# Licensed under the GNU General Public License v3 or later. See LICENSE.
set -eu
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
PYTHON="${PYTHON:-.venv/bin/python}"
TOOL="${APPIMAGETOOL:-appimagetool}"
VERSION="$("$PYTHON" -c 'import kerfly; print(kerfly.__version__)')"

"$PYTHON" -m PyInstaller packaging/kerfly.spec --noconfirm --distpath build/pyinstaller/dist \
    --workpath build/pyinstaller/work

APPDIR=build/Kerfly.AppDir
rm -rf "$APPDIR"
mkdir -p "$APPDIR/usr/lib" "$APPDIR/usr/share/applications" "$APPDIR/usr/share/icons/hicolor/256x256/apps"
cp -a build/pyinstaller/dist/Kerfly "$APPDIR/usr/lib/kerfly"
cp packaging/linux/99-kerfly-k40.rules "$APPDIR/usr/lib/kerfly/"
cp packaging/linux/kerfly.desktop "$APPDIR/kerfly.desktop"
cp packaging/linux/kerfly.desktop "$APPDIR/usr/share/applications/kerfly.desktop"
cp kerfly/gui/icons/kerfly.png "$APPDIR/kerfly.png"
cp kerfly/gui/icons/kerfly.png "$APPDIR/usr/share/icons/hicolor/256x256/apps/kerfly.png"
cat > "$APPDIR/AppRun" <<'RUN'
#!/bin/sh
# start Kerfly from inside the AppImage
HERE="$(dirname "$(readlink -f "$0")")"
exec "$HERE/usr/lib/kerfly/Kerfly" "$@"
RUN
chmod +x "$APPDIR/AppRun"

mkdir -p dist
OUT="dist/Kerfly-$VERSION-x86_64.AppImage"
# --appimage-extract-and-run: works without FUSE (containers, CI)
ARCH=x86_64 "$TOOL" --appimage-extract-and-run "$APPDIR" "$OUT"
echo "Written: $OUT"
