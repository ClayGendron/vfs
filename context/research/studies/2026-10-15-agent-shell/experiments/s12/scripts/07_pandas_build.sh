#!/bin/sh
# Stretch: cross-compile pandas 3.0.6 for wasm32-wasip1 as static archives with the same cross file and wrapper.
set -eu
HERE=$(CDPATH= cd "$(dirname "$0")/.." && pwd -P)
export WASI_SDK_PATH="$HERE/build/tools/wasi-sdk-24.0-arm64-macos"
export PATH="$HERE/.venv-build/bin:$PATH"
export PYTHONPATH="$HERE/build/numpy-host-shim"
SRC="$HERE/build/pandas-3.0.6"
B="$SRC/build-wasi"
sed "s#@S12@#$HERE#g" "$HERE/cross/wasi-pandas.cross" > "$HERE/build/wasi-pandas.cross"
cd "$SRC"
if [ ! -f "$B/build.ninja" ]; then
  meson setup "$B" --cross-file "$HERE/build/wasi-pandas.cross" --buildtype=release "$@"
fi
time ninja -C "$B" -j 10
find "$B" -name '*.so' | sort | xargs ls -la | awk '{print $5, $9}'
