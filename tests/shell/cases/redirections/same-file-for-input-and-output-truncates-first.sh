# tier: language
# world: none
printf 'line1\nline2\n' > f
while IFS= read -r l; do echo "$l"; done < f > f
mapfile -t lines < f
echo "lines=${#lines[@]}"
