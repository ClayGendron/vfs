# tier: language
# world: none
while IFS= read -r l; do echo "l=$l"; done <<< $'one\ntwo\nthree'
