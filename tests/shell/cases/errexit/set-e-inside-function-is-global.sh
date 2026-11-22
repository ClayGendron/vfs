# tier: language
# world: none
f() { set -e; echo "f set errexit"; }
f
shopt -o -q errexit && echo "errexit is on"
false
echo "not reached"
