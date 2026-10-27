#!/bin/bash
# Link python-vfsmain.wasm (our main with the wizer.initialize export) from the same objects and libs as python.wasm.
set -euo pipefail
HERE=$(CDPATH= cd "$(dirname "$0")/.." && pwd -P)
W="$HERE/build/Python-3.14.8/cross-build/wasm32-wasip1"
CC="$HERE/build/tools/wasi-sdk-24.0-arm64-macos/bin/clang"
cd "$W"
MAKELOG=${MAKELOG:-$HERE/outputs/06_make.log}; OUT=${OUT:-python-vfsmain.wasm}
cflags=$(grep -m1 'Modules/_json.o' "$MAKELOG" | sed -E 's#^[^ ]+/clang ##; s# -c \.\./\.\./Modules/_json\.c -o Modules/_json\.o##')
$CC $cflags -DVFS_PREIMPORT="\"${VFS_PREIMPORT:-import encodings, io, os, sys, json, csv, re, numpy}\"" -c "$HERE/cross/vfs_main.c" -o Modules/vfs_main.o
link=$(grep -m1 -- '-o python.wasm Programs/python.o' "$MAKELOG" | sed -E "s#^[^ ]+/clang ##; s#-o python\.wasm Programs/python\.o#-o $OUT Modules/vfs_main.o#")
$CC -mexec-model=reactor $link 2> "$HERE/outputs/13_vfsmain_link.log" || { tail -5 "$HERE/outputs/13_vfsmain_link.log"; exit 1; }
ls -la "$OUT"; shasum -a 256 "$OUT"
