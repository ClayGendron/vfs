# tier: language
# world: none
c() { echo "stack: ${FUNCNAME[*]}"; echo "depth: ${#FUNCNAME[@]}"; }
b() { c; }
a() { b; }
a
