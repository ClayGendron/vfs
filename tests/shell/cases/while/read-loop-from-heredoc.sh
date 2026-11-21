# tier: language
# world: none
while read -r name age; do
  echo "$name is $age"
done <<EOF
ada 36
alan 41
EOF
