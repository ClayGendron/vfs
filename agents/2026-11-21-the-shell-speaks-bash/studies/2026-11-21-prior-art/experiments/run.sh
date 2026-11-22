#!/bin/bash
# usage: run.sh 'line'   -- runs the native probe with a 60 s timeout, prints the line and the result
echo "\$ shellprobe $(printf %q "$1")"
PROBE_SECS=${PROBE_SECS:-20} timeout 60 $SCRATCH/rs/target/release/shellprobe "$1" 2>&1 | head -c 2000
echo "(timeout-exit=$?)"
echo
