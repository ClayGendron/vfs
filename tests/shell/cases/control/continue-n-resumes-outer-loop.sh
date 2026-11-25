# tier: language
# world: none
for i in 1 2 3; do
  for j in a b c; do
    [ "$j" = b ] && continue 2
    echo "$i$j"
  done
  echo "not reached"
done
