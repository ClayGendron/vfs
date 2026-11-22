# tier: language
# world: none
i=0
while [ "$i" -lt 3 ]; do
  echo "i=$i"
  i=$((i + 1))
done
echo "after i=$i"
