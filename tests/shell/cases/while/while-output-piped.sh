# tier: language
# world: none
i=0
while [ "$i" -lt 2 ]; do echo "row $i"; i=$((i + 1)); done | while read -r l; do echo "got $l"; done
