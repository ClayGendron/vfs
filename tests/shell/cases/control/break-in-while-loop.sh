# tier: language
# world: none
n=0
while true; do
  n=$((n + 1))
  [ "$n" -ge 3 ] && break
done
echo "n=$n"
