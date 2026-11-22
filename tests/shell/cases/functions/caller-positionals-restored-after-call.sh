# tier: language
# world: none
set -- top1 top2
f() { echo "in f: $# $1"; set -- x y z; echo "in f after set: $# $1"; }
f only
echo "after f: $# $1 $2"
