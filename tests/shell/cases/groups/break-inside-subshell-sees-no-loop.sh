# tier: language
# world: none
for i in 1 2 3; do
  (break; echo never)
  echo "i=$i"
done
