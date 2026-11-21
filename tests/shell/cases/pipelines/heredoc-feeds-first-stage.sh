# tier: language
# world: none
while IFS= read -r l; do echo "<$l>"; done <<EOF | { mapfile -t got; echo "${#got[@]}: ${got[*]}"; }
one
two
EOF
