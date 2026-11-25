# tier: language
# world: none
set -- a b c
f() { shift; echo "in f: $*"; shift 2; echo "status of shift 2: $?"; }
f 1 2
echo "top: $*"
