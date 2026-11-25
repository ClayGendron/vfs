# tier: language
# world: none
{ echo out; echo err >&2; } &> all.txt
mapfile -t lines < all.txt
echo "lines=${#lines[@]}"
printf '[%s]\n' "${lines[@]}"
