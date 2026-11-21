# tier: language
# world: none
x=value
while IFS= read -r l; do printf '%s\n' "$l"; done <<'EOF'
x is $x
cmd is $(echo no)
back\slash and `tick`
EOF
