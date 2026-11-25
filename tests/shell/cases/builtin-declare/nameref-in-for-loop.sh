# tier: language
# world: none
a=1 b=2 c=3
declare -n r
for r in a b c; do
  echo "$r"
done
