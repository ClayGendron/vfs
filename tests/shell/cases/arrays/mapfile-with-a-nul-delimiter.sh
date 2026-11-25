# tier: language
# world: none
printf 'one\0two words\0three\0' > nul.dat
mapfile -t -d '' items < nul.dat
echo "count=${#items[@]}"
printf '[%s]\n' "${items[@]}"
