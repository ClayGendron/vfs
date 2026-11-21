# tier: language
# world: none
while IFS= read -r line; do echo "$line"; done <<EOF
quote: \"
letter: \n
single: \'
EOF
