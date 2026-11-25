# tier: language
# world: none
while IFS= read -r l; do echo "$l"; done <<EOF | while IFS= read -r m; do echo "piped: $m"; done
a
b
EOF
