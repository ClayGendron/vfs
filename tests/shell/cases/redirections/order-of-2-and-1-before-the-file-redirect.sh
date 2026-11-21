# tier: language
# world: none
{ echo out; echo err >&2; } 2>&1 > only-stdout.txt
echo "--- file:"
mapfile -t lines < only-stdout.txt
printf '[%s]\n' "${lines[@]}"
