# tier: language
# world: none
echo first line > f
echo second line >> f
echo replaced > f
mapfile -t lines < f
echo "count=${#lines[@]}"
printf '[%s]\n' "${lines[@]}"
