# tier: language
# world: none
for i in a b; do echo "$i"; done | while read -r l; do echo "got $l"; done
