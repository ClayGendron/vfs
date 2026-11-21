# tier: language
# world: none
for i in 1 2 3; do echo "item $i" > inside.txt; done
mapfile -t lines < inside.txt
printf '[%s]\n' "${lines[@]}"
