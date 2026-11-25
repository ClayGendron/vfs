# tier: language
# world: none
set -e
for i in 1 2 3; do
  echo "i=$i"
  [ "$i" -lt 2 ]
done
echo "not reached"
