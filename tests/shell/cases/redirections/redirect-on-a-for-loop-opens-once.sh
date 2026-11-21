# tier: language
# world: none
for i in 1 2 3; do echo "item $i"; done > loop.txt
mapfile -t lines < loop.txt
printf '[%s]\n' "${lines[@]}"
