#!/bin/sh
# numpy chain: rebuild archives (03) -> relink python.wasm with Setup.local (04) -> install + zip (05).
set -eu
HERE=$(CDPATH= cd "$(dirname "$0")/.." && pwd -P)
rm -rf "$HERE/build/numpy-2.5.2/build-wasi"
"$HERE/scripts/03_numpy_build.sh" > "$HERE/outputs/05_numpy_build.log" 2>&1 || { echo "03 failed"; grep -n 'error:\|FAILED' "$HERE/outputs/05_numpy_build.log" | head -20; exit 1; }
echo "03 ok: $(grep -c 'Compiling' "$HERE/outputs/05_numpy_build.log") compile steps"; tail -40 "$HERE/outputs/05_numpy_build.log" | grep '\.so$\|\.a$' | sed "s#$HERE/##"
"$HERE/scripts/04_link_python_numpy.sh" > "$HERE/outputs/06_link_numpy.log" 2>&1 || { echo "04 failed"; tail -40 "$HERE/outputs/06_link_numpy.log"; exit 1; }
echo "04 ok"; tail -4 "$HERE/outputs/06_link_numpy.log"
"$HERE/scripts/05_numpy_install_zip.sh" > "$HERE/outputs/07_numpy_zip.log" 2>&1 || { echo "05 failed"; tail -20 "$HERE/outputs/07_numpy_zip.log"; exit 1; }
echo "05 ok"; tail -2 "$HERE/outputs/07_numpy_zip.log"
