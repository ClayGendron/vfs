# tier: language
# world: none
IFS=0
printf '[%s]\n' $((100 + 5))
echo ---
printf '[%s]\n' $((1000 + 5))
echo ---
printf '[%s]\n' "$((100 + 5))"
