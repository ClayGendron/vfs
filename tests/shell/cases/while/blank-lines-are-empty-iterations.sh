# tier: language
# world: none
n=0
while IFS= read -r l; do n=$((n + 1)); printf '%s:[%s]\n' "$n" "$l"; done <<'EOF'
a

b
EOF
