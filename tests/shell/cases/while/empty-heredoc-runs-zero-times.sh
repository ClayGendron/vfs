# tier: language
# world: none
while read -r l; do echo "never"; done <<EOF
EOF
echo "status=$?"
