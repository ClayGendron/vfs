# tier: language
# world: none
target=named.out
{ echo out; echo err >&2; } >&$target
mapfile -t lines < named.out
printf '[%s]\n' "${lines[@]}"
