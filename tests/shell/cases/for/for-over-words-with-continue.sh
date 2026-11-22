# tier: language
# world: none
total=0
for n in 1 2 3 4; do
  if [ "$n" -eq 3 ]; then
    continue
  fi
  total=$(( total + n ))
  echo "n=$n total=$total"
done
echo "done $total"
