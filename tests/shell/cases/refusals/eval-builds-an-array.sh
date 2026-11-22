# tier: language
# world: none
words="'one two' three"
eval "arr=($words)"
echo "count=${#arr[@]}"
printf '[%s]\n' "${arr[@]}"
