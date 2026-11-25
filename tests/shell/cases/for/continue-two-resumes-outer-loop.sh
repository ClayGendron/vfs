# tier: language
# world: none
for a in 1 2; do
  for b in x y z; do
    [ "$b" = y ] && continue 2
    echo "$a$b"
  done
  echo "never reached"
done
