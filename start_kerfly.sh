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
    cp requirements.txt .venv/kerfly-requirements.txt
fi
# after an update: install libraries that were added since the last start
if ! cmp -s requirements.txt .venv/kerfly-requirements.txt; then
    echo "Updating the libraries ..."
    if .venv/bin/python -m pip install -r requirements.txt; then
        cp requirements.txt .venv/kerfly-requirements.txt
    else
        echo "Updating the libraries failed; Kerfly starts anyway."
    fi
fi
# the optional libraries (pyclipper: offsets and the boundary trace; spyrrow: nesting by outlines), also
# those added in an update; tried once for each change of the list: Kerfly works without them
if ! cmp -s requirements-optional.txt .venv/kerfly-requirements-optional.txt; then
    echo "Installing the optional libraries ..."
    .venv/bin/python -m pip install -r requirements-optional.txt || \
        echo "Some optional libraries were not installed; Kerfly works without them (fewer functions)."
    cp requirements-optional.txt .venv/kerfly-requirements-optional.txt
fi
exec .venv/bin/python kerfly.py "$@"
