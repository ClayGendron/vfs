# tier: language
# world: none
for i in 1 2 3; do
  read -r line <<EOF
item $i
EOF
  echo "$line"
done
