#!/bin/sh
# Step 2 (the floor): build CPython 3.14.8 for wasm32-wasip1 with its own Tools/wasm/wasi driver and wasi-sdk 24.
# The driver builds a native "build Python" first (cross-build/<host-triple>/) and then the WASI one (cross-build/wasm32-wasip1/).
set -eu
HERE=$(CDPATH= cd "$(dirname "$0")/.." && pwd -P)
export WASI_SDK_PATH="$HERE/build/tools/wasi-sdk-24.0-arm64-macos"
export PATH="$HERE/build/tools/wasmtime-v49.0.3-aarch64-macos:$PATH"
cd "$HERE/build/Python-3.14.8"
time "$HERE/.venv-build/bin/python" Tools/wasm/wasi build --quiet --logdir "$HERE/outputs/cpython-floor-logs" "$@"
ls -la cross-build/wasm32-wasip1/python.wasm
shasum -a 256 cross-build/wasm32-wasip1/python.wasm
