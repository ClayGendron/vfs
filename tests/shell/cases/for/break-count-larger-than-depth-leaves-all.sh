# tier: language
# world: none
for a in 1 2; do
  for b in 1 2; do
    break 5
  done
  echo "never"
done
echo "status=$? a=$a b=$b"
