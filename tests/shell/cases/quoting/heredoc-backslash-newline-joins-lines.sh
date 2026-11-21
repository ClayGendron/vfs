# tier: language
# world: none
while IFS= read -r l; do printf '[%s]\n' "$l"; done <<EOF
one \
two
EOF
while IFS= read -r l; do printf '[%s]\n' "$l"; done <<'EOF'
one \
two
EOF
