# tier: language
# world: none
stop() { break; }
for i in 1 2 3; do
  echo "i=$i"
  stop 2>/dev/null
done
echo "status=$?"
