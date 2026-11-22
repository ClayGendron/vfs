# tier: language
# world: none
name=world
while IFS= read -r line; do echo "$line"; done <<E"O"F
hello $name
EOF
