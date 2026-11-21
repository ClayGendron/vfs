# tier: language
# world: none
while read -r first rest; do
  echo "first=[$first] rest=[$rest]"
done <<'EOF'
a b c d
EOF
