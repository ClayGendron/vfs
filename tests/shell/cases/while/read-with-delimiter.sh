# tier: language
# world: none
while IFS= read -r -d , item; do echo "[$item]"; done <<< "a,b,c,"
