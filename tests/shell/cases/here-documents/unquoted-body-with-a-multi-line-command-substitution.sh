# tier: language
# world: none
while IFS= read -r line; do echo "[$line]"; done <<EOF
before $(echo one
echo two) after
EOF
