# tier: language
# world: none
read -r out < <(read -r in < <(echo inner); echo "outer[$in]")
echo "$out"
