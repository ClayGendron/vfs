# tier: language
# world: none
for i in 1 2 3 4; do
  [ "$i" = 3 ] && break
  echo "i=$i"
done
echo "after loop i=$i"
