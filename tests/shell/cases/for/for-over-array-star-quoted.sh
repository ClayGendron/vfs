# tier: language
# world: none
arr=(one "two words" three)
for e in "${arr[*]}"; do printf '[%s]\n' "$e"; done
