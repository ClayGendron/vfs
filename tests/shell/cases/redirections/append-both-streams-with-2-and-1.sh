# tier: language
# world: none
echo start > log
{ echo out; echo err >&2; } >> log 2>&1
mapfile -t lines < log
printf '[%s]\n' "${lines[@]}"
