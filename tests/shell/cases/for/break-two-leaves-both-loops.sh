# tier: language
# world: none
for a in 1 2 3; do
  for b in x y z; do
    [ "$b" = y ] && break 2
    echo "$a$b"
  done
done
echo "after a=$a b=$b"
