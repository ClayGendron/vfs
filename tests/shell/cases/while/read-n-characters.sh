# tier: language
# world: none
while IFS= read -r -n 2 pair; do printf '[%s]' "$pair"; done <<< "abcde"
echo
