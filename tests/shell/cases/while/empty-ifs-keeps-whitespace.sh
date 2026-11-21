# tier: language
# world: none
while IFS= read -r l; do printf '[%s]\n' "$l"; done <<< "   leading and trailing   "
