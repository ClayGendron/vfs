# tier: language
# world: none
n=5 total=0
while (( n > 0 )); do
  (( total += n, n-- ))
done
echo "total=$total n=$n"
