# tier: language
# world: none
f() { break; }
for i in 1 2 3; do
  echo "i=$i"
  f
done
echo "after loop"
