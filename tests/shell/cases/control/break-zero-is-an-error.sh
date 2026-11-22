# tier: language
# world: none
for i in 1 2; do
  break 0 2>/dev/null
  echo "status=$? i=$i"
done
echo "after loop"
