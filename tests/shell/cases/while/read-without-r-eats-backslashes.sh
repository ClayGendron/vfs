# tier: language
# world: none
while read l; do printf '[%s]\n' "$l"; done <<'EOF'
a\tb
c\\d
EOF
