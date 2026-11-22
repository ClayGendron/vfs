# tier: language
# world: none
for i in 1 2; do
  read -r line
  echo "$i:$line"
done <<EOF
alpha
beta
EOF
