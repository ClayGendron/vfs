# tier: language
# world: none
while IFS= read -r line; do echo "[$line]"; done <<EOF
joined \
together
next
EOF
