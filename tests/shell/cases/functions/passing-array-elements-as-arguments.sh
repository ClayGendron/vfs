# tier: language
# world: none
f() { echo "n=$#"; printf '[%s]\n' "$@"; }
arr=("x y" z "")
f "${arr[@]}"
