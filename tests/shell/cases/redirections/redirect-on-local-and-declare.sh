# tier: language
# world: none
f() { local v=1 > f.txt; echo "v=$v"; }
f
declare -i n=5 > d.txt
echo "n=$n"
mapfile -t a < f.txt; mapfile -t b < d.txt
echo "f.txt=${#a[@]} d.txt=${#b[@]}"
