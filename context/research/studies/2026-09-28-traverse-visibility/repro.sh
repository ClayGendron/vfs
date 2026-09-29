#!/bin/sh
# Traverse (x) vs list (r) on a directory ABOVE a subtree the caller can use.
#
# Tree:  P/alpha/file.txt   <- the "granted" file (think /projects/alpha)
#        P/beta/secret.txt  <- a sibling the caller should not learn about
#
# The script runs as one non-root user and chmods its own directory P.
# For the owner, the owner bits decide, so owner mode 0100 (--x) plays the
# role of the classic 0711 home directory seen by "others": search, no list.
# POSIX sh, no sudo; runs on macOS and Linux. Scratch lives under
# ${SCRATCH:-<this dir>/.scratch} and is removed on exit.

set -u
HERE=$(cd "$(dirname "$0")" && pwd)
BASE=${SCRATCH:-$HERE/.scratch}
mkdir -p "$BASE"
T=$(mktemp -d "$BASE/tv.XXXXXX")
P="$T/P"

cleanup() {
	chmod 700 "$P" 2>/dev/null
	chmod -R u+rwx "$T" 2>/dev/null
	rm -rf "$T"
	rmdir "$BASE" 2>/dev/null
}
trap cleanup EXIT INT TERM

# stat format differs: GNU coreutils uses -c, BSD/macOS uses -f.
if stat -c '%h' / >/dev/null 2>&1; then
	meta() { stat -c 'mode=%A links=%h size=%s mtime=%Y' "$1"; }
else
	meta() { stat -f 'mode=%Sp links=%l size=%z mtime=%m' "$1"; }
fi

run() {
	label=$1
	shift
	out=$(cd "$T" && "$@" 2>&1)
	rc=$?
	flat=$(printf '%s' "$out" | tr '\n' ' ' | sed "s|$T/||g; s|$T|T|g" | cut -c1-120)
	printf '  %-40s rc=%-3s %s\n' "$label" "$rc" "$flat"
}

mkdir -p "$P/alpha" "$P/beta"
echo "alpha data" >"$P/alpha/file.txt"
echo "beta secret" >"$P/beta/secret.txt"

echo "# platform: $(uname -sr)  user: uid=$(id -u) (non-root)"
echo

for mode in 700 100 400 000; do
	case $mode in
	700) what="rwx: list + search (control)" ;;
	100) what="--x: search only (the 0711 home-dir pattern)" ;;
	400) what="r--: list only, no search" ;;
	000) what="---: nothing" ;;
	esac
	chmod "$mode" "$P"
	echo "## P mode 0$mode  ($what)"
	run "ls P            (list the ancestor)" ls P
	run "stat P          (the ancestor itself)" meta P
	run "stat P/beta     (existing sibling)" meta P/beta
	run "stat P/nope     (missing name)" meta P/nope
	run "cat P/alpha/file.txt (the grant)" cat P/alpha/file.txt
	run "ls P/alpha      (list the grant)" ls P/alpha
	run "glob P/*" sh -c 'for f in P/*; do printf "%s " "$f"; done'
	run "glob P/alpha/*" sh -c 'for f in P/alpha/*; do printf "%s " "$f"; done'
	run "find P" find P
	run "mkdir -p P/alpha/new/deep" mkdir -p P/alpha/new/deep
	run "mkdir P/gamma   (create sibling)" mkdir P/gamma
	chmod 700 "$P"
	rm -rf "$P/alpha/new" "$P/gamma"
	echo
done

echo "## Leak probe: what a search-only (--x) caller learns from stat P"
chmod 100 "$P"
before=$(meta "$P")
chmod 700 "$P"
sleep 1
mkdir "$P/gamma" # a hidden sibling appears, created by someone else
chmod 100 "$P"
after=$(meta "$P")
echo "  before hidden sibling: $before"
echo "  after  hidden sibling: $after"
run "stat P/gamma (guess the new name)" meta P/gamma
chmod 700 "$P"
