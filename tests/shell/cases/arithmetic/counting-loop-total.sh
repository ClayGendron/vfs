# tier: language
# world: none
total=0
for n in 3 4 5; do
  total=$(( total + n * n ))
done
echo "total=$total"
