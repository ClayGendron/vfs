# tier: language
# world: none
n=0
until [ "$n" -ge 4 ]; do
  n=$((n + 1))
  [ $((n % 2)) -eq 0 ] && continue
  echo "odd n=$n"
done
