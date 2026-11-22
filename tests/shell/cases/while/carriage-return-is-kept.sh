# tier: language
# world: none
while IFS= read -r l; do printf '%q\n' "$l"; done <<< $'dos\r'
