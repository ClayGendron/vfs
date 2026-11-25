# tier: language
# world: none
while IFS= read -r line; do echo "$line"; done <<EOF
upper: $(echo inner)
backticks: `echo old-style`
EOF
