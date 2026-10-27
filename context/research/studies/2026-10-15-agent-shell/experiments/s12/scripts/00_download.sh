#!/bin/sh
# Spike s12 step 1: fetch the pinned toolchain and sources into downloads/ (untrusted data; never installed system-wide).
set -eu
HERE=$(CDPATH= cd "$(dirname "$0")/.." && pwd -P)
D="$HERE/downloads"
cd "$D"
get() { # url
  f=$(basename "$1")
  [ -s "$f" ] || curl -sSL --retry 3 -o "$f" "$1"
  printf '%s\n' "$f"
}
get https://github.com/WebAssembly/wasi-sdk/releases/download/wasi-sdk-24/wasi-sdk-24.0-arm64-macos.tar.gz &
get https://github.com/bytecodealliance/wizer/releases/download/v11.0.3/wizer-v11.0.3-aarch64-macos.tar.xz &
get https://github.com/bytecodealliance/wasmtime/releases/download/v49.0.3/wasmtime-v49.0.3-aarch64-macos.tar.xz &
get https://www.python.org/ftp/python/3.14.8/Python-3.14.8.tar.xz &
get https://files.pythonhosted.org/packages/9a/80/db0b4559e57ec36362bedbb05530a87fafbcb6067708c946967a41d449e7/numpy-2.5.2.tar.gz &
get "$(curl -sS https://pypi.org/pypi/pandas/3.0.6/json | python3 -c 'import json,sys; print([u["url"] for u in json.load(sys.stdin)["urls"] if u["packagetype"]=="sdist"][0])')" &
get https://github.com/brettcannon/cpython-wasi-build/releases/download/v3.14.7/python-3.14.7-wasi_sdk-24.zip &
wait
shasum -a 256 *.tar.gz *.tar.xz *.zip | tee SHA256SUMS
ls -la
