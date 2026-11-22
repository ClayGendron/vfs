# tier: language
# world: none
for i in 1 2; do
  for j in a b c; do
    [ "$j" = b ] && break 2
    echo "$i$j"
  done
done
echo "after i=$i j=$j"
