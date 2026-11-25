# tier: language
# world: none
for n in 95 75 40; do
  echo "$n -> $(( n >= 90 ? 1 : n >= 70 ? 2 : 3 ))"
done
