#!/bin/sh
# zlib 1.3.1 as a static archive for wasm32-wasip1 (CPython's zlib, gzip, deflated zips, dateutil's zoneinfo tarball).
set -eu
HERE=$(CDPATH= cd "$(dirname "$0")/.." && pwd -P)
SDK="$HERE/build/tools/wasi-sdk-24.0-arm64-macos"
cd "$HERE/build" && rm -rf zlib-1.3.1 && tar xzf ../downloads/zlib-1.3.1.tar.gz && cd zlib-1.3.1
CC="$SDK/bin/clang --target=wasm32-wasip1" AR="$SDK/bin/llvm-ar" RANLIB="$SDK/bin/llvm-ranlib" CFLAGS="-O2" ./configure --static --prefix="$HERE/build/zlib-wasi" > configure.log 2>&1
# zlib's configure swaps in `libtool -o` as the archiver on Darwin hosts, which rejects wasm objects: name the archiver on the make line.
make -j10 AR="$SDK/bin/llvm-ar" ARFLAGS="rc" libz.a > make.log 2>&1 && make AR="$SDK/bin/llvm-ar" ARFLAGS="rc" install > install.log 2>&1
ls -la "$HERE/build/zlib-wasi/lib/libz.a" "$HERE/build/zlib-wasi/include/zlib.h"
