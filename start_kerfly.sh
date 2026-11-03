#!/bin/sh
# Start Kerfly on Linux. The first start creates a Python environment in .venv
# and installs the libraries (needs internet, a few minutes).
cd "$(dirname "$0")" || exit 1
if [ ! -x .venv/bin/python ]; then
    echo "Creating the Python environment in .venv ..."
    if ! python3 -m venv .venv; then
        echo "Could not create it. On Debian/Ubuntu run: sudo apt install python3-venv"
        exit 1
    fi
    .venv/bin/python -m pip install --upgrade pip
    if ! .venv/bin/python -m pip install -r requirements.txt; then
        echo "Installing the libraries failed. Check the internet connection and run this again."
        rm -rf .venv
        exit 1
    fi
    # optional: offset of the boundary trace; Kerfly works without it
    .venv/bin/python -m pip install -r requirements-optional.txt || \
        echo "Optional library pyclipper was not installed; Kerfly works without it."
fi
exec .venv/bin/python kerfly.py "$@"
