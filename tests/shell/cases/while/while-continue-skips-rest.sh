# tier: language
# world: none
i=0
while [ "$i" -lt 5 ]; do
  i=$((i + 1))
  [ $((i % 2)) -eq 0 ] && continue
  echo "odd $i"
done
