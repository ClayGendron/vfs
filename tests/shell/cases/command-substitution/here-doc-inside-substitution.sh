# tier: language
# world: none
x=$(while IFS= read -r l; do printf '<%s>' "$l"; done <<EOF
one
two
EOF
)
echo "[$x]"
