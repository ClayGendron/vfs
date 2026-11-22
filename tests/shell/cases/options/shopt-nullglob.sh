# tier: language
# world: none
# world: seed
echo "default: " *.none
shopt -s nullglob
echo "nullglob: [" *.none "]"
a=(*.none)
echo "count=${#a[@]}"
