# tier: language
# world: none
while IFS=, read -r name age; do
  echo "name=$name age=$age"
done <<EOF
ada,36
alan,41
EOF
