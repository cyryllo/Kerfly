#!/bin/sh
# Build and check the AppImage on this computer, in an Ubuntu 22.04 container,
# the same way the release workflow does on GitHub (a fallback for when the
# GitHub runners cannot build it, for example while they cannot reach Ubuntu's
# package servers). Ubuntu 22.04 keeps the AppImage running on older systems;
# built straight on a newer system it would not start there.
#
#   packaging/linux/build-appimage-docker.sh [tag or commit, default: HEAD]
#
# Needs Docker. Builds from a clean copy of that version (git archive), runs the
# AppImage's --self-test and --release-test, and writes it to dist/. Then attach
# it to the GitHub release by hand (Releases -> Edit -> drop the file).
#
# Copyright (C) 2026 Kerfly contributors
# Licensed under the GNU General Public License v3 or later. See LICENSE.
set -eu
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
REF="${1:-HEAD}"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/kerfly-appimage-XXXXXX")"
trap 'rm -rf "$WORK"' EXIT
mkdir -p "$WORK/src"
git -C "$ROOT" archive "$REF" | tar -x -C "$WORK/src"
cat > "$WORK/inside.sh" <<'INSIDE'
#!/bin/bash
# inside ubuntu:22.04
set -eux
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y --no-install-recommends software-properties-common gpg-agent curl ca-certificates \
    binutils file libegl1 libgl1 libxkbcommon0 libxkbcommon-x11-0 libfontconfig1 libdbus-1-3 libusb-1.0-0 \
    libglib2.0-0 fonts-dejavu-core libxcb-cursor0 libxcb-icccm4 libxcb-keysyms1 libxcb-shape0 \
    libxcb-xinerama0 libxcb-randr0 libxcb-render-util0 libxcb-image0
add-apt-repository -y ppa:deadsnakes/ppa          # Python 3.13, as on GitHub
apt-get update
apt-get install -y --no-install-recommends python3.13 python3.13-venv python3.13-dev
cd /work/src
python3.13 -m venv /venv
/venv/bin/python -m pip install --upgrade pip
/venv/bin/python -m pip install -r requirements.txt pyinstaller
/venv/bin/python -m pip install -r requirements-optional.txt
curl -fsSL -o /work/appimagetool \
    https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage
chmod +x /work/appimagetool
PYTHON=/venv/bin/python APPIMAGETOOL=/work/appimagetool packaging/linux/build-appimage.sh
chmod +x dist/*.AppImage
QT_QPA_PLATFORM=offscreen dist/Kerfly-*-x86_64.AppImage --appimage-extract-and-run --self-test
QT_QPA_PLATFORM=offscreen dist/Kerfly-*-x86_64.AppImage --appimage-extract-and-run --release-test
cp dist/Kerfly-*-x86_64.AppImage /work/
chown "$HOST_UID:$HOST_GID" /work/Kerfly-*-x86_64.AppImage
INSIDE
chmod +x "$WORK/inside.sh"
docker run --rm -v "$WORK:/work" -e HOST_UID="$(id -u)" -e HOST_GID="$(id -g)" ubuntu:22.04 /work/inside.sh
mkdir -p "$ROOT/dist"
cp "$WORK"/Kerfly-*-x86_64.AppImage "$ROOT/dist/"
echo "Written: $(ls "$ROOT"/dist/Kerfly-*-x86_64.AppImage | tail -1)"
