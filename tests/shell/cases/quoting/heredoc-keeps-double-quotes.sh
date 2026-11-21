# tier: language
# world: none
x=v
while IFS= read -r l; do printf '%s\n' "$l"; done <<EOF
"$x" and '$x'
EOF
