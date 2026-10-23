#!/bin/sh
# Creates .venv for the PeerCam Bridge script and installs its packages.
# Usage: ./setup.sh [path/to/python3]
# The Python must be the same version as the one OBS uses: on Linux that's
# usually the system python3; on macOS the one set in OBS > Tools > Scripts >
# Python Settings.
set -e
cd "$(dirname "$0")"

PY="${1:-}"
if [ -z "$PY" ]; then
    for candidate in python3 python; do
        if command -v "$candidate" >/dev/null 2>&1; then
            PY="$candidate"
            break
        fi
    done
fi
if [ -z "$PY" ]; then
    echo "Python 3 was not found. Install it, or run: ./setup.sh /path/to/python3" >&2
    exit 1
fi

PYVER=$("$PY" -c 'import sys; print("%d.%d" % sys.version_info[:2])')
PYHOME=$("$PY" -c 'import sys; print(sys.base_prefix)')
echo "Using Python $PYVER from $PYHOME"

if [ ! -x .venv/bin/python ]; then
    echo "Creating .venv ..."
    if ! "$PY" -m venv .venv; then
        echo "Creating the venv failed. On Debian/Ubuntu: sudo apt install python3-venv" >&2
        exit 1
    fi
else
    echo "Reusing existing .venv. Delete the .venv folder to recreate it."
fi

.venv/bin/python -m pip install --upgrade pip --quiet
.venv/bin/python -m pip install -r requirements.txt

echo
echo "Done. Next, in OBS:"
echo "  1. macOS only: Tools > Scripts > Python Settings: set the install path to"
echo "       $PYHOME"
echo "  2. Scripts tab: press + and choose $(pwd)/peercam_bridge.py"
