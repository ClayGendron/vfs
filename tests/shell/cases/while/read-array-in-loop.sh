# tier: language
# world: none
while read -r -a parts; do
  echo "count=${#parts[@]} last=${parts[-1]}"
done <<'EOF'
a b c
d e
EOF
