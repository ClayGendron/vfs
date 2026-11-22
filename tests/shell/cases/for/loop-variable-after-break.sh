# tier: language
# world: none
for i in 1 2 3 4; do
  [ "$i" = 3 ] && break
done
echo "i=$i"
