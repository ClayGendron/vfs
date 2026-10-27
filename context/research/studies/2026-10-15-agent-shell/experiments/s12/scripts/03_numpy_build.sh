#!/bin/sh
# Step 3: cross-compile numpy 2.5.2 for wasm32-wasip1 as static archives with numpy's vendored meson + a cross file.
set -eu
HERE=$(CDPATH= cd "$(dirname "$0")/.." && pwd -P)
export WASI_SDK_PATH="$HERE/build/tools/wasi-sdk-24.0-arm64-macos"
export PATH="$HERE/.venv-build/bin:$PATH"
SRC="$HERE/build/numpy-2.5.2"
B="$SRC/build-wasi"
sed "s#@S12@#$HERE#g" "$HERE/cross/wasi-numpy.cross" > "$HERE/build/wasi-numpy.cross"
cd "$SRC"
if [ ! -f "$B/build.ninja" ]; then
  "$HERE/.venv-build/bin/python" vendored-meson/meson/meson.py setup "$B" \
    --cross-file "$HERE/build/wasi-numpy.cross" \
    --buildtype=release -Dallow-noblas=true -Dblas=none -Dlapack=none \
    -Ddisable-optimization=true -Ddisable-threading=true -Ddisable-highway=true -Ddisable-intel-sort=true -Ddisable-svml=true \
    -Dtest-simd=BASELINE "$@"
fi
time ninja -C "$B" -j 10
find "$B" -name '*.so' -o -name '*.a' | sort | xargs ls -la
