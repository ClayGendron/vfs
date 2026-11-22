# tier: language
# world: none
printf 'one\ntwo' > f.txt
mapfile -t arr < f.txt
echo "count=${#arr[@]} last=[${arr[-1]}]"
mapfile arr < f.txt
printf '%q\n' "${arr[@]}"
