# tier: language
# world: none
x=$(echo captured; echo to-stderr >&2) 2> err.txt
echo "x=[$x]"
mapfile -t e < err.txt
echo "err lines=${#e[@]} [${e[*]}]"
