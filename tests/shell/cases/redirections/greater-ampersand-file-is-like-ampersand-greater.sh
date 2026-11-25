# tier: language
# world: none
{ echo out; echo err >&2; } >& both.txt
mapfile -t lines < both.txt
printf '[%s]\n' "${lines[@]}"
