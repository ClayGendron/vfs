# tier: language
# world: none
f() { declare -g x=from-f; declare -gi n=2+2; }
f
echo "x=$x n=$n"
