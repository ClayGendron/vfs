# tier: language
# world: none
for i in 1 2; do
  for j in a b; do
    break 5
  done
  echo "not reached"
done
echo "status=$? i=$i j=$j"
