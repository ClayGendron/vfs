# tier: language
# world: none
false
while IFS= read -r l; do echo "$l"; done <<EOF
last status: $?
EOF
