# tier: language
# world: none
for i in a b c; do echo "$i" >> acc.txt; done
mapfile -t lines < acc.txt
echo "${lines[*]}"
