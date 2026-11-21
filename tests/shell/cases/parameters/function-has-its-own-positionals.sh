# tier: language
# world: none
f() { echo "in f: $# [$1]"; set -- z; echo "in f after set: $1"; }
set -- a b
f x
echo "top: $# $1"
