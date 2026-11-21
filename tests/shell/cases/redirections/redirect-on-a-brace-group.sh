# tier: language
# world: none
{ echo one; echo two; } > g.txt
mapfile -t lines < g.txt
printf '[%s]\n' "${lines[@]}"
