# tier: language
# world: none
name=world
while IFS= read -r line; do echo "$line"; done <<\EOF
hello $name
EOF
