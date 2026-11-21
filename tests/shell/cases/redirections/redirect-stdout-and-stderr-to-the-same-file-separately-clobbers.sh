# tier: language
# world: none
{ echo out-text; echo ERR >&2; } > same.txt 2> same.txt
mapfile -t lines < same.txt
echo "lines=${#lines[@]}"
printf '[%s]\n' "${lines[@]}"
