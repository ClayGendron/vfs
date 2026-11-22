# tier: language
# world: none
name=world
count=3
while IFS= read -r line; do echo "$line"; done <<EOF
hello $name
count is ${count}
EOF
