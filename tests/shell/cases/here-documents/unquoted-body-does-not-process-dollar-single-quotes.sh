# tier: language
# world: none
while IFS= read -r line; do echo "$line"; done <<EOF
ansi: $'a\tb'
EOF
