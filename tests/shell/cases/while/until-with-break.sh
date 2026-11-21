# tier: language
# world: none
i=0
until false; do
  i=$((i + 1))
  [ "$i" -ge 2 ] && break
done
echo "i=$i"
