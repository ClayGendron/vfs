# tier: language
# world: none
n=0
while :; do
  n=$((n + 1))
  [ "$n" -eq 4 ] && break
done
echo "n=$n"
