# tier: language
# world: none
arr=(x y)
mapfile -t -O "${#arr[@]}" arr <<< $'z\nw'
printf '[%s]\n' "${arr[@]}"
