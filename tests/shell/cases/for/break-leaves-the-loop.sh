# tier: language
# world: none
for i in 1 2 3 4 5; do
  [ "$i" -eq 3 ] && break
  echo "i=$i"
done
echo "status=$?"
