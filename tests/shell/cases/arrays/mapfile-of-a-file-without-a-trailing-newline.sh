# tier: language
# world: seed
mapfile lines < data/nonl.txt
echo "count=${#lines[@]}"
printf '<%s>\n' "${lines[0]}"
