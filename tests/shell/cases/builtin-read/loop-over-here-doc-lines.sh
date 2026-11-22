# tier: language
# world: none
while read -r line; do
  echo "got [$line]"
done <<'EOF'
first
  second  
third
EOF
