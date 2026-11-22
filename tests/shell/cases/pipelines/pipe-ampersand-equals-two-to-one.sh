# tier: language
# world: none
f() { echo to-stderr >&2; }
f 2>&1 | { read -r a; echo "a=[$a]"; }
f |& { read -r b; echo "b=[$b]"; }
