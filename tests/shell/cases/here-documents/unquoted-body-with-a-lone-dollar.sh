# tier: language
# world: none
while IFS= read -r line; do echo "[$line]"; done <<EOF
price: 5$
alone: $ here
EOF
