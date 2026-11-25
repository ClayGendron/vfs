# tier: language
# world: none
i=0
until [ "$i" -ge 10 ]; do
  while true; do i=$((i + 4)); break; done
done
echo "i=$i"
