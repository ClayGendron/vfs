# tier: language
# world: none
i=0
until [ "$i" -ge 3 ]; do
  echo "i=$i"
  i=$((i + 1))
done
