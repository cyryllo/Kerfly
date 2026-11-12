#!/bin/bash
# Every check before a release, on this computer (needs xvfb-run): core, window,
# translations, laser output identical to K40 Whisperer, reference results,
# self-test, release check, the clicked-through release session at Full HD and
# three random sessions. Prints one short block per suite; anything but
# "passed" / "match" / "0 problems" / "all fine" needs a look.
#
#   tools/run_release_checks.sh
#
# Copyright (C) 2026 Kerfly contributors
# Licensed under the GNU General Public License v3 or later. See LICENSE.
cd "$(dirname "$0")/.." || exit 1
export QT_QPA_PLATFORM=xcb                  # never a window on the desktop: everything runs in xvfb
FULLHD=(xvfb-run -a -s "-screen 0 1920x1080x24")
run() { echo "=== $1"; shift; "$@" 2>&1 | grep -E "FAIL|Traceback|Error|passed|failed|match|problems|steps" | tail -4; }
run core .venv/bin/python tests/test_core.py
run gui "${FULLHD[@]}" .venv/bin/python tests/test_gui.py
run i18n xvfb-run -a .venv/bin/python tests/test_i18n.py
run regression xvfb-run -a .venv/bin/python tests/regression.py
run references xvfb-run -a .venv/bin/python tests/test_references.py
echo "=== self-test"; xvfb-run -a .venv/bin/python -m kerfly --self-test 2>&1 | tail -2
echo "=== release-test"; xvfb-run -a .venv/bin/python -m kerfly --release-test 2>&1 | tail -2
run release "${FULLHD[@]}" .venv/bin/python tests/test_release.py
for seed in 1 2 3; do
    run "random $seed" "${FULLHD[@]}" .venv/bin/python tests/test_random.py --seed "$seed"
done
echo ALLDONE
