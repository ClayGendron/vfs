# tier: language
# world: none
for i in 1 2 3; do
  ( [ "$i" = 2 ] && break; echo "sub i=$i" )
  echo "loop i=$i"
done
