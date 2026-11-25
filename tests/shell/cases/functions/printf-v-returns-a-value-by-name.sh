# tier: language
# world: none
get() { printf -v "$1" '%s-%s' "$2" "$3"; }
get out left right
echo "out=$out"
