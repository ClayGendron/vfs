# tier: language
# world: none
n=4
while IFS= read -r line; do echo "$line"; done <<EOF
sum=$((n + 1)) square=$((n * n))
EOF
