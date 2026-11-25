# tier: language
# world: none
for i in 1 2 3 4; do
  [ "$i" = 2 ] && continue
  echo "i=$i"
done
