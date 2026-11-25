# tier: language
# world: none
n=0
while read -r line; do
  n=$((n + 1))
done <<EOF
1
2
3
4
EOF
echo "n=$n"
