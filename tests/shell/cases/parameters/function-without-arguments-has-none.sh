# tier: language
# world: none
f() { echo "in f: $# [${1-unset}]"; }
set -- a b
f
