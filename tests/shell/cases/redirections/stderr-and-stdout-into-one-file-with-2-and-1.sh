# tier: language
# world: none
{ echo out1; echo err1 >&2; echo out2; } > both.txt 2>&1
mapfile -t lines < both.txt
printf '[%s]\n' "${lines[@]}"
