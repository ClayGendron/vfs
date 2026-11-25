# tier: language
# world: none
v=value
while IFS= read -r l; do echo "[$l]"; done <<EOF
$v $(echo sub) $((1 + 2)) \$v
EOF
