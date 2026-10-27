#!/bin/sh
# Step 3c: install numpy's pure-Python half (and generated __config__.py / version.py) with meson into a destdir,
# then build python314-numpy.zip = stdlib + numpy (stored).  The .so archives meson installs too are deleted from the zip input.
set -eu
HERE=$(CDPATH= cd "$(dirname "$0")/.." && pwd -P)
export WASI_SDK_PATH="$HERE/build/tools/wasi-sdk-24.0-arm64-macos"
export PATH="$HERE/.venv-build/bin:$PATH"
B="$HERE/build/numpy-2.5.2/build-wasi"
D="$HERE/build/numpy-install"
rm -rf "$D"
"$HERE/.venv-build/bin/python" "$HERE/build/numpy-2.5.2/vendored-meson/meson/meson.py" install -C "$B" --destdir "$D" --tags python-runtime --quiet
site=$(find "$D" -type d -name numpy -path '*site-packages*' | head -1)
echo "installed numpy at: $site"
find "$site" -name '*.so' -delete
find "$site" -name '*.so.deps' -delete
"$HERE/.venv-build/bin/python" "$HERE/scripts/make_stdlib_zip.py" --lib "$HERE/build/Python-3.14.8/Lib" --extra "$(dirname "$site")" "$@" "$HERE/build/python314-numpy.zip"
