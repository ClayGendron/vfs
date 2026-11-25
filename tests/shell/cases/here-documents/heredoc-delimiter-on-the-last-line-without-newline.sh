# tier: language
# world: none
echo "start"
while IFS= read -r l; do echo "[$l]"; done <<EOF
last
EOF
