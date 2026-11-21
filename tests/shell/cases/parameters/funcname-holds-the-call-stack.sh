# tier: language
# world: none
f() { echo "${FUNCNAME[0]} ${FUNCNAME[1]} ${FUNCNAME[2]-none}"; echo "depth=${#FUNCNAME[@]}"; }
g() { f; }
g
