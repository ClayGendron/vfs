# tier: language
# world: none
for i in 1 2 3; do
  if [ "$i" = 2 ]; then break; fi
  echo "i=$i"
done
echo "stopped at $i"
