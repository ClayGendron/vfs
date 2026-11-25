# tier: language
# world: none
unset missing
while IFS= read -r line; do echo "$line"; done <<EOF
value: ${missing:?is required}
EOF
echo "not reached"
