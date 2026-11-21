# tier: language
# world: none
while IFS= read -r line; do echo "[$line]"; done <<EOF
it's fine
an "open quote
EOF
