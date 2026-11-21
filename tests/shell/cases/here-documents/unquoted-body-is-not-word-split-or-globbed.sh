# tier: language
# world: seed
while IFS= read -r line; do echo "[$line]"; done <<EOF
star: *
many    spaces   kept
EOF
