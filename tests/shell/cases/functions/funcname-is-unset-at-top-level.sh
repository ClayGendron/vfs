# tier: language
# world: none
echo "top: [${FUNCNAME-unset}] count=${#FUNCNAME[@]}"
f() { echo "in f: [${FUNCNAME[0]}] [${FUNCNAME[1]}]"; }
f
