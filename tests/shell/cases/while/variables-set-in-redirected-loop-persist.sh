# tier: language
# world: none
while read -r x; do last=$x; count=$((count + 1)); done <<EOF
p
q
EOF
echo "last=$last count=$count"
