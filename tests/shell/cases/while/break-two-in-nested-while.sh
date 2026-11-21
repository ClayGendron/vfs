# tier: language
# world: none
i=0
while true; do
  i=$((i + 1))
  while true; do
    echo "inner i=$i"
    break 2
  done
  echo "never"
done
echo "out with i=$i"
