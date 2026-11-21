# tier: language
# world: none
echo start > all.txt
{ echo out; echo err >&2; } &>> all.txt
mapfile -t lines < all.txt
printf '[%s]\n' "${lines[@]}"
