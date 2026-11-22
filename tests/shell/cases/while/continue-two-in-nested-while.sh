# tier: language
# world: none
i=0
while [ "$i" -lt 3 ]; do
  i=$((i + 1))
  j=0
  while true; do
    j=$((j + 1))
    [ "$j" -gt 1 ] && continue 2
    echo "i=$i j=$j"
  done
done
