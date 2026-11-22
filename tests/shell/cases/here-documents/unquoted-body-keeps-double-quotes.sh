# tier: language
# world: none
v=val
while IFS= read -r line; do echo "$line"; done <<EOF
"$v" and "quoted words"
EOF
