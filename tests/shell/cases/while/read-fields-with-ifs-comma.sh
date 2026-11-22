# tier: language
# world: none
while IFS=, read -r name age city; do
  echo "name=$name age=$age city=$city"
done <<'EOF'
grace,85,new york
linus,28,helsinki
EOF
