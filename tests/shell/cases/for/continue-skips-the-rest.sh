# tier: language
# world: none
for i in 1 2 3 4; do
  [ $((i % 2)) -eq 0 ] && continue
  echo "odd $i"
done
