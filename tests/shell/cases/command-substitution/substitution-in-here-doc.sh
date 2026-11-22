# tier: language
# world: none
n=3
while IFS= read -r l; do echo "$l"; done <<EOF
value: $(echo computed)
sum: $(echo $((n + 1)))
EOF
