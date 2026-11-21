# tier: language
# world: none
while IFS= read -r line; do
  echo "line: $line"
done <<EOF
first
second
third
EOF
